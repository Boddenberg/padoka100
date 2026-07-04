from typing import Any
from uuid import UUID

from supabase import Client

from app.shared.db import to_db_payload


def registrar_evento_na_linha_do_tempo(
    client: Client,
    *,
    tipo_evento: str,
    titulo: str,
    tipo_entidade: str,
    entidade_id: UUID | str | None = None,
    dia_de_venda_id: UUID | str | None = None,
    detalhes: dict[str, Any] | None = None,
) -> None:
    dados = to_db_payload(
        {
            "tipo_evento": tipo_evento,
            "titulo": titulo,
            "tipo_entidade": tipo_entidade,
            "entidade_id": entidade_id,
            "dia_de_venda_id": dia_de_venda_id,
            "detalhes": detalhes or {},
        }
    )
    client.table("eventos_linha_do_tempo").insert(dados).execute()
