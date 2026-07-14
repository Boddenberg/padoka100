import logging
from uuid import UUID

from app.db.supabase import get_supabase_client
from app.infra.supabase.result import coluna_ausente, tabela_ausente
from app.shared.db import first_or_none, to_db_payload

logger = logging.getLogger(__name__)


def listar(
    *,
    item: str | None = None,
    thread_id: UUID | str | None = None,
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
    if thread_id:
        consulta = consulta.eq("thread_id", str(thread_id))
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
    thread_id: UUID | str | None = None,
    interacao_ia_id: UUID | str | None = None,
    midia_id: UUID | str | None = None,
    nome_arquivo: str | None = None,
    url_publica: str | None = None,
    tipo_conteudo: str | None = None,
    resposta_ia: str | None = None,
) -> dict | None:
    payload = to_db_payload(
        {
            "usuario_id": usuario_id,
            "thread_id": thread_id,
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
            "resposta_ia": resposta_ia,
        }
    )
    try:
        return _inserir(payload)
    except Exception as exc:  # noqa: BLE001 - log de troubleshooting nao bloqueia o agente
        payload_fallback = payload
        while True:
            payload_ajustado = _remover_colunas_ausentes(payload_fallback, exc)
            if payload_ajustado == payload_fallback:
                break
            try:
                return _inserir(payload_ajustado)
            except Exception as exc_retry:  # noqa: BLE001
                exc = exc_retry
                payload_fallback = payload_ajustado
        if tabela_ausente(exc):
            logger.warning("Tabela ia_midias_recebidas ainda nao esta disponivel")
            return None
        logger.exception("Falha ao registrar midia recebida por IA")
        return None


def _inserir(payload: dict) -> dict:
    return (
        get_supabase_client()
        .table("ia_midias_recebidas")
        .insert(payload)
        .execute()
        .data[0]
    )


def _remover_colunas_ausentes(payload: dict, exc: Exception) -> dict:
    ajustado = {**payload}
    for coluna in ("resposta_ia", "thread_id"):
        if coluna_ausente(exc, coluna) and coluna in ajustado:
            logger.warning("Coluna ia_midias_recebidas.%s ainda nao esta disponivel", coluna)
            ajustado.pop(coluna, None)
    return ajustado


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
        "thread_id": linha.get("thread_id"),
        "usuario_id": linha.get("usuario_id"),
        "usuario_nome_cadastrado": linha.get("usuario_nome_cadastrado"),
        "data": linha.get("criado_em"),
        "item": linha["item"],
        "interacao_ia_id": linha.get("interacao_ia_id"),
        "midia_id": linha.get("midia_id"),
        "nome_arquivo": linha.get("nome_arquivo"),
        "url_publica": linha.get("url_publica"),
        "tipo_conteudo": linha.get("tipo_conteudo"),
        "resposta_ia": linha.get("resposta_ia"),
    }
