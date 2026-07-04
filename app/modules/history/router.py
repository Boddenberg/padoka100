from uuid import UUID

from fastapi import APIRouter, Query

from app.modules.history import service
from app.shared.schemas import TimelineEventOut

router = APIRouter(prefix="/history", tags=["history"])


@router.get("/timeline", response_model=list[TimelineEventOut])
def list_timeline_events(
    sales_day_id: UUID | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    return service.list_timeline_events(
        sales_day_id=sales_day_id,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
    )

