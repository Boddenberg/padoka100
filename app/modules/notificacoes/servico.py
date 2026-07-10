from datetime import UTC, datetime
from uuid import UUID

from fastapi import UploadFile

from app.core.errors import NotFoundError
from app.db.supabase import get_supabase_client
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
    usuario_id: UUID | str | None = None,
    incluir_lidas: bool = True,
    incluir_ocultas: bool = False,
) -> list[dict]:
    client = get_supabase_client()
    linhas = _consultar_notificacoes_publicas(
        client,
        limite=_limite_consulta_estado(limite, usuario_id),
        campos="id,titulo,corpo,midias,publicado_em,criado_em",
    )
    notificacoes = _anexar_estado(
        client,
        _anexar_midias(client, linhas, enxuto=True),
        usuario_id=usuario_id,
    )
    if not incluir_ocultas:
        notificacoes = [notificacao for notificacao in notificacoes if not notificacao["oculta"]]
    if not incluir_lidas:
        notificacoes = [notificacao for notificacao in notificacoes if not notificacao["lida"]]
    return [_formatar_notificacao_publica(notificacao) for notificacao in notificacoes[:limite]]


def listar_notificacoes_admin(*, status: str | None = None, limite: int = 100) -> list[dict]:
    client = get_supabase_client()
    consulta = client.table("notificacoes").select("*").order("criado_em", desc=True).limit(limite)
    if status:
        consulta = consulta.eq("status", status)
    return _anexar_midias(client, consulta.execute().data)


def buscar_notificacao_publica(
    notificacao_id: UUID,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    notificacao = buscar_notificacao(notificacao_id)
    agora = datetime.now(UTC)
    publicado_em = _parse_datetime(notificacao.get("publicado_em"))
    expira_em = _parse_datetime(notificacao.get("expira_em"))
    if (
        notificacao["status"] != "publicada"
        or notificacao["publico"] != "todos"
        or not publicado_em
        or publicado_em > agora
        or (expira_em and expira_em < agora)
    ):
        raise NotFoundError("Notificacao", str(notificacao_id))
    return _formatar_notificacao_publica(
        _anexar_estado(get_supabase_client(), [notificacao], usuario_id=usuario_id)[0]
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
    linha = (
        client.table("notificacoes")
        .insert(
            to_db_payload(
                {
                    "titulo": requisicao.titulo,
                    "corpo": requisicao.corpo,
                    "publico": requisicao.publico,
                    "prioridade": requisicao.prioridade,
                    "status": status,
                    "midias": [midia.model_dump() for midia in requisicao.midias],
                    "metadados": requisicao.metadados,
                    "criado_por_usuario_id": usuario.get("id"),
                    "publicado_em": publicado_em,
                    "expira_em": requisicao.expira_em,
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
    buscar_notificacao(notificacao_id)
    dados = requisicao.model_dump(exclude_unset=True)
    if "midias" in dados and dados["midias"] is not None:
        dados["midias"] = [
            midia.model_dump() if hasattr(midia, "model_dump") else midia
            for midia in dados["midias"]
        ]
    if not dados:
        return buscar_notificacao(notificacao_id)
    client = get_supabase_client()
    linha = (
        client.table("notificacoes")
        .update(to_db_payload(dados))
        .eq("id", str(notificacao_id))
        .execute()
        .data[0]
    )
    return _anexar_midias(client, [linha])[0]


def publicar_notificacao(notificacao_id: UUID) -> dict:
    buscar_notificacao(notificacao_id)
    client = get_supabase_client()
    linha = (
        client.table("notificacoes")
        .update({"status": "publicada", "publicado_em": datetime.now(UTC).isoformat()})
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
    usuario_id: UUID | str | None,
) -> dict:
    buscar_notificacao_publica(notificacao_id)
    if not usuario_id:
        return _estado_sem_persistencia(notificacao_id, lida=True)

    client = get_supabase_client()
    try:
        _substituir_linha_estado(
            client,
            tabela="notificacao_visualizacoes",
            notificacao_id=notificacao_id,
            usuario_id=usuario_id,
            campo_data="visualizado_em",
        )
    except Exception as exc:
        if _erro_tabela_ausente(exc):
            return _estado_sem_persistencia(notificacao_id, lida=True)
        raise
    return _buscar_estado_notificacao(client, notificacao_id, usuario_id=usuario_id)


def desmarcar_notificacao_lida(
    notificacao_id: UUID,
    *,
    usuario_id: UUID | str | None,
) -> dict:
    buscar_notificacao_publica(notificacao_id)
    if not usuario_id:
        return _estado_sem_persistencia(notificacao_id, lida=False)

    client = get_supabase_client()
    try:
        (
            client.table("notificacao_visualizacoes")
            .delete()
            .eq("notificacao_id", str(notificacao_id))
            .eq("usuario_id", str(usuario_id))
            .execute()
        )
    except Exception as exc:
        if _erro_tabela_ausente(exc):
            return _estado_sem_persistencia(notificacao_id, lida=False)
        raise
    return _buscar_estado_notificacao(client, notificacao_id, usuario_id=usuario_id)


def ocultar_notificacao(
    notificacao_id: UUID,
    *,
    usuario_id: UUID | str | None,
) -> dict:
    buscar_notificacao_publica(notificacao_id)
    if not usuario_id:
        return _estado_sem_persistencia(notificacao_id, oculta=True)

    client = get_supabase_client()
    try:
        _substituir_linha_estado(
            client,
            tabela="notificacao_ocultacoes",
            notificacao_id=notificacao_id,
            usuario_id=usuario_id,
            campo_data="ocultado_em",
        )
    except Exception as exc:
        if _erro_tabela_ausente(exc):
            return _estado_sem_persistencia(notificacao_id, oculta=True)
        raise
    return _buscar_estado_notificacao(client, notificacao_id, usuario_id=usuario_id)


def contar_notificacoes_nao_lidas(*, usuario_id: UUID | str | None) -> dict:
    client = get_supabase_client()
    linhas = _consultar_notificacoes_publicas(client, campos="id")
    if not usuario_id:
        return {"total": len(linhas), "persistida": False}

    estados = _buscar_estados(
        client,
        [linha["id"] for linha in linhas],
        usuario_id=usuario_id,
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
        .eq("publico", "todos")
        .lte("publicado_em", agora)
        .or_(f"expira_em.is.null,expira_em.gte.{agora}")
        .order("publicado_em", desc=True)
        .order("criado_em", desc=True)
    )
    if limite:
        consulta = consulta.limit(limite)
    return consulta.execute().data


def _limite_consulta_estado(limite: int, usuario_id: UUID | str | None) -> int:
    if not usuario_id:
        return limite
    return min(max(limite * 3, limite), 300)


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
    return {
        "id": notificacao["id"],
        "titulo": notificacao["titulo"],
        "corpo": notificacao["corpo"],
        "publicado_em": notificacao.get("publicado_em"),
        "criado_em": notificacao.get("criado_em"),
        "lida": notificacao.get("lida", False),
        "lida_em": notificacao.get("lida_em"),
        "midias": [
            _formatar_midia_publica(midia)
            for midia in (notificacao.get("midias") or [])
        ],
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


def _parse_datetime(valor: str | None) -> datetime | None:
    if not valor:
        return None
    return datetime.fromisoformat(valor.replace("Z", "+00:00"))


def _executar_lista_opcional(consulta) -> list[dict]:
    try:
        return consulta.execute().data
    except Exception as exc:
        if _erro_tabela_ausente(exc):
            return []
        raise


def _erro_tabela_ausente(exc: Exception) -> bool:
    mensagem = str(exc)
    return "PGRST205" in mensagem and "Could not find the table" in mensagem
