import logging
from uuid import UUID

from app.db.supabase import get_supabase_client
from app.infra.supabase.result import tabela_ausente
from app.shared.db import first_or_none, to_db_payload

logger = logging.getLogger(__name__)


def listar(
    *,
    item: str | None = None,
    usuario_id: UUID | str | None = None,
    limite: int = 100,
) -> list[dict]:
    client = get_supabase_client()
    consulta = (
        client.table("ia_midias_recebidas")
        .select("*")
        .order("criado_em", desc=True)
        .limit(limite)
    )
    if item:
        consulta = consulta.eq("item", item)
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    try:
        linhas = consulta.execute().data
    except Exception as exc:
        if tabela_ausente(exc):
            return []
        raise
    return [_montar_saida(linha) for linha in linhas]


def registrar(
    *,
    item: str,
    usuario_id: UUID | str | None,
    usuario_nome: str | None,
    interacao_ia_id: UUID | str | None = None,
    midia_id: UUID | str | None = None,
    nome_arquivo: str | None = None,
    url_publica: str | None = None,
    tipo_conteudo: str | None = None,
) -> dict | None:
    try:
        return (
            get_supabase_client()
            .table("ia_midias_recebidas")
            .insert(
                to_db_payload(
                    {
                        "usuario_id": usuario_id,
                        "usuario_nome_cadastrado": _resolver_nome_usuario_cadastrado(
                            usuario_id,
                            usuario_nome,
                        ),
                        "item": item,
                        "interacao_ia_id": interacao_ia_id,
                        "midia_id": midia_id,
                        "nome_arquivo": nome_arquivo,
                        "url_publica": url_publica,
                        "tipo_conteudo": tipo_conteudo,
                    }
                )
            )
            .execute()
            .data[0]
        )
    except Exception as exc:  # noqa: BLE001 - log de troubleshooting nao bloqueia o agente
        if tabela_ausente(exc):
            logger.warning("Tabela ia_midias_recebidas ainda nao esta disponivel")
            return None
        logger.exception("Falha ao registrar midia recebida por IA")
        return None


def _resolver_nome_usuario_cadastrado(
    usuario_id: UUID | str | None,
    usuario_nome: str | None,
) -> str | None:
    if usuario_nome:
        return usuario_nome
    if not usuario_id:
        return None
    try:
        usuario = first_or_none(
            get_supabase_client()
            .table("usuarios")
            .select("nome")
            .eq("id", str(usuario_id))
            .limit(1)
            .execute()
            .data
        )
    except Exception:  # noqa: BLE001 - falha de lookup nao deve derrubar o fluxo
        logger.exception("Falha ao buscar nome cadastrado do usuario")
        return None
    if not usuario:
        return None
    return usuario.get("nome")


def _montar_saida(linha: dict) -> dict:
    return {
        "id": linha["id"],
        "usuario_id": linha.get("usuario_id"),
        "usuario_nome_cadastrado": linha.get("usuario_nome_cadastrado"),
        "data": linha.get("criado_em"),
        "item": linha["item"],
        "interacao_ia_id": linha.get("interacao_ia_id"),
        "midia_id": linha.get("midia_id"),
        "nome_arquivo": linha.get("nome_arquivo"),
        "url_publica": linha.get("url_publica"),
        "tipo_conteudo": linha.get("tipo_conteudo"),
    }
