from uuid import UUID

from fastapi import APIRouter

from app.modules.locations import service
from app.modules.locations.schemas import LocationCreate, LocationOut, LocationUpdate

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", response_model=list[LocationOut])
def list_locations(active_only: bool = True) -> list[dict]:
    return service.list_locations(active_only=active_only)


@router.post("", response_model=LocationOut, status_code=201)
def create_location(payload: LocationCreate) -> dict:
    return service.create_location(payload)


@router.get("/{location_id}", response_model=LocationOut)
def get_location(location_id: UUID) -> dict:
    return service.get_location(location_id)


@router.patch("/{location_id}", response_model=LocationOut)
def update_location(location_id: UUID, payload: LocationUpdate) -> dict:
    return service.update_location(location_id, payload)

