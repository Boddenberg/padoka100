from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PriceSnapshot(ApiModel):
    price_version_id: UUID | None = None
    sale_price: Decimal = Field(ge=0)
    cost_price: Decimal = Field(ge=0)
    currency: str = "BRL"
    effective_from: date
    effective_to: date | None = None


class TimelineEventOut(ApiModel):
    id: UUID
    sales_day_id: UUID | None = None
    entity_type: str
    entity_id: UUID | None = None
    event_type: str
    title: str
    details: dict
    created_at: datetime

