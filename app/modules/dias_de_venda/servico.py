from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from supabase import Client

from app.core.errors import BadRequestError, NotFoundError
from app.db.supabase import get_supabase_client
from app.modules.dias_de_venda.esquemas import (
    RequisicaoAtualizarDiaDeVenda,
    RequisicaoCriarDiaDeVenda,
    RequisicaoCriarItemProducao,
    RequisicaoDecisaoSobra,
    RequisicaoFecharDiaDeVenda,
    RequisicaoIniciarDiaDeVenda,
)
from app.modules.locais import servico as servico_de_locais
from app.modules.produtos import servico as servico_de_produtos
from app.shared.db import first_or_none, to_db_payload
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo

FUSO_HORARIO_NEGOCIO = "America/Sao_Paulo"
FUSO_HORARIO_NEGOCIO_FALLBACK = timezone(timedelta(hours=-3))


def listar_dias_de_venda(
    *,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    situacao: str | None = None,
) -> list[dict]:
    client = get_supabase_client()
    consulta = client.table("dias_de_venda").select("*").order("data_venda", desc=True)
    if data_inicio:
        consulta = consulta.gte("data_venda", data_inicio.isoformat())
    if data_fim:
        consulta = consulta.lte("data_venda", data_fim.isoformat())
    if situacao:
        consulta = consulta.eq("situacao", situacao)
    dias = consulta.execute().data
    return [_anexar_itens_producao(client, dia) for dia in dias]


def criar_dia_de_venda(requisicao: RequisicaoCriarDiaDeVenda) -> dict:
    client = get_supabase_client()
    nome_local_no_momento = requisicao.nome_local
    if requisicao.local_id:
        local = servico_de_locais.buscar_local(requisicao.local_id)
        nome_local_no_momento = local["nome"]

    dados_dia = to_db_payload(
        {
            "data_venda": requisicao.data_venda,
            "local_id": requisicao.local_id,
            "nome_local_no_momento": nome_local_no_momento,
            "observacoes": requisicao.observacoes,
            "situacao": "aberto",
        }
    )
    dia_de_venda = client.table("dias_de_venda").insert(dados_dia).execute().data[0]
    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="dia_de_venda_aberto",
        titulo=f"Dia aberto: {dia_de_venda['data_venda']}",
        tipo_entidade="dia_de_venda",
        entidade_id=dia_de_venda["id"],
        dia_de_venda_id=dia_de_venda["id"],
        detalhes={"nome_local": nome_local_no_momento},
    )

    for item in requisicao.itens_producao:
        salvar_item_producao(UUID(dia_de_venda["id"]), item)

    return buscar_dia_de_venda(UUID(dia_de_venda["id"]))


def iniciar_dia_de_venda(requisicao: RequisicaoIniciarDiaDeVenda) -> dict:
    client = get_supabase_client()
    data_venda = requisicao.data_venda or _data_operacional_hoje()
    dia_atual = _buscar_dia_aberto_por_data(client, data_venda)
    dia_anterior = _buscar_dia_aberto_anterior(client, data_venda)

    if not dia_anterior:
        if dia_atual:
            _salvar_itens_producao_informados(UUID(dia_atual["id"]), requisicao.itens_producao)
            return {
                "acao": "dia_atual_aberto",
                "mensagem": "O dia de venda de hoje ja esta aberto.",
                "data_venda": data_venda,
                "dia_de_venda": buscar_dia_de_venda(UUID(dia_atual["id"])),
                "dia_anterior": None,
                "sobras_pendentes": [],
                "decisoes_sobra": _listar_decisoes_sobra_do_destino(client, dia_atual["id"]),
            }
        if requisicao.decisoes_sobra:
            raise BadRequestError("Nao ha dia anterior aberto com sobra pendente.")

        dia_atual = _criar_dia_de_venda_para_inicio(requisicao, data_venda, None)
        return {
            "acao": "dia_iniciado",
            "mensagem": "Dia de venda iniciado.",
            "data_venda": data_venda,
            "dia_de_venda": dia_atual,
            "dia_anterior": None,
            "sobras_pendentes": [],
            "decisoes_sobra": [],
        }

    sobras_pendentes = _calcular_sobras_pendentes(client, dia_anterior["id"])
    if sobras_pendentes:
        decisoes_existentes = []
        if dia_atual:
            decisoes_existentes = _listar_decisoes_sobra_por_origem_destino(
                client,
                dia_origem_id=dia_anterior["id"],
                dia_destino_id=dia_atual["id"],
            )
        if not requisicao.decisoes_sobra and not decisoes_existentes:
            return {
                "acao": "decidir_sobras",
                "mensagem": (
                    "Existe sobra do dia anterior. Escolha o que usar hoje antes de iniciar."
                ),
                "data_venda": data_venda,
                "dia_de_venda": buscar_dia_de_venda(UUID(dia_atual["id"])) if dia_atual else None,
                "dia_anterior": _anexar_itens_producao(client, dia_anterior),
                "sobras_pendentes": sobras_pendentes,
                "decisoes_sobra": [],
            }
        if not dia_atual:
            dia_atual = _criar_dia_de_venda_para_inicio(requisicao, data_venda, dia_anterior)
        else:
            _salvar_itens_producao_informados(UUID(dia_atual["id"]), requisicao.itens_producao)

        if decisoes_existentes:
            decisoes_sobra = decisoes_existentes
        else:
            decisoes_sobra = _registrar_decisoes_sobra(
                client,
                dia_origem=dia_anterior,
                dia_destino=dia_atual,
                sobras_pendentes=sobras_pendentes,
                decisoes=requisicao.decisoes_sobra,
            )
    else:
        if requisicao.decisoes_sobra:
            raise BadRequestError("O dia anterior aberto nao tem sobra pendente.")
        decisoes_sobra = []
        if not dia_atual:
            dia_atual = _criar_dia_de_venda_para_inicio(requisicao, data_venda, dia_anterior)
        else:
            _salvar_itens_producao_informados(UUID(dia_atual["id"]), requisicao.itens_producao)

    dia_anterior_fechado = fechar_dia_de_venda(
        UUID(dia_anterior["id"]),
        RequisicaoFecharDiaDeVenda(observacoes=requisicao.observacoes_fechamento_dia_anterior),
    )
    return {
        "acao": "dia_iniciado",
        "mensagem": "Dia anterior fechado e novo dia iniciado.",
        "data_venda": data_venda,
        "dia_de_venda": buscar_dia_de_venda(UUID(dia_atual["id"])),
        "dia_anterior": dia_anterior_fechado,
        "sobras_pendentes": [],
        "decisoes_sobra": decisoes_sobra,
    }


def buscar_dia_de_venda_atual(*, data_venda: date | None = None) -> dict:
    client = get_supabase_client()
    consulta = (
        client.table("dias_de_venda")
        .select("*")
        .eq("situacao", "aberto")
        .order("aberto_em", desc=True)
    )
    if data_venda:
        consulta = consulta.eq("data_venda", data_venda.isoformat())
    dia_de_venda = first_or_none(consulta.limit(1).execute().data)
    if not dia_de_venda:
        raise NotFoundError(
            "Dia de venda aberto",
            data_venda.isoformat() if data_venda else "atual",
        )
    return _anexar_itens_producao(client, dia_de_venda)


def buscar_dia_de_venda(dia_de_venda_id: UUID | str) -> dict:
    client = get_supabase_client()
    dia_de_venda = buscar_linha_dia_de_venda(client, dia_de_venda_id)
    return _anexar_itens_producao(client, dia_de_venda)


def buscar_linha_dia_de_venda(client: Client, dia_de_venda_id: UUID | str) -> dict:
    dia_de_venda = first_or_none(
        client.table("dias_de_venda")
        .select("*")
        .eq("id", str(dia_de_venda_id))
        .limit(1)
        .execute()
        .data
    )
    if not dia_de_venda:
        raise NotFoundError("Dia de venda", str(dia_de_venda_id))
    return dia_de_venda


def atualizar_dia_de_venda(
    dia_de_venda_id: UUID,
    requisicao: RequisicaoAtualizarDiaDeVenda,
) -> dict:
    client = get_supabase_client()
    dia_de_venda = buscar_linha_dia_de_venda(client, dia_de_venda_id)
    if dia_de_venda["situacao"] == "fechado":
        raise BadRequestError("Nao e possivel editar um dia fechado.")

    dados_atualizacao = requisicao.model_dump(exclude_unset=True)
    if requisicao.local_id:
        local = servico_de_locais.buscar_local(requisicao.local_id)
        dados_atualizacao["nome_local_no_momento"] = local["nome"]
    elif requisicao.nome_local is not None:
        dados_atualizacao["nome_local_no_momento"] = requisicao.nome_local
    dados_atualizacao.pop("nome_local", None)

    if dados_atualizacao:
        dia_de_venda = (
            client.table("dias_de_venda")
            .update(to_db_payload(dados_atualizacao))
            .eq("id", str(dia_de_venda_id))
            .execute()
            .data[0]
        )
        registrar_evento_na_linha_do_tempo(
            client,
            tipo_evento="dia_de_venda_atualizado",
            titulo=f"Dia atualizado: {dia_de_venda['data_venda']}",
            tipo_entidade="dia_de_venda",
            entidade_id=dia_de_venda_id,
            dia_de_venda_id=dia_de_venda_id,
            detalhes={"campos_alterados": sorted(dados_atualizacao.keys())},
        )
    return _anexar_itens_producao(client, dia_de_venda)


def salvar_item_producao(dia_de_venda_id: UUID, requisicao: RequisicaoCriarItemProducao) -> dict:
    client = get_supabase_client()
    dia_de_venda = buscar_linha_dia_de_venda(client, dia_de_venda_id)
    if dia_de_venda["situacao"] == "fechado":
        raise BadRequestError("Nao e possivel alterar a producao de um dia fechado.")

    snapshot = servico_de_produtos.buscar_snapshot_do_produto(
        requisicao.produto_id,
        date.fromisoformat(dia_de_venda["data_venda"]),
    )
    produto = snapshot["produto"]
    preco = snapshot["preco"]
    dados_item = to_db_payload(
        {
            "dia_de_venda_id": dia_de_venda_id,
            "produto_id": requisicao.produto_id,
            "nome_produto_no_momento": produto["nome"],
            "url_imagem_produto_no_momento": produto.get("url_imagem_principal"),
            "versao_preco_id": preco["id"],
            "preco_venda_unitario_no_momento": preco["preco_venda"],
            "preco_custo_unitario_no_momento": preco["preco_custo"],
            "quantidade_produzida": requisicao.quantidade_produzida,
            "observacoes": requisicao.observacoes,
        }
    )

    existente = first_or_none(
        client.table("itens_producao")
        .select("*")
        .eq("dia_de_venda_id", str(dia_de_venda_id))
        .eq("produto_id", str(requisicao.produto_id))
        .limit(1)
        .execute()
        .data
    )
    if existente:
        item = (
            client.table("itens_producao")
            .update(dados_item)
            .eq("id", existente["id"])
            .execute()
            .data[0]
        )
        tipo_evento = "item_producao_atualizado"
        titulo = f"Producao atualizada: {produto['nome']}"
    else:
        item = client.table("itens_producao").insert(dados_item).execute().data[0]
        tipo_evento = "item_producao_adicionado"
        titulo = f"Producao adicionada: {produto['nome']}"

    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento=tipo_evento,
        titulo=titulo,
        tipo_entidade="item_producao",
        entidade_id=item["id"],
        dia_de_venda_id=dia_de_venda_id,
        detalhes={
            "produto_id": str(requisicao.produto_id),
            "quantidade_produzida": requisicao.quantidade_produzida,
            "preco_venda_unitario_no_momento": preco["preco_venda"],
        },
    )
    return item


def fechar_dia_de_venda(dia_de_venda_id: UUID, requisicao: RequisicaoFecharDiaDeVenda) -> dict:
    client = get_supabase_client()
    dia_de_venda = buscar_linha_dia_de_venda(client, dia_de_venda_id)
    if dia_de_venda["situacao"] == "fechado":
        return _anexar_itens_producao(client, dia_de_venda)

    dados_atualizacao = {
        "situacao": "fechado",
        "fechado_em": datetime.now(timezone.utc),
    }
    if requisicao.observacoes is not None:
        dados_atualizacao["observacoes"] = requisicao.observacoes
    dia_fechado = (
        client.table("dias_de_venda")
        .update(to_db_payload(dados_atualizacao))
        .eq("id", str(dia_de_venda_id))
        .execute()
        .data[0]
    )
    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="dia_de_venda_fechado",
        titulo=f"Dia fechado: {dia_fechado['data_venda']}",
        tipo_entidade="dia_de_venda",
        entidade_id=dia_de_venda_id,
        dia_de_venda_id=dia_de_venda_id,
    )
    return _anexar_itens_producao(client, dia_fechado)


def _anexar_itens_producao(client: Client, dia_de_venda: dict) -> dict:
    itens = (
        client.table("itens_producao")
        .select("*")
        .eq("dia_de_venda_id", dia_de_venda["id"])
        .order("nome_produto_no_momento")
        .execute()
        .data
    )
    dia_de_venda["itens_producao"] = itens
    dia_de_venda["sobras_usadas_hoje"] = _listar_decisoes_sobra_do_destino(
        client,
        dia_de_venda["id"],
    )
    return dia_de_venda


def _data_operacional_hoje() -> date:
    return datetime.now(_fuso_horario_negocio()).date()


def _fuso_horario_negocio():
    try:
        return ZoneInfo(FUSO_HORARIO_NEGOCIO)
    except ZoneInfoNotFoundError:
        return FUSO_HORARIO_NEGOCIO_FALLBACK


def _buscar_dia_aberto_por_data(client: Client, data_venda: date) -> dict | None:
    return first_or_none(
        client.table("dias_de_venda")
        .select("*")
        .eq("situacao", "aberto")
        .eq("data_venda", data_venda.isoformat())
        .order("aberto_em", desc=True)
        .limit(1)
        .execute()
        .data
    )


def _buscar_dia_aberto_anterior(client: Client, data_venda: date) -> dict | None:
    return first_or_none(
        client.table("dias_de_venda")
        .select("*")
        .eq("situacao", "aberto")
        .lt("data_venda", data_venda.isoformat())
        .order("data_venda", desc=True)
        .order("aberto_em", desc=True)
        .limit(1)
        .execute()
        .data
    )


def _criar_dia_de_venda_para_inicio(
    requisicao: RequisicaoIniciarDiaDeVenda,
    data_venda: date,
    dia_anterior: dict | None,
) -> dict:
    local_id = requisicao.local_id
    nome_local = requisicao.nome_local
    if not local_id and nome_local is None and dia_anterior:
        local_id = dia_anterior.get("local_id")
        nome_local = None if local_id else dia_anterior.get("nome_local_no_momento")

    return criar_dia_de_venda(
        RequisicaoCriarDiaDeVenda(
            data_venda=data_venda,
            local_id=local_id,
            nome_local=nome_local,
            observacoes=requisicao.observacoes,
            itens_producao=requisicao.itens_producao,
        )
    )


def _salvar_itens_producao_informados(
    dia_de_venda_id: UUID,
    itens_producao: list[RequisicaoCriarItemProducao],
) -> None:
    for item in itens_producao:
        salvar_item_producao(dia_de_venda_id, item)


def _calcular_sobras_pendentes(client: Client, dia_de_venda_id: UUID | str) -> list[dict]:
    itens_producao = (
        client.table("itens_producao")
        .select("*")
        .eq("dia_de_venda_id", str(dia_de_venda_id))
        .execute()
        .data
    )
    vendas_ativas = (
        client.table("vendas")
        .select("id")
        .eq("dia_de_venda_id", str(dia_de_venda_id))
        .eq("situacao", "ativa")
        .execute()
        .data
    )
    venda_ids = [venda["id"] for venda in vendas_ativas]
    itens_venda = []
    if venda_ids:
        itens_venda = (
            client.table("itens_venda")
            .select("*")
            .in_("venda_id", venda_ids)
            .execute()
            .data
        )

    vendidos_por_produto: dict[str, int] = {}
    for item in itens_venda:
        produto_id = item["produto_id"]
        vendidos_por_produto[produto_id] = (
            vendidos_por_produto.get(produto_id, 0) + item["quantidade"]
        )

    sobras = []
    for item in itens_producao:
        quantidade_sobra = item["quantidade_produzida"] - vendidos_por_produto.get(
            item["produto_id"],
            0,
        )
        if quantidade_sobra <= 0:
            continue
        sobras.append(
            {
                "produto_id": item["produto_id"],
                "nome_produto": item["nome_produto_no_momento"],
                "url_imagem_produto": item.get("url_imagem_produto_no_momento"),
                "quantidade_sobra": quantidade_sobra,
                "quantidade_sugerida_para_usar": quantidade_sobra,
            }
        )
    return sorted(sobras, key=lambda item: item["nome_produto"])


def _registrar_decisoes_sobra(
    client: Client,
    *,
    dia_origem: dict,
    dia_destino: dict,
    sobras_pendentes: list[dict],
    decisoes: list[RequisicaoDecisaoSobra],
) -> list[dict]:
    if not decisoes:
        raise BadRequestError("Informe a decisao para cada sobra pendente.")

    sobras_por_produto = {sobra["produto_id"]: sobra for sobra in sobras_pendentes}
    decisoes_por_produto: dict[str, RequisicaoDecisaoSobra] = {}
    for decisao in decisoes:
        produto_id = str(decisao.produto_id)
        if produto_id in decisoes_por_produto:
            raise BadRequestError("Ha decisao de sobra repetida para o mesmo produto.")
        decisoes_por_produto[produto_id] = decisao

    produtos_pendentes = set(sobras_por_produto)
    produtos_decididos = set(decisoes_por_produto)
    produtos_faltando = produtos_pendentes - produtos_decididos
    produtos_extras = produtos_decididos - produtos_pendentes
    if produtos_faltando or produtos_extras:
        raise BadRequestError(
            "As decisoes de sobra precisam corresponder exatamente as sobras pendentes.",
            {
                "produtos_faltando": sorted(produtos_faltando),
                "produtos_sem_sobra_pendente": sorted(produtos_extras),
            },
        )

    linhas = []
    for produto_id, sobra in sobras_por_produto.items():
        decisao = decisoes_por_produto[produto_id]
        quantidade_usada = decisao.quantidade_usada_hoje
        quantidade_sobra = sobra["quantidade_sobra"]
        quantidade_nao_usada = decisao.quantidade_nao_usada_hoje
        if quantidade_nao_usada is None:
            quantidade_nao_usada = quantidade_sobra - quantidade_usada
        if quantidade_nao_usada < 0:
            raise BadRequestError(
                "A quantidade usada hoje nao pode ser maior que a sobra de origem.",
                {
                    "produto_id": produto_id,
                    "quantidade_sobra": quantidade_sobra,
                    "quantidade_usada_hoje": quantidade_usada,
                },
            )
        if quantidade_usada + quantidade_nao_usada != quantidade_sobra:
            raise BadRequestError(
                "A soma entre sobra usada hoje e nao usada hoje deve fechar a sobra de origem.",
                {
                    "produto_id": produto_id,
                    "quantidade_sobra": quantidade_sobra,
                    "quantidade_usada_hoje": quantidade_usada,
                    "quantidade_nao_usada_hoje": quantidade_nao_usada,
                },
            )

        linhas.append(
            to_db_payload(
                {
                    "dia_origem_id": dia_origem["id"],
                    "dia_destino_id": dia_destino["id"],
                    "produto_id": produto_id,
                    "nome_produto_no_momento": sobra["nome_produto"],
                    "url_imagem_produto_no_momento": sobra.get("url_imagem_produto"),
                    "quantidade_sobra_origem": quantidade_sobra,
                    "quantidade_usada_hoje": quantidade_usada,
                    "quantidade_nao_usada_hoje": quantidade_nao_usada,
                    "observacoes": decisao.observacoes,
                }
            )
        )

    decisoes_registradas = client.table("decisoes_sobra").insert(linhas).execute().data
    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="sobras_decididas",
        titulo="Sobras do dia anterior decididas",
        tipo_entidade="dia_de_venda",
        entidade_id=dia_destino["id"],
        dia_de_venda_id=dia_destino["id"],
        detalhes={
            "dia_origem_id": dia_origem["id"],
            "itens": [
                {
                    "produto_id": decisao["produto_id"],
                    "quantidade_sobra_origem": decisao["quantidade_sobra_origem"],
                    "quantidade_usada_hoje": decisao["quantidade_usada_hoje"],
                    "quantidade_nao_usada_hoje": decisao["quantidade_nao_usada_hoje"],
                }
                for decisao in decisoes_registradas
            ],
        },
    )
    return decisoes_registradas


def _listar_decisoes_sobra_do_destino(client: Client, dia_de_venda_id: UUID | str) -> list[dict]:
    return (
        client.table("decisoes_sobra")
        .select("*")
        .eq("dia_destino_id", str(dia_de_venda_id))
        .order("nome_produto_no_momento")
        .execute()
        .data
    )


def _listar_decisoes_sobra_por_origem_destino(
    client: Client,
    *,
    dia_origem_id: UUID | str,
    dia_destino_id: UUID | str,
) -> list[dict]:
    return (
        client.table("decisoes_sobra")
        .select("*")
        .eq("dia_origem_id", str(dia_origem_id))
        .eq("dia_destino_id", str(dia_destino_id))
        .order("nome_produto_no_momento")
        .execute()
        .data
    )
