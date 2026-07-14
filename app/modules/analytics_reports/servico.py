import logging
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from app.core.clock import agora_utc, fuso_horario_negocio, hoje_operacional
from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.db.supabase import get_supabase_client
from app.modules.analytics_reports import domain
from app.modules.analytics_reports.ia import gerar_leitura
from app.modules.auth.domain.capacidades import plano_do_usuario, usuario_tem_capacidade
from app.modules.ia.servico import montar_dados_estruturados_periodo
from app.modules.notificacoes import servico as notificacoes_servico
from app.modules.notificacoes.esquemas import RequisicaoCriarNotificacao
from app.shared.db import first_or_none, to_db_payload
from supabase import Client

logger = logging.getLogger(__name__)

INTERVALO_COMUM = timedelta(days=7)
TEMPO_JOB_PRESO = timedelta(minutes=30)


def _eh_admin(usuario: dict) -> bool:
    return (
        str(usuario.get("papel") or "").lower() == "administrador"
        or plano_do_usuario(usuario) == "admin"
    )


def _tipo_do_usuario(usuario: dict) -> str:
    return "ia" if usuario_tem_capacidade(usuario, "ia.analitica") else "analytics"


def _parse_datetime(valor) -> datetime | None:
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=UTC)
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None


def _linhas_do_usuario(usuario_id: UUID | str, *, limite: int = 100) -> list[dict]:
    return (
        get_supabase_client()
        .table("analytics_relatorios")
        .select("*")
        .eq("usuario_id", str(usuario_id))
        .order("solicitado_em", desc=True)
        .limit(limite)
        .execute()
        .data
    )


def disponibilidade(usuario: dict, *, agora: datetime | None = None) -> dict:
    referencia = agora or agora_utc()
    linhas = _linhas_do_usuario(usuario["id"])
    em_andamento = next(
        (linha for linha in linhas if linha.get("status") in {"na_fila", "processando"}),
        None,
    )
    tipo = _tipo_do_usuario(usuario)
    plano = plano_do_usuario(usuario)
    if em_andamento:
        return {
            "pode_solicitar": False,
            "motivo": "Ja existe um relatorio sendo preparado para voce.",
            "proxima_solicitacao_em": None,
            "intervalo_dias": None if _eh_admin(usuario) else 7,
            "ilimitado": _eh_admin(usuario),
            "relatorio_em_andamento_id": em_andamento["id"],
            "plano": plano,
            "tipo": tipo,
        }
    if _eh_admin(usuario):
        return {
            "pode_solicitar": True,
            "motivo": None,
            "proxima_solicitacao_em": None,
            "intervalo_dias": None,
            "ilimitado": True,
            "relatorio_em_andamento_id": None,
            "plano": plano,
            "tipo": tipo,
        }
    ultimo_pronto = next((linha for linha in linhas if linha.get("status") == "pronto"), None)
    solicitado_em = _parse_datetime((ultimo_pronto or {}).get("solicitado_em"))
    proxima = solicitado_em + INTERVALO_COMUM if solicitado_em else None
    pode = not proxima or referencia >= proxima
    return {
        "pode_solicitar": pode,
        "motivo": None if pode else "Seu proximo relatorio fica disponivel em breve.",
        "proxima_solicitacao_em": None if pode else proxima,
        "intervalo_dias": 7,
        "ilimitado": False,
        "relatorio_em_andamento_id": None,
        "plano": plano,
        "tipo": tipo,
    }


def solicitar_relatorio(*, usuario: dict, data_inicio: date, data_fim: date) -> dict:
    if data_fim > hoje_operacional():
        raise BadRequestError("O relatorio nao pode incluir datas futuras.")
    if data_fim < data_inicio or (data_fim - data_inicio).days > 365:
        raise BadRequestError("Escolha um periodo entre 1 e 366 dias.")
    estado = disponibilidade(usuario)
    if estado["relatorio_em_andamento_id"]:
        linha = buscar_relatorio(
            estado["relatorio_em_andamento_id"],
            usuario_id=usuario["id"],
        )
        linha["reaproveitado"] = True
        return linha
    if not estado["pode_solicitar"]:
        raise ConflictError(
            estado["motivo"] or "Aguarde para solicitar outro relatorio.",
            {
                "proxima_solicitacao_em": (
                    estado["proxima_solicitacao_em"].isoformat()
                    if estado["proxima_solicitacao_em"]
                    else None
                )
            },
        )

    agora = agora_utc()
    plano = plano_do_usuario(usuario)
    tipo = _tipo_do_usuario(usuario)
    try:
        linha = (
            get_supabase_client()
            .table("analytics_relatorios")
            .insert(
                to_db_payload(
                    {
                        "usuario_id": usuario["id"],
                        "plano_origem": plano,
                        "tipo": tipo,
                        "data_inicio": data_inicio,
                        "data_fim": data_fim,
                        "status": "na_fila",
                        "progresso": 5,
                        "etapa": "Aguardando processamento",
                        "export_token": uuid4(),
                        "solicitado_em": agora,
                        "atualizado_em": agora,
                    }
                )
            )
            .execute()
            .data[0]
        )
    except Exception as exc:
        if "analytics_relatorios_usuario_ativo_idx" in str(exc):
            ativo = disponibilidade(usuario)["relatorio_em_andamento_id"]
            if ativo:
                linha = buscar_relatorio(ativo, usuario_id=usuario["id"])
                linha["reaproveitado"] = True
                return linha
        raise

    from app.modules.analytics_reports.worker import agendar

    agendar(linha["id"])
    return _formatar_saida(linha)


def listar_relatorios(*, usuario_id: UUID | str, limite: int = 30) -> list[dict]:
    return [_formatar_saida(linha) for linha in _linhas_do_usuario(usuario_id, limite=limite)]


def buscar_relatorio(relatorio_id: UUID | str, *, usuario_id: UUID | str) -> dict:
    linha = first_or_none(
        get_supabase_client()
        .table("analytics_relatorios")
        .select("*")
        .eq("id", str(relatorio_id))
        .eq("usuario_id", str(usuario_id))
        .limit(1)
        .execute()
        .data
    )
    if not linha:
        raise NotFoundError("Relatorio de Analytics", str(relatorio_id))
    return _formatar_saida(linha)


def buscar_por_token(relatorio_id: UUID | str, token: UUID | str) -> dict:
    linha = first_or_none(
        get_supabase_client()
        .table("analytics_relatorios")
        .select("*")
        .eq("id", str(relatorio_id))
        .eq("export_token", str(token))
        .eq("status", "pronto")
        .limit(1)
        .execute()
        .data
    )
    if not linha:
        raise NotFoundError("Relatorio de Analytics", str(relatorio_id))
    return linha


def _atualizar(relatorio_id: UUID | str, dados: dict) -> dict:
    linhas = (
        get_supabase_client()
        .table("analytics_relatorios")
        .update(to_db_payload({**dados, "atualizado_em": agora_utc()}))
        .eq("id", str(relatorio_id))
        .execute()
        .data
    )
    return linhas[0] if linhas else {}


def _reivindicar(relatorio_id: UUID | str) -> dict | None:
    linhas = (
        get_supabase_client()
        .table("analytics_relatorios")
        .update(
            to_db_payload(
                {
                    "status": "processando",
                    "progresso": 12,
                    "etapa": "Organizando seus dados",
                    "iniciado_em": agora_utc(),
                    "erro": None,
                }
            )
        )
        .eq("id", str(relatorio_id))
        .eq("status", "na_fila")
        .execute()
        .data
    )
    return linhas[0] if linhas else None


def _coletar_vendas(
    client: Client,
    *,
    usuario_id: UUID | str,
    data_inicio: str,
    data_fim: str,
) -> dict:
    dias = (
        client.table("dias_de_venda")
        .select("id,data_venda")
        .eq("usuario_id", str(usuario_id))
        .gte("data_venda", data_inicio)
        .lte("data_venda", data_fim)
        .execute()
        .data
    )
    dia_por_id = {str(dia["id"]): dia["data_venda"] for dia in dias}
    if not dia_por_id:
        return {"quantidade": 0, "por_data": {}, "por_hora": []}
    vendas = (
        client.table("vendas")
        .select("id,dia_de_venda_id,ocorrido_em")
        .eq("usuario_id", str(usuario_id))
        .in_("dia_de_venda_id", list(dia_por_id))
        .eq("situacao", "ativa")
        .execute()
        .data
    )
    venda_ids = [venda["id"] for venda in vendas]
    itens = []
    if venda_ids:
        itens = (
            client.table("itens_venda")
            .select("venda_id,valor_total_venda")
            .in_("venda_id", venda_ids)
            .execute()
            .data
        )
    valor_por_venda: dict[str, float] = {}
    for item in itens:
        venda_id = str(item["venda_id"])
        valor_por_venda[venda_id] = valor_por_venda.get(venda_id, 0.0) + float(
            item.get("valor_total_venda") or 0
        )
    por_data: dict[str, int] = {}
    por_hora = {hora: {"hora": hora, "vendas": 0, "faturamento": 0.0} for hora in range(24)}
    for venda in vendas:
        data_venda = dia_por_id.get(str(venda["dia_de_venda_id"]))
        if data_venda:
            por_data[data_venda] = por_data.get(data_venda, 0) + 1
        ocorrido = _parse_datetime(venda.get("ocorrido_em"))
        if ocorrido:
            hora = ocorrido.astimezone(fuso_horario_negocio()).hour
            por_hora[hora]["vendas"] += 1
            por_hora[hora]["faturamento"] += valor_por_venda.get(str(venda["id"]), 0)
    faixas = []
    for item in por_hora.values():
        if item["vendas"]:
            item["faturamento"] = round(item["faturamento"], 2)
            faixas.append(item)
    return {"quantidade": len(vendas), "por_data": por_data, "por_hora": faixas}


def _dados_do_periodo(
    *, usuario_id: UUID | str, data_inicio: date, data_fim: date
) -> dict:
    dados = montar_dados_estruturados_periodo(
        data_inicio=data_inicio.isoformat(),
        data_fim=data_fim.isoformat(),
        usuario_id=usuario_id,
    )
    vendas = _coletar_vendas(
        get_supabase_client(),
        usuario_id=usuario_id,
        data_inicio=data_inicio.isoformat(),
        data_fim=data_fim.isoformat(),
    )
    dados["quantidadeVendas"] = vendas["quantidade"]
    dados["vendasPorHora"] = vendas["por_hora"]
    for dia in dados.get("dias") or []:
        dia["quantidadeVendas"] = vendas["por_data"].get(str(dia.get("data")), 0)
    return dados


def processar_relatorio(relatorio_id: UUID | str) -> None:
    linha = _reivindicar(relatorio_id)
    if not linha:
        return
    try:
        data_inicio = date.fromisoformat(str(linha["data_inicio"]))
        data_fim = date.fromisoformat(str(linha["data_fim"]))
        tamanho = (data_fim - data_inicio).days + 1
        anterior_fim = data_inicio - timedelta(days=1)
        anterior_inicio = data_inicio - timedelta(days=tamanho)
        _atualizar(
            relatorio_id,
            {"progresso": 30, "etapa": "Conferindo vendas, producao e custos"},
        )
        atual = _dados_do_periodo(
            usuario_id=linha["usuario_id"],
            data_inicio=data_inicio,
            data_fim=data_fim,
        )
        anterior = _dados_do_periodo(
            usuario_id=linha["usuario_id"],
            data_inicio=anterior_inicio,
            data_fim=anterior_fim,
        )
        _atualizar(
            relatorio_id,
            {"progresso": 62, "etapa": "Encontrando tendencias e oportunidades"},
        )
        conteudo = domain.montar_relatorio(
            atual=atual,
            anterior=anterior,
            tipo=linha["tipo"],
            gerado_em=agora_utc(),
        )
        modelo_ia = None
        if linha["tipo"] == "ia":
            _atualizar(
                relatorio_id,
                {"progresso": 78, "etapa": "O Paozinho esta fazendo a leitura estrategica"},
            )
            conteudo["ia"] = gerar_leitura(conteudo)
            modelo_ia = conteudo["ia"]["modelo"]
        titulo = f"Raio-X do negocio - {data_inicio:%d/%m/%Y} a {data_fim:%d/%m/%Y}"
        concluido = agora_utc()
        _atualizar(
            relatorio_id,
            {
                "status": "pronto",
                "progresso": 100,
                "etapa": "Relatorio pronto",
                "titulo": titulo,
                "conteudo": conteudo,
                "modelo_ia": modelo_ia,
                "concluido_em": concluido,
                "erro": None,
            },
        )
        _notificar_conclusao(linha, titulo)
    except Exception as exc:  # noqa: BLE001 - persiste falha e libera nova tentativa
        logger.exception("Falha ao processar relatorio de Analytics %s", relatorio_id)
        _atualizar(
            relatorio_id,
            {
                "status": "falhou",
                "progresso": 100,
                "etapa": "Nao foi possivel concluir",
                "erro": "Nao conseguimos concluir este relatorio. Voce ja pode tentar novamente.",
                "concluido_em": agora_utc(),
            },
        )
        raise exc


def _notificar_conclusao(linha: dict, titulo: str) -> None:
    try:
        notificacoes_servico.criar_notificacao(
            RequisicaoCriarNotificacao(
                titulo="Seu Raio-X do negocio esta pronto",
                corpo=(
                    "Terminamos de analisar suas vendas, producao, sobras e oportunidades. "
                    "Toque em Abrir relatorio para ver tudo."
                ),
                publico="usuario",
                usuario_alvo_id=UUID(str(linha["usuario_id"])),
                prioridade="alta",
                metadados={
                    "tipo": "analytics_relatorio_pronto",
                    "relatorio_id": str(linha["id"]),
                    "rota": f"/relatorio/{linha['id']}",
                    "titulo_relatorio": titulo,
                },
                publicar_agora=True,
                expira_em_dias=365,
            ),
            {"id": linha["usuario_id"]},
        )
    except Exception:  # noqa: BLE001 - notificacao nao invalida o relatorio pronto
        logger.exception("Falha ao notificar conclusao do relatorio %s", linha["id"])


def recuperar_e_listar_pendentes() -> tuple[list[str], int]:
    client = get_supabase_client()
    limite = (agora_utc() - TEMPO_JOB_PRESO).isoformat()
    presos = (
        client.table("analytics_relatorios")
        .select("id")
        .eq("status", "processando")
        .lt("iniciado_em", limite)
        .execute()
        .data
    )
    for preso in presos:
        (
            client.table("analytics_relatorios")
            .update(
                {
                    "status": "na_fila",
                    "progresso": 5,
                    "etapa": "Retomando processamento",
                }
            )
            .eq("id", str(preso["id"]))
            .eq("status", "processando")
            .execute()
        )
    pendentes = (
        client.table("analytics_relatorios")
        .select("id")
        .eq("status", "na_fila")
        .order("solicitado_em")
        .limit(100)
        .execute()
        .data
    )
    return [str(linha["id"]) for linha in pendentes], len(presos)


def _formatar_saida(linha: dict) -> dict:
    token = linha.get("export_token")
    url = None
    if linha.get("status") == "pronto" and token:
        url = (
            f"/api/v1/analytics/relatorios/compartilhados/{linha['id']}/"
            f"padoka-analytics.pdf?token={token}"
        )
    return {
        "id": linha["id"],
        "status": linha.get("status") or "na_fila",
        "tipo": linha.get("tipo") or "analytics",
        "plano_origem": linha.get("plano_origem") or "analitico",
        "data_inicio": linha["data_inicio"],
        "data_fim": linha["data_fim"],
        "progresso": linha.get("progresso") or 0,
        "etapa": linha.get("etapa") or "Aguardando processamento",
        "titulo": linha.get("titulo"),
        "conteudo": linha.get("conteudo"),
        "modelo_ia": linha.get("modelo_ia"),
        "erro": linha.get("erro"),
        "solicitado_em": linha.get("solicitado_em"),
        "iniciado_em": linha.get("iniciado_em"),
        "concluido_em": linha.get("concluido_em"),
        "atualizado_em": linha.get("atualizado_em") or linha.get("solicitado_em"),
        "url_exportacao": url,
        "reaproveitado": linha.get("reaproveitado", False),
    }
