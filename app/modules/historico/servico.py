from uuid import UUID

from app.db.supabase import get_supabase_client
from app.shared.linha_do_tempo import montar_evento_publico_enxuto


def listar_eventos_da_linha_do_tempo(
    *,
    dia_de_venda_id: UUID | None = None,
    tipo_entidade: str | None = None,
    entidade_id: UUID | None = None,
    limite: int = 100,
) -> list[dict]:
    client = get_supabase_client()
    consulta = (
        client.table("eventos_linha_do_tempo")
        .select("*")
        .order("criado_em", desc=True)
        .limit(limite)
    )
    if dia_de_venda_id:
        consulta = consulta.eq("dia_de_venda_id", str(dia_de_venda_id))
    if tipo_entidade:
        consulta = consulta.eq("tipo_entidade", tipo_entidade)
    if entidade_id:
        consulta = consulta.eq("entidade_id", str(entidade_id))
    return [montar_evento_publico_enxuto(evento) for evento in consulta.execute().data]
