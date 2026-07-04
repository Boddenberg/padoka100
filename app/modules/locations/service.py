from uuid import UUID

from app.core.errors import NotFoundError
from app.db.supabase import get_supabase_client
from app.modules.locations.schemas import LocationCreate, LocationUpdate
from app.shared.db import first_or_none, to_db_payload
from app.shared.timeline import record_timeline_event


def list_locations(*, active_only: bool = True) -> list[dict]:
    client = get_supabase_client()
    query = client.table("locations").select("*").order("name")
    if active_only:
        query = query.eq("status", "active")
    return query.execute().data


def get_location(location_id: UUID | str) -> dict:
    client = get_supabase_client()
    location = first_or_none(
        client.table("locations").select("*").eq("id", str(location_id)).limit(1).execute().data
    )
    if not location:
        raise NotFoundError("Local", str(location_id))
    return location


def create_location(payload: LocationCreate) -> dict:
    client = get_supabase_client()
    location = client.table("locations").insert(to_db_payload(payload.model_dump())).execute().data[0]
    record_timeline_event(
        client,
        event_type="location_created",
        title=f"Local criado: {location['name']}",
        entity_type="location",
        entity_id=location["id"],
    )
    return location


def update_location(location_id: UUID, payload: LocationUpdate) -> dict:
    client = get_supabase_client()
    get_location(location_id)
    update_payload = payload.model_dump(exclude_unset=True)
    if not update_payload:
        return get_location(location_id)
    location = (
        client.table("locations")
        .update(to_db_payload(update_payload))
        .eq("id", str(location_id))
        .execute()
        .data[0]
    )
    record_timeline_event(
        client,
        event_type="location_updated",
        title=f"Local atualizado: {location['name']}",
        entity_type="location",
        entity_id=location_id,
        details={"changed_fields": sorted(update_payload.keys())},
    )
    return location

