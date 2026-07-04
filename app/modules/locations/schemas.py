from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.shared.schemas import ApiModel


class LocationCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    address_text: str | None = None
    description: str | None = None
    main_image_url: str | None = None


class LocationUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    address_text: str | None = None
    description: str | None = None
    main_image_url: str | None = None
    status: str | None = Field(default=None, pattern="^(active|inactive)$")


class LocationOut(ApiModel):
    id: UUID
    name: str
    address_text: str | None = None
    description: str | None = None
    main_image_url: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

