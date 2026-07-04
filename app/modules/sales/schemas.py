from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.shared.schemas import ApiModel


class SaleItemCreate(ApiModel):
    product_id: UUID
    quantity: int = Field(gt=0)


class SaleCreate(ApiModel):
    sales_day_id: UUID
    items: list[SaleItemCreate] = Field(min_length=1)
    input_type: str = Field(default="manual", pattern="^(manual|audio|ai)$")
    ai_interaction_id: UUID | None = None
    raw_text: str | None = None
    audio_url: str | None = None
    notes: str | None = None
    occurred_at: datetime | None = None


class SaleVoid(ApiModel):
    reason: str | None = None


class SaleItemOut(ApiModel):
    id: UUID
    sale_id: UUID
    sales_day_id: UUID
    product_id: UUID
    product_name_snapshot: str
    product_image_url_snapshot: str | None = None
    price_version_id: UUID | None = None
    unit_sale_price_snapshot: Decimal
    unit_cost_price_snapshot: Decimal
    quantity: int
    total_sale_amount: Decimal
    total_cost_amount: Decimal
    created_at: datetime


class SaleOut(ApiModel):
    id: UUID
    sales_day_id: UUID
    input_type: str
    ai_interaction_id: UUID | None = None
    raw_text: str | None = None
    audio_url: str | None = None
    notes: str | None = None
    status: str
    occurred_at: datetime
    voided_at: datetime | None = None
    void_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[SaleItemOut] = Field(default_factory=list)

