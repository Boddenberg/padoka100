from uuid import UUID

from app.db.supabase import get_supabase_client


def list_timeline_events(
    *,
    sales_day_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    limit: int = 100,
) -> list[dict]:
    client = get_supabase_client()
    query = client.table("timeline_events").select("*").order("created_at", desc=True).limit(limit)
    if sales_day_id:
        query = query.eq("sales_day_id", str(sales_day_id))
    if entity_type:
        query = query.eq("entity_type", entity_type)
    if entity_id:
        query = query.eq("entity_id", str(entity_id))
    return query.execute().data

