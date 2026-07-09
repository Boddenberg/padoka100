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


def listar_notificacoes_publicas(*, limite: int = 50) -> list[dict]:
    agora = datetime.now(UTC).isoformat()
    client = get_supabase_client()
    linhas = (
        client.table("notificacoes")
        .select("*")
        .eq("status", "publicada")
        .eq("publico", "todos")
        .lte("publicado_em", agora)
        .or_(f"expira_em.is.null,expira_em.gte.{agora}")
        .order("publicado_em", desc=True)
        .order("criado_em", desc=True)
        .limit(limite)
        .execute()
        .data
    )
    return _anexar_midias(client, linhas)


def listar_notificacoes_admin(*, status: str | None = None, limite: int = 100) -> list[dict]:
    client = get_supabase_client()
    consulta = client.table("notificacoes").select("*").order("criado_em", desc=True).limit(limite)
    if status:
        consulta = consulta.eq("status", status)
    return _anexar_midias(client, consulta.execute().data)


def buscar_notificacao_publica(notificacao_id: UUID) -> dict:
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
    return notificacao


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


def _anexar_midias(client: Client, notificacoes: list[dict]) -> list[dict]:
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
        por_entidade.setdefault(str(midia["entidade_id"]), []).append(
            {
                "id": midia["id"],
                "origem": "upload",
                "tipo": _inferir_tipo_midia(midia.get("tipo_conteudo")),
                "url": midia.get("url_publica") or "",
                "tipo_conteudo": midia.get("tipo_conteudo"),
                "descricao": midia.get("descricao"),
                "texto_alternativo": midia.get("texto_alternativo"),
                "thumbnail_url": None,
            }
        )

    for notificacao in notificacoes:
        externas = [
            {**midia, "id": None, "origem": "externa"}
            for midia in (notificacao.get("midias") or [])
        ]
        notificacao["midias"] = externas + por_entidade.get(str(notificacao["id"]), [])
    return notificacoes


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
