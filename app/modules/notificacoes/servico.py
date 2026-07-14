from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import UploadFile

from app.core.errors import BadRequestError, NotFoundError
from app.db.supabase import get_supabase_client
from app.infra.supabase.payload import encode_value
from app.infra.supabase.result import executar_lista_opcional, tabela_ausente
from app.modules.auth.domain.capacidades import usuario_tem_capacidade
from app.modules.midia import servico as servico_de_midia
from app.modules.notificacoes.esquemas import (
    RequisicaoAtualizarNotificacao,
    RequisicaoCriarNotificacao,
)
from app.shared.db import first_or_none, to_db_payload
from supabase import Client


def listar_notificacoes_publicas(
    *,
    limite: int = 50,
    usuario: dict | None = None,
    usuario_id: UUID | str | None = None,
    incluir_lidas: bool = True,
    incluir_ocultas: bool = False,
) -> list[dict]:
    client = get_supabase_client()
    usuario = _normalizar_usuario(usuario, usuario_id)
    usuario_id_estado = _usuario_id_para_estado(usuario, usuario_id)
    linhas = _consultar_notificacoes_publicas(
        client,
        limite=_limite_consulta_publica(limite, usuario),
        campos=(
            "id,titulo,corpo,status,publico,planos_alvo,usuario_alvo_id,"
            "prioridade,midias,metadados,publicado_em,expira_em,criado_em"
        ),
    )
    linhas = [
        notificacao
        for notificacao in linhas
        if _notificacao_visivel_para_usuario(notificacao, usuario)
    ]
    notificacoes = _anexar_estado(
        client,
        _anexar_midias(client, linhas, enxuto=True),
        usuario_id=usuario_id_estado,
    )
    if not incluir_ocultas:
        notificacoes = [notificacao for notificacao in notificacoes if not notificacao["oculta"]]
    if not incluir_lidas:
        notificacoes = [notificacao for notificacao in notificacoes if not notificacao["lida"]]
    return [_formatar_notificacao_publica(notificacao) for notificacao in notificacoes[:limite]]


def obter_feed_notificacoes(
    *,
    limite: int = 20,
    usuario: dict | None = None,
    incluir_lidas: bool = True,
) -> dict:
    client = get_supabase_client()
    usuario = _normalizar_usuario(usuario)
    usuario_id_estado = _usuario_id_para_estado(usuario)
    notificacoes = _buscar_notificacoes_visiveis_com_estado(
        client,
        usuario=usuario,
        usuario_id_estado=usuario_id_estado,
    )
    notificacoes = [notificacao for notificacao in notificacoes if not notificacao["oculta"]]

    nao_lidas = sorted(
        [notificacao for notificacao in notificacoes if not notificacao["lida"]],
        key=_chave_feed,
    )
    lidas = sorted(
        [notificacao for notificacao in notificacoes if notificacao["lida"]],
        key=_chave_feed,
    )
    candidatas = nao_lidas + (lidas if incluir_lidas else [])
    itens = candidatas[:limite]

    return {
        "itens": [_formatar_notificacao_publica(notificacao) for notificacao in itens],
        "resumo": {
            "total": len(notificacoes),
            "nao_lidas": len(nao_lidas),
            "lidas": len(lidas),
            "novas": len(nao_lidas),
            "retornadas": len(itens),
        },
        "limite": limite,
        "tem_mais": len(candidatas) > len(itens),
        "persistida": bool(usuario_id_estado),
    }


def listar_notificacoes_admin(*, status: str | None = None, limite: int = 100) -> list[dict]:
    client = get_supabase_client()
    consulta = client.table("notificacoes").select("*").order("criado_em", desc=True).limit(limite)
    if status:
        consulta = consulta.eq("status", status)
    return _anexar_midias(client, consulta.execute().data)


def buscar_notificacao_publica(
    notificacao_id: UUID,
    *,
    usuario: dict | None = None,
    usuario_id: UUID | str | None = None,
) -> dict:
    notificacao = buscar_notificacao(notificacao_id)
    usuario = _normalizar_usuario(usuario, usuario_id)
    if not _notificacao_visivel_para_usuario(notificacao, usuario):
        raise NotFoundError("Notificacao", str(notificacao_id))
    return _formatar_notificacao_publica(
        _anexar_estado(
            get_supabase_client(),
            [notificacao],
            usuario_id=_usuario_id_para_estado(usuario, usuario_id),
        )[0]
    )


def buscar_notificacao(notificacao_id: UUID) -> dict:
    client = get_supabase_client()
    linha = first_or_none(
        client.table("notificacoes")
        .select("*")
        .eq("id", str(notificacao_id))
        .limit(1)
        .execute()
        .data
    )
    if not linha:
        raise NotFoundError("Notificacao", str(notificacao_id))
    return _anexar_midias(client, [linha])[0]


def criar_notificacao(requisicao: RequisicaoCriarNotificacao, usuario: dict) -> dict:
    client = get_supabase_client()
    status = "publicada" if requisicao.publicar_agora else "rascunho"
    publicado_em = datetime.now(UTC) if requisicao.publicar_agora else None
    expira_em = _resolver_expiracao(
        publicado_em=publicado_em,
        expira_em=requisicao.expira_em,
        expira_em_dias=requisicao.expira_em_dias,
    )
    _validar_alvo_notificacao(
        publico=requisicao.publico,
        planos_alvo=requisicao.planos_alvo,
        usuario_alvo_id=requisicao.usuario_alvo_id,
    )
    linha = (
        client.table("notificacoes")
        .insert(
            to_db_payload(
                {
                    "titulo": requisicao.titulo,
                    "corpo": requisicao.corpo,
                    "publico": requisicao.publico,
                    "planos_alvo": _normalizar_planos_alvo(requisicao.planos_alvo),
                    "usuario_alvo_id": requisicao.usuario_alvo_id,
                    "prioridade": requisicao.prioridade,
                    "status": status,
                    "midias": [midia.model_dump() for midia in requisicao.midias],
                    "metadados": requisicao.metadados,
                    "criado_por_usuario_id": usuario.get("id"),
                    "publicado_em": publicado_em,
                    "expira_em": expira_em,
                    "expira_em_dias": requisicao.expira_em_dias,
                }
            )
        )
        .execute()
        .data[0]
    )
    return _anexar_midias(client, [linha])[0]


def atualizar_notificacao(
    notificacao_id: UUID,
    requisicao: RequisicaoAtualizarNotificacao,
) -> dict:
    atual = buscar_notificacao(notificacao_id)
    dados = requisicao.model_dump(exclude_unset=True)
    if "midias" in dados and dados["midias"] is not None:
        dados["midias"] = [
            midia.model_dump() if hasattr(midia, "model_dump") else midia
            for midia in dados["midias"]
        ]
    dados = _normalizar_payload_de_atualizacao(atual, dados)
    if not dados:
        return buscar_notificacao(notificacao_id)
    client = get_supabase_client()
    linha = (
        client.table("notificacoes")
        .update(_payload_com_nulos(dados))
        .eq("id", str(notificacao_id))
        .execute()
        .data[0]
    )
    return _anexar_midias(client, [linha])[0]


def publicar_notificacao(notificacao_id: UUID) -> dict:
    notificacao = buscar_notificacao(notificacao_id)
    client = get_supabase_client()
    publicado_em = datetime.now(UTC)
    expira_em = _resolver_expiracao(
        publicado_em=publicado_em,
        expira_em=_parse_datetime(notificacao.get("expira_em")),
        expira_em_dias=notificacao.get("expira_em_dias"),
    )
    linha = (
        client.table("notificacoes")
        .update(
            _payload_com_nulos(
                {
                    "status": "publicada",
                    "publicado_em": publicado_em,
                    "expira_em": expira_em,
                }
            )
        )
        .eq("id", str(notificacao_id))
        .execute()
        .data[0]
    )
    return _anexar_midias(client, [linha])[0]


def arquivar_notificacao(notificacao_id: UUID) -> dict:
    buscar_notificacao(notificacao_id)
    client = get_supabase_client()
    linha = (
        client.table("notificacoes")
        .update({"status": "arquivada"})
        .eq("id", str(notificacao_id))
        .execute()
        .data[0]
    )
    return _anexar_midias(client, [linha])[0]


def excluir_notificacao(notificacao_id: UUID) -> None:
    buscar_notificacao(notificacao_id)
    client = get_supabase_client()
    (
        client.table("midias")
        .delete()
        .eq("tipo_entidade", "notificacao")
        .eq("entidade_id", str(notificacao_id))
        .execute()
    )
    client.table("notificacoes").delete().eq("id", str(notificacao_id)).execute()


def limpar_notificacoes_expiradas(*, agora: datetime | None = None) -> dict:
    client = get_supabase_client()
    referencia = agora or datetime.now(UTC)
    expiradas = (
        client.table("notificacoes")
        .select("id")
        .lt("expira_em", referencia.isoformat())
        .execute()
        .data
    )
    ids = [str(linha["id"]) for linha in expiradas]
    if not ids:
        return {"removidas": 0}

    client.table("midias").delete().eq("tipo_entidade", "notificacao").in_(
        "entidade_id", ids
    ).execute()
    client.table("notificacoes").delete().in_("id", ids).execute()
    return {"removidas": len(ids)}


async def anexar_upload(
    notificacao_id: UUID,
    file: UploadFile,
    *,
    descricao: str | None = None,
    texto_alternativo: str | None = None,
) -> dict:
    buscar_notificacao(notificacao_id)
    await servico_de_midia.enviar_midia(
        tipo_entidade="notificacao",
        entidade_id=notificacao_id,
        file=file,
        descricao=descricao,
        texto_alternativo=texto_alternativo,
    )
    return buscar_notificacao(notificacao_id)


def marcar_notificacao_lida(
    notificacao_id: UUID,
    *,
    usuario: dict | None = None,
    usuario_id: UUID | str | None = None,
) -> dict:
    usuario = _normalizar_usuario(usuario, usuario_id)
    buscar_notificacao_publica(notificacao_id, usuario=usuario)
    usuario_id_estado = _usuario_id_para_estado(usuario, usuario_id)
    if not usuario_id_estado:
        return _estado_sem_persistencia(notificacao_id, lida=True)

    client = get_supabase_client()
    try:
        _substituir_linha_estado(
            client,
            tabela="notificacao_visualizacoes",
            notificacao_id=notificacao_id,
            usuario_id=usuario_id_estado,
            campo_data="visualizado_em",
        )
    except Exception as exc:
        if _erro_tabela_ausente(exc):
            return _estado_sem_persistencia(notificacao_id, lida=True)
        raise
    return _buscar_estado_notificacao(client, notificacao_id, usuario_id=usuario_id_estado)


def desmarcar_notificacao_lida(
    notificacao_id: UUID,
    *,
    usuario: dict | None = None,
    usuario_id: UUID | str | None = None,
) -> dict:
    usuario = _normalizar_usuario(usuario, usuario_id)
    buscar_notificacao_publica(notificacao_id, usuario=usuario)
    usuario_id_estado = _usuario_id_para_estado(usuario, usuario_id)
    if not usuario_id_estado:
        return _estado_sem_persistencia(notificacao_id, lida=False)

    client = get_supabase_client()
    try:
        (
            client.table("notificacao_visualizacoes")
            .delete()
            .eq("notificacao_id", str(notificacao_id))
            .eq("usuario_id", str(usuario_id_estado))
            .execute()
        )
    except Exception as exc:
        if _erro_tabela_ausente(exc):
            return _estado_sem_persistencia(notificacao_id, lida=False)
        raise
    return _buscar_estado_notificacao(client, notificacao_id, usuario_id=usuario_id_estado)


def ocultar_notificacao(
    notificacao_id: UUID,
    *,
    usuario: dict | None = None,
    usuario_id: UUID | str | None = None,
) -> dict:
    usuario = _normalizar_usuario(usuario, usuario_id)
    buscar_notificacao_publica(notificacao_id, usuario=usuario)
    usuario_id_estado = _usuario_id_para_estado(usuario, usuario_id)
    if not usuario_id_estado:
        return _estado_sem_persistencia(notificacao_id, oculta=True)

    client = get_supabase_client()
    try:
        _substituir_linha_estado(
            client,
            tabela="notificacao_ocultacoes",
            notificacao_id=notificacao_id,
            usuario_id=usuario_id_estado,
            campo_data="ocultado_em",
        )
    except Exception as exc:
        if _erro_tabela_ausente(exc):
            return _estado_sem_persistencia(notificacao_id, oculta=True)
        raise
    return _buscar_estado_notificacao(client, notificacao_id, usuario_id=usuario_id_estado)


def contar_notificacoes_nao_lidas(
    *,
    usuario: dict | None = None,
    usuario_id: UUID | str | None = None,
) -> dict:
    client = get_supabase_client()
    usuario = _normalizar_usuario(usuario, usuario_id)
    usuario_id_estado = _usuario_id_para_estado(usuario, usuario_id)
    linhas = _consultar_notificacoes_publicas(
        client,
        campos="id,status,publico,planos_alvo,usuario_alvo_id,publicado_em,expira_em",
    )
    linhas = [
        notificacao
        for notificacao in linhas
        if _notificacao_visivel_para_usuario(notificacao, usuario)
    ]
    if not usuario_id_estado:
        return {"total": len(linhas), "persistida": False}

    estados = _buscar_estados(
        client,
        [linha["id"] for linha in linhas],
        usuario_id=usuario_id_estado,
    )
    total = 0
    for linha in linhas:
        estado = estados.get(str(linha["id"]), _estado_padrao(linha["id"]))
        if not estado["lida"] and not estado["oculta"]:
            total += 1
    return {"total": total, "persistida": True}


def _consultar_notificacoes_publicas(
    client: Client,
    *,
    limite: int | None = None,
    campos: str = "*",
) -> list[dict]:
    agora = datetime.now(UTC).isoformat()
    consulta = (
        client.table("notificacoes")
        .select(campos)
        .eq("status", "publicada")
        .lte("publicado_em", agora)
        .or_(f"expira_em.is.null,expira_em.gte.{agora}")
        .order("publicado_em", desc=True)
        .order("criado_em", desc=True)
    )
    if limite:
        consulta = consulta.limit(limite)
    return consulta.execute().data


def _buscar_notificacoes_visiveis_com_estado(
    client: Client,
    *,
    usuario: dict | None,
    usuario_id_estado: UUID | str | None,
) -> list[dict]:
    linhas = _consultar_notificacoes_publicas(
        client,
        campos=(
            "id,titulo,corpo,status,publico,planos_alvo,usuario_alvo_id,"
            "prioridade,midias,metadados,publicado_em,expira_em,criado_em"
        ),
    )
    linhas = [
        notificacao
        for notificacao in linhas
        if _notificacao_visivel_para_usuario(notificacao, usuario)
    ]
    return _anexar_estado(
        client,
        _anexar_midias(client, linhas, enxuto=True),
        usuario_id=usuario_id_estado,
    )


def _limite_consulta_publica(limite: int, usuario: dict | None) -> int:
    if not usuario:
        return limite
    return min(max(limite * 5, limite), 500)


def _anexar_midias(
    client: Client,
    notificacoes: list[dict],
    *,
    enxuto: bool = False,
) -> list[dict]:
    if not notificacoes:
        return []
    ids = [linha["id"] for linha in notificacoes]
    midias_upload = (
        client.table("midias")
        .select("*")
        .eq("tipo_entidade", "notificacao")
        .in_("entidade_id", ids)
        .order("criado_em")
        .execute()
        .data
    )
    por_entidade: dict[str, list[dict]] = {str(entidade_id): [] for entidade_id in ids}
    for midia in midias_upload:
        item_midia = {
            "url": midia.get("url_publica") or "",
            "descricao": midia.get("descricao") or midia.get("texto_alternativo"),
        }
        if not enxuto:
            item_midia = {
                "id": midia["id"],
                "origem": "upload",
                "tipo": _inferir_tipo_midia(midia.get("tipo_conteudo")),
                "url": midia.get("url_publica") or "",
                "tipo_conteudo": midia.get("tipo_conteudo"),
                "descricao": midia.get("descricao"),
                "texto_alternativo": midia.get("texto_alternativo"),
                "thumbnail_url": None,
            }
        por_entidade.setdefault(str(midia["entidade_id"]), []).append(
            item_midia
        )

    for notificacao in notificacoes:
        if enxuto:
            externas = [
                _formatar_midia_publica(midia)
                for midia in (notificacao.get("midias") or [])
            ]
        else:
            externas = [
                {**midia, "id": None, "origem": "externa"}
                for midia in (notificacao.get("midias") or [])
            ]
        notificacao["midias"] = externas + por_entidade.get(str(notificacao["id"]), [])
    return notificacoes


def _formatar_notificacao_publica(notificacao: dict) -> dict:
    lida = notificacao.get("lida", False)
    return {
        "id": notificacao["id"],
        "titulo": notificacao["titulo"],
        "corpo": notificacao["corpo"],
        "prioridade": notificacao.get("prioridade") or "normal",
        "publicado_em": notificacao.get("publicado_em"),
        "expira_em": notificacao.get("expira_em"),
        "criado_em": notificacao.get("criado_em"),
        "lida": lida,
        "lida_em": notificacao.get("lida_em"),
        "nova": not lida,
        "midias": [
            _formatar_midia_publica(midia)
            for midia in (notificacao.get("midias") or [])
        ],
        "metadados": notificacao.get("metadados") or {},
    }


def _formatar_midia_publica(midia: dict) -> dict:
    return {
        "url": midia.get("url") or midia.get("url_publica") or "",
        "descricao": midia.get("descricao") or midia.get("texto_alternativo"),
    }


def _anexar_estado(
    client: Client,
    notificacoes: list[dict],
    *,
    usuario_id: UUID | str | None,
) -> list[dict]:
    if not notificacoes:
        return []

    estados = {}
    if usuario_id:
        estados = _buscar_estados(
            client,
            [notificacao["id"] for notificacao in notificacoes],
            usuario_id=usuario_id,
        )
    for notificacao in notificacoes:
        estado = estados.get(str(notificacao["id"]), _estado_padrao(notificacao["id"]))
        notificacao["lida"] = estado["lida"]
        notificacao["lida_em"] = estado["lida_em"]
        notificacao["oculta"] = estado["oculta"]
        notificacao["oculta_em"] = estado["oculta_em"]
    return notificacoes


def _buscar_estado_notificacao(
    client: Client,
    notificacao_id: UUID,
    *,
    usuario_id: UUID | str,
) -> dict:
    estados = _buscar_estados(client, [notificacao_id], usuario_id=usuario_id)
    estado = estados.get(str(notificacao_id), _estado_padrao(notificacao_id))
    estado["persistida"] = True
    return estado


def _buscar_estados(
    client: Client,
    notificacao_ids: list[UUID | str],
    *,
    usuario_id: UUID | str,
) -> dict[str, dict]:
    ids = [str(notificacao_id) for notificacao_id in notificacao_ids]
    estados = {notificacao_id: _estado_padrao(notificacao_id) for notificacao_id in ids}
    if not ids:
        return estados

    visualizacoes = _executar_lista_opcional(
        client.table("notificacao_visualizacoes")
        .select("notificacao_id,visualizado_em")
        .eq("usuario_id", str(usuario_id))
        .in_("notificacao_id", ids)
    )
    for linha in visualizacoes:
        estado = estados.setdefault(
            str(linha["notificacao_id"]),
            _estado_padrao(linha["notificacao_id"]),
        )
        estado["lida"] = True
        estado["lida_em"] = linha.get("visualizado_em")

    ocultacoes = _executar_lista_opcional(
        client.table("notificacao_ocultacoes")
        .select("notificacao_id,ocultado_em")
        .eq("usuario_id", str(usuario_id))
        .in_("notificacao_id", ids)
    )
    for linha in ocultacoes:
        estado = estados.setdefault(
            str(linha["notificacao_id"]),
            _estado_padrao(linha["notificacao_id"]),
        )
        estado["oculta"] = True
        estado["oculta_em"] = linha.get("ocultado_em")
    return estados


def _substituir_linha_estado(
    client: Client,
    *,
    tabela: str,
    notificacao_id: UUID,
    usuario_id: UUID | str,
    campo_data: str,
) -> None:
    (
        client.table(tabela)
        .delete()
        .eq("notificacao_id", str(notificacao_id))
        .eq("usuario_id", str(usuario_id))
        .execute()
    )
    (
        client.table(tabela)
        .insert(
            {
                "notificacao_id": str(notificacao_id),
                "usuario_id": str(usuario_id),
                campo_data: datetime.now(UTC).isoformat(),
            }
        )
        .execute()
    )


def _estado_padrao(notificacao_id: UUID | str) -> dict:
    return {
        "notificacao_id": str(notificacao_id),
        "lida": False,
        "lida_em": None,
        "oculta": False,
        "oculta_em": None,
        "persistida": True,
    }


def _estado_sem_persistencia(
    notificacao_id: UUID,
    *,
    lida: bool = False,
    oculta: bool = False,
) -> dict:
    estado = _estado_padrao(notificacao_id)
    estado["lida"] = lida
    estado["oculta"] = oculta
    estado["persistida"] = False
    return estado


def _inferir_tipo_midia(tipo_conteudo: str | None) -> str:
    if not tipo_conteudo:
        return "arquivo"
    if tipo_conteudo == "image/gif":
        return "gif"
    if tipo_conteudo.startswith("image/"):
        return "imagem"
    if tipo_conteudo.startswith("video/"):
        return "video"
    return "arquivo"


def _parse_datetime(valor: datetime | str | None) -> datetime | None:
    if not valor:
        return None
    if isinstance(valor, datetime):
        return _datetime_com_timezone(valor)
    return _datetime_com_timezone(datetime.fromisoformat(valor.replace("Z", "+00:00")))


def _datetime_com_timezone(valor: datetime) -> datetime:
    if valor.tzinfo is None:
        return valor.replace(tzinfo=UTC)
    return valor


def _normalizar_usuario(
    usuario: dict | None,
    usuario_id: UUID | str | None = None,
) -> dict | None:
    if usuario:
        return usuario
    if usuario_id:
        return {"id": str(usuario_id)}
    return None


def _usuario_id_para_estado(
    usuario: dict | None,
    usuario_id: UUID | str | None = None,
) -> str | None:
    identificador = usuario_id or (usuario or {}).get("id")
    if not identificador:
        return None
    identificador = str(identificador)
    if identificador == "00000000-0000-0000-0000-000000000001":
        return None
    return identificador


# Sessoes internas (X-API-Key, requisicao sem token): nao representam uma conta
# de verdade e por isso ficam de fora do corte por data de criacao.
_IDS_USUARIO_SENTINELA = frozenset(
    {
        "00000000-0000-0000-0000-000000000000",  # requisicao sem token
        "00000000-0000-0000-0000-000000000001",  # X-API-Key
    }
)


def _notificacao_visivel_para_usuario(notificacao: dict, usuario: dict | None) -> bool:
    if not _notificacao_ativa(notificacao):
        return False

    # Conta nova nao recebe avisos publicados antes de ela existir: notificacoes
    # antigas (inclusive testes) nao aparecem retroativamente para quem chegou depois.
    if not _publicada_apos_criacao_do_usuario(notificacao, usuario):
        return False

    publico = str(notificacao.get("publico") or "todos")
    if publico == "todos":
        return True
    if publico == "admins":
        return bool(usuario and usuario_tem_capacidade(usuario, "notificacoes.admin"))
    if publico == "usuario":
        return bool(usuario and str(notificacao.get("usuario_alvo_id")) == str(usuario.get("id")))
    if publico == "plano":
        plano = str((usuario or {}).get("plano") or "").strip().lower()
        return plano in _normalizar_planos_alvo(notificacao.get("planos_alvo") or [])
    return False


def _publicada_apos_criacao_do_usuario(notificacao: dict, usuario: dict | None) -> bool:
    if not usuario:
        return True
    if str(usuario.get("id") or "") in _IDS_USUARIO_SENTINELA:
        return True
    criado_em = _parse_datetime(usuario.get("criado_em"))
    if not criado_em:
        return True
    publicado_em = _parse_datetime(notificacao.get("publicado_em")) or _parse_datetime(
        notificacao.get("criado_em")
    )
    if not publicado_em:
        return True
    return publicado_em >= criado_em


def _notificacao_ativa(notificacao: dict) -> bool:
    agora = datetime.now(UTC)
    publicado_em = _parse_datetime(notificacao.get("publicado_em"))
    expira_em = _parse_datetime(notificacao.get("expira_em"))
    return bool(
        notificacao.get("status") == "publicada"
        and publicado_em
        and publicado_em <= agora
        and (not expira_em or expira_em >= agora)
    )


def _normalizar_planos_alvo(planos: list[str] | None) -> list[str]:
    vistos = set()
    normalizados = []
    for plano in planos or []:
        valor = str(plano).strip().lower()
        if valor and valor not in vistos:
            vistos.add(valor)
            normalizados.append(valor)
    return normalizados


def _chave_feed(notificacao: dict) -> tuple[int, float]:
    prioridade = str(notificacao.get("prioridade") or "normal")
    prioridade_rank = {"alta": 0, "normal": 1, "baixa": 2}.get(prioridade, 1)
    data = _parse_datetime(notificacao.get("publicado_em") or notificacao.get("criado_em"))
    timestamp = data.timestamp() if data else 0
    return (prioridade_rank, -timestamp)


def _validar_alvo_notificacao(
    *,
    publico: str,
    planos_alvo: list[str] | None,
    usuario_alvo_id: UUID | str | None,
) -> None:
    planos = _normalizar_planos_alvo(planos_alvo)
    if publico == "plano" and not planos:
        raise BadRequestError("Informe ao menos um plano em planos_alvo.")
    if publico != "plano" and planos:
        raise BadRequestError("planos_alvo so pode ser usado com publico plano.")
    if publico == "usuario" and not usuario_alvo_id:
        raise BadRequestError("Informe usuario_alvo_id para notificacao individual.")
    if publico != "usuario" and usuario_alvo_id:
        raise BadRequestError("usuario_alvo_id so pode ser usado com publico usuario.")


def _resolver_expiracao(
    *,
    publicado_em: datetime | None,
    expira_em: datetime | None,
    expira_em_dias: int | None,
) -> datetime | None:
    publicado_em = _parse_datetime(publicado_em)
    expira_em = _parse_datetime(expira_em)
    if expira_em and expira_em_dias:
        raise BadRequestError("Use expira_em ou expira_em_dias, nao os dois.")
    if expira_em_dias and publicado_em:
        return publicado_em + timedelta(days=expira_em_dias)
    if expira_em and publicado_em and expira_em <= publicado_em:
        raise BadRequestError("expira_em precisa ser posterior a publicado_em.")
    return expira_em


def _normalizar_payload_de_atualizacao(atual: dict, dados: dict) -> dict:
    dados = dict(dados)
    publico = dados.get("publico", atual.get("publico", "todos"))

    if "planos_alvo" in dados and dados["planos_alvo"] is not None:
        dados["planos_alvo"] = _normalizar_planos_alvo(dados["planos_alvo"])
    elif publico != "plano":
        dados["planos_alvo"] = []

    if publico != "usuario" and "usuario_alvo_id" not in dados:
        dados["usuario_alvo_id"] = None

    planos = dados.get("planos_alvo", atual.get("planos_alvo") or [])
    usuario_alvo_id = dados.get("usuario_alvo_id", atual.get("usuario_alvo_id"))
    _validar_alvo_notificacao(
        publico=publico,
        planos_alvo=planos,
        usuario_alvo_id=usuario_alvo_id,
    )

    publicado_em = _parse_datetime(dados.get("publicado_em") or atual.get("publicado_em"))
    if "expira_em" in dados:
        dados["expira_em_dias"] = None
        if dados["expira_em"] is not None:
            dados["expira_em"] = _resolver_expiracao(
                publicado_em=publicado_em,
                expira_em=_parse_datetime(dados["expira_em"]),
                expira_em_dias=None,
            )
    elif "expira_em_dias" in dados:
        if dados["expira_em_dias"] is None:
            dados["expira_em"] = None
        elif publicado_em:
            dados["expira_em"] = datetime.now(UTC) + timedelta(days=dados["expira_em_dias"])
        else:
            dados["expira_em"] = None
    return dados


def _payload_com_nulos(dados: dict) -> dict:
    return {key: encode_value(value) for key, value in dados.items()}


# Helpers centralizados em infra; aliases preservam os nomes locais.
_executar_lista_opcional = executar_lista_opcional
_erro_tabela_ausente = tabela_ausente
