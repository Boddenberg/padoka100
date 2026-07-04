from typing import Any
from uuid import UUID

from supabase import Client

from app.shared.db import to_db_payload


def record_timeline_event(
    client: Client,
    *,
    event_type: str,
    title: str,
    entity_type: str,
    entity_id: UUID | str | None = None,
    sales_day_id: UUID | str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    payload = to_db_payload(
        {
            "event_type": event_type,
            "title": title,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "sales_day_id": sales_day_id,
            "details": details or {},
        }
    )
    client.table("timeline_events").insert(payload).execute()

