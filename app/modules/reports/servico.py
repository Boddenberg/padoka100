import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import UploadFile

from app.core.errors import BadRequestError, NotFoundError
from app.db.supabase import get_supabase_client
from app.infra.supabase.result import tabela_ausente
from app.modules.midia import servico as servico_de_midia
from app.shared.db import first_or_none, to_db_payload
from supabase import Client

logger = logging.getLogger(__name__)

TIPOS_VALIDOS = {"erro", "dificuldade", "sugestao", "recado"}
STATUS_VALIDOS = {"novo", "lido", "resolvido"}


async def criar_report(
    *,
    usuario: dict,
    tipo: str | None,
    mensagem: str | None,
    contexto: str | None = None,
    plataforma: str | None = None,
    app_versao: str | None = None,
    arquivos: list[UploadFile] | None = None,
) -> dict:
    """Registra um report do usuario e anexa os arquivos enviados (se houver)."""
    mensagem_limpa = (mensagem or "").strip() or None
    arquivos = [arquivo for arquivo in (arquivos or []) if arquivo is not None and arquivo.filename]
    if not mensagem_limpa and not arquivos:
        raise BadRequestError("Escreva uma mensagem ou anexe um print/audio para enviar.")

    tipo_normalizado = (tipo or "recado").strip().lower()
    if tipo_normalizado not in TIPOS_VALIDOS:
        tipo_normalizado = "recado"

    client = get_supabase_client()
    usuario_id = usuario.get("id")
    linha = (
        client.table("reports")
        .insert(
            to_db_payload(
                {
                    "usuario_id": usuario_id,
                    "tipo": tipo_normalizado,
                    "mensagem": mensagem_limpa,
                    "contexto": (contexto or "").strip() or None,
                    "plataforma": (plataforma or "").strip() or None,
                    "app_versao": (app_versao or "").strip() or None,
                    "status": "novo",
                }
            )
        )
        .execute()
        .data[0]
    )

    report_id = linha["id"]
    for arquivo in arquivos:
        try:
            await servico_de_midia.enviar_midia(
                tipo_entidade="report",
                entidade_id=report_id,
                file=arquivo,
                usuario_id=usuario_id,
            )
        except Exception:  # noqa: BLE001 - um anexo com problema nao invalida o report
            logger.exception("Falha ao anexar arquivo ao report %s", report_id)

    return _montar_saida_publica(_anexar_midias(client, [linha])[0])


def listar_reports_admin(*, status: str | None = None, limite: int = 100) -> list[dict]:
    client = get_supabase_client()
    consulta = client.table("reports").select("*").order("criado_em", desc=True).limit(limite)
    if status:
        consulta = consulta.eq("status", status)
    try:
        linhas = consulta.execute().data
    except Exception as exc:  # noqa: BLE001
        if tabela_ausente(exc):
            return []
        raise
    linhas = _anexar_usuarios(client, _anexar_midias(client, linhas))
    return [_montar_saida_admin(linha) for linha in linhas]


def atualizar_status_report(report_id: UUID, status: str) -> dict:
    if status not in STATUS_VALIDOS:
        raise BadRequestError("Status invalido.", {"status": status})
    client = get_supabase_client()
    atual = first_or_none(
        client.table("reports").select("id").eq("id", str(report_id)).limit(1).execute().data
    )
    if not atual:
        raise NotFoundError("Report", str(report_id))
    linha = (
        client.table("reports")
        .update(to_db_payload({"status": status, "atualizado_em": datetime.now(UTC)}))
        .eq("id", str(report_id))
        .execute()
        .data[0]
    )
    linha = _anexar_usuarios(client, _anexar_midias(client, [linha]))[0]
    return _montar_saida_admin(linha)


def _anexar_midias(client: Client, linhas: list[dict]) -> list[dict]:
    if not linhas:
        return []
    ids = [str(linha["id"]) for linha in linhas]
    try:
        midias = (
            client.table("midias")
            .select("id,entidade_id,url_publica,tipo_conteudo,criado_em")
            .eq("tipo_entidade", "report")
            .in_("entidade_id", ids)
            .order("criado_em")
            .execute()
            .data
        )
    except Exception:  # noqa: BLE001 - sem anexos nao pode derrubar a listagem
        logger.exception("Falha ao carregar anexos de reports")
        midias = []

    por_entidade: dict[str, list[dict]] = {report_id: [] for report_id in ids}
    for midia in midias:
        por_entidade.setdefault(str(midia["entidade_id"]), []).append(
            {
                "id": midia["id"],
                "url": midia.get("url_publica") or "",
                "tipo": _inferir_tipo_midia(midia.get("tipo_conteudo")),
                "tipo_conteudo": midia.get("tipo_conteudo"),
            }
        )
    for linha in linhas:
        linha["anexos"] = por_entidade.get(str(linha["id"]), [])
    return linhas


def _anexar_usuarios(client: Client, linhas: list[dict]) -> list[dict]:
    if not linhas:
        return []
    ids = {str(linha["usuario_id"]) for linha in linhas if linha.get("usuario_id")}
    mapa: dict[str, dict] = {}
    if ids:
        try:
            usuarios = (
                client.table("usuarios")
                .select("id,nome,email,foto_url")
                .in_("id", list(ids))
                .execute()
                .data
            )
            mapa = {str(usuario["id"]): usuario for usuario in usuarios}
        except Exception:  # noqa: BLE001 - identificar o remetente e desejavel, nao obrigatorio
            logger.exception("Falha ao carregar remetentes dos reports")
    for linha in linhas:
        usuario = mapa.get(str(linha.get("usuario_id"))) or {}
        linha["usuario_nome"] = usuario.get("nome")
        linha["usuario_email"] = usuario.get("email")
        linha["usuario_foto_url"] = usuario.get("foto_url")
    return linhas


def _montar_saida_publica(linha: dict) -> dict:
    return {
        "id": linha["id"],
        "tipo": linha.get("tipo") or "recado",
        "mensagem": linha.get("mensagem"),
        "contexto": linha.get("contexto"),
        "plataforma": linha.get("plataforma"),
        "app_versao": linha.get("app_versao"),
        "status": linha.get("status") or "novo",
        "criado_em": linha.get("criado_em"),
        "anexos": linha.get("anexos") or [],
    }


def _montar_saida_admin(linha: dict) -> dict:
    return {
        **_montar_saida_publica(linha),
        "usuario_id": linha.get("usuario_id"),
        "usuario_nome": linha.get("usuario_nome"),
        "usuario_email": linha.get("usuario_email"),
        "usuario_foto_url": linha.get("usuario_foto_url"),
        "atualizado_em": linha.get("atualizado_em"),
    }


def _inferir_tipo_midia(tipo_conteudo: str | None) -> str:
    if not tipo_conteudo:
        return "arquivo"
    if tipo_conteudo.startswith("image/"):
        return "imagem"
    if tipo_conteudo.startswith("audio/"):
        return "audio"
    if tipo_conteudo.startswith("video/"):
        return "video"
    return "arquivo"
