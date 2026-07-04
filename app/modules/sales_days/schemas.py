from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.shared.schemas import ApiModel


class ProductionItemCreate(ApiModel):
    product_id: UUID
    quantity_produced: int = Field(ge=0)
    notes: str | None = None


class ProductionItemOut(ApiModel):
    id: UUID
    sales_day_id: UUID
    product_id: UUID
    product_name_snapshot: str
    product_image_url_snapshot: str | None = None
    price_version_id: UUID | None = None
    unit_sale_price_snapshot: Decimal
    unit_cost_price_snapshot: Decimal
    quantity_produced: int
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class SalesDayCreate(ApiModel):
    business_date: date = Field(default_factory=date.today)
    location_id: UUID | None = None
    location_name: str | None = None
    notes: str | None = None
    production_items: list[ProductionItemCreate] = Field(default_factory=list)


class SalesDayUpdate(ApiModel):
    location_id: UUID | None = None
    location_name: str | None = None
    notes: str | None = None


class SalesDayClose(ApiModel):
    notes: str | None = None


class SalesDayOut(ApiModel):
    id: UUID
    business_date: date
    location_id: UUID | None = None
    location_name_snapshot: str | None = None
    notes: str | None = None
    status: str
    opened_at: datetime
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    production_items: list[ProductionItemOut] = Field(default_factory=list)

