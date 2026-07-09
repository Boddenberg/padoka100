from uuid import UUID

from app.core.errors import NotFoundError
from app.db.supabase import get_supabase_client
from app.modules.rag.esquemas import RequisicaoCriarDocumentoRag
from app.shared.db import first_or_none, to_db_payload


def criar_documento(requisicao: RequisicaoCriarDocumentoRag, usuario: dict) -> dict:
    client = get_supabase_client()
    documento = (
        client.table("rag_documentos")
        .insert(
            to_db_payload(
                {
                    "tipo": requisicao.tipo,
                    "titulo": requisicao.titulo,
                    "conteudo": requisicao.conteudo,
                    "fonte": requisicao.fonte,
                    "tags": requisicao.tags,
                    "metadados": requisicao.metadados,
                    "status": requisicao.status,
                    "criado_por_usuario_id": usuario.get("id"),
                }
            )
        )
        .execute()
        .data[0]
    )
    trechos = _quebrar_em_trechos(
        requisicao.conteudo,
        tamanho=requisicao.tamanho_trecho,
        sobreposicao=requisicao.sobreposicao,
    )
    if trechos:
        client.table("rag_trechos").insert(
            [
                to_db_payload(
                    {
                        "documento_id": documento["id"],
                        "indice": indice,
                        "conteudo": trecho,
                        "tokens_estimados": max(1, len(trecho) // 4),
                        "metadados": {
                            "titulo_documento": requisicao.titulo,
                            "tipo_documento": requisicao.tipo,
                        },
                    }
                )
                for indice, trecho in enumerate(trechos)
            ]
        ).execute()
    return buscar_documento(UUID(documento["id"]))


def listar_documentos(
    *,
    status: str | None = None,
    tipo: str | None = None,
    limite: int = 100,
) -> list[dict]:
    client = get_supabase_client()
    consulta = (
        client.table("rag_documentos").select("*").order("criado_em", desc=True).limit(limite)
    )
    if status:
        consulta = consulta.eq("status", status)
    if tipo:
        consulta = consulta.eq("tipo", tipo)
    return _anexar_trechos(client, consulta.execute().data)


def buscar_documento(documento_id: UUID) -> dict:
    client = get_supabase_client()
    documento = first_or_none(
        client.table("rag_documentos")
        .select("*")
        .eq("id", str(documento_id))
        .limit(1)
        .execute()
        .data
    )
    if not documento:
        raise NotFoundError("Documento RAG", str(documento_id))
    return _anexar_trechos(client, [documento])[0]


def _anexar_trechos(client, documentos: list[dict]) -> list[dict]:
    if not documentos:
        return []
    ids = [documento["id"] for documento in documentos]
    trechos = (
        client.table("rag_trechos")
        .select("id,documento_id,indice,conteudo,tokens_estimados,metadados,embedding_model,criado_em")
        .in_("documento_id", ids)
        .order("indice")
        .execute()
        .data
    )
    por_documento: dict[str, list[dict]] = {str(documento_id): [] for documento_id in ids}
    for trecho in trechos:
        por_documento.setdefault(str(trecho["documento_id"]), []).append(trecho)
    for documento in documentos:
        documento["trechos"] = por_documento.get(str(documento["id"]), [])
    return documentos


def _quebrar_em_trechos(texto: str, *, tamanho: int, sobreposicao: int) -> list[str]:
    texto_limpo = " ".join(texto.split())
    if not texto_limpo:
        return []
    if len(texto_limpo) <= tamanho:
        return [texto_limpo]

    trechos: list[str] = []
    inicio = 0
    while inicio < len(texto_limpo):
        fim = min(len(texto_limpo), inicio + tamanho)
        if fim < len(texto_limpo):
            ponto = texto_limpo.rfind(". ", inicio + int(tamanho * 0.55), fim)
            if ponto != -1:
                fim = ponto + 1
        trecho = texto_limpo[inicio:fim].strip()
        if trecho:
            trechos.append(trecho)
        if fim >= len(texto_limpo):
            break
        inicio = max(0, fim - sobreposicao)
    return trechos
