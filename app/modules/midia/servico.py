import re
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import BadRequestError
from app.db.supabase import get_supabase_client
from app.shared.db import to_db_payload
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo

TIPOS_DE_ENTIDADE_COM_MIDIA = {
    "produto",
    "local",
    "dia_de_venda",
    "venda",
    "interacao_ia",
    "usuario",
    "sessao_custeio",
    "notificacao",
}


async def enviar_midia(
    *,
    tipo_entidade: str,
    entidade_id: UUID,
    file: UploadFile,
    descricao: str | None = None,
    texto_alternativo: str | None = None,
    definir_como_principal: bool = False,
) -> dict:
    conteudo = await file.read()
    return enviar_midia_em_bytes(
        tipo_entidade=tipo_entidade,
        entidade_id=entidade_id,
        conteudo=conteudo,
        nome_arquivo=file.filename,
        tipo_conteudo=file.content_type,
        descricao=descricao,
        texto_alternativo=texto_alternativo,
        definir_como_principal=definir_como_principal,
    )


def enviar_midia_em_bytes(
    *,
    tipo_entidade: str,
    entidade_id: UUID,
    conteudo: bytes,
    nome_arquivo: str | None,
    tipo_conteudo: str | None = None,
    descricao: str | None = None,
    texto_alternativo: str | None = None,
    definir_como_principal: bool = False,
) -> dict:
    if tipo_entidade not in TIPOS_DE_ENTIDADE_COM_MIDIA:
        raise BadRequestError(
            "Tipo de entidade de midia invalido.",
            {"tipo_entidade": tipo_entidade},
        )

    if not conteudo:
        raise BadRequestError("Arquivo vazio.")

    settings = get_settings()
    client = get_supabase_client()
    bucket = settings.supabase_storage_bucket
    caminho_arquivo = _montar_caminho_do_arquivo(tipo_entidade, entidade_id, nome_arquivo)
    tipo_conteudo_resolvido = tipo_conteudo or "application/octet-stream"

    client.storage.from_(bucket).upload(
        caminho_arquivo,
        conteudo,
        file_options={"content-type": tipo_conteudo_resolvido},
    )
    url_publica = client.storage.from_(bucket).get_public_url(caminho_arquivo)

    midia = (
        client.table("midias")
        .insert(
            to_db_payload(
                {
                    "tipo_entidade": tipo_entidade,
                    "entidade_id": entidade_id,
                    "bucket": bucket,
                    "caminho_arquivo": caminho_arquivo,
                    "url_publica": url_publica,
                    "tipo_conteudo": tipo_conteudo_resolvido,
                    "descricao": descricao,
                    "texto_alternativo": texto_alternativo,
                }
            )
        )
        .execute()
        .data[0]
    )

    if definir_como_principal and tipo_entidade in {"produto", "local"}:
        tabela = "produtos" if tipo_entidade == "produto" else "locais"
        client.table(tabela).update({"url_imagem_principal": url_publica}).eq(
            "id",
            str(entidade_id),
        ).execute()

    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="midia_enviada",
        titulo="Midia enviada",
        tipo_entidade=tipo_entidade,
        entidade_id=entidade_id,
        detalhes={
            "midia_id": midia["id"],
            "caminho_arquivo": caminho_arquivo,
            "tipo_conteudo": tipo_conteudo_resolvido,
            "definir_como_principal": definir_como_principal,
        },
    )
    return midia


def _montar_caminho_do_arquivo(
    tipo_entidade: str,
    entidade_id: UUID,
    nome_arquivo: str | None,
) -> str:
    sufixo = Path(nome_arquivo or "upload").suffix.lower()
    nome_seguro = _normalizar_nome_arquivo(Path(nome_arquivo or "upload").stem)
    return f"{tipo_entidade}/{entidade_id}/{uuid4()}-{nome_seguro}{sufixo}"


def _normalizar_nome_arquivo(valor: str) -> str:
    nome_seguro = re.sub(r"[^a-zA-Z0-9_-]+", "-", valor).strip("-").lower()
    return nome_seguro or "arquivo"
