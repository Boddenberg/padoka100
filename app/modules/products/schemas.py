from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.shared.schemas import ApiModel


class ProductBase(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    visual_description: str | None = None
    main_image_url: str | None = None
    button_color: str | None = None
    sort_order: int = 0


class ProductCreate(ProductBase):
    sale_price: Decimal = Field(ge=0)
    cost_price: Decimal = Field(default=0, ge=0)
    effective_from: date = Field(default_factory=date.today)
    price_reason: str | None = "Preco inicial"


class ProductUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    visual_description: str | None = None
    main_image_url: str | None = None
    button_color: str | None = None
    sort_order: int | None = None
    status: str | None = Field(default=None, pattern="^(active|inactive)$")


class PriceVersionCreate(ApiModel):
    sale_price: Decimal = Field(ge=0)
    cost_price: Decimal = Field(default=0, ge=0)
    effective_from: date = Field(default_factory=date.today)
    reason: str | None = None


class PriceVersionOut(ApiModel):
    id: UUID
    product_id: UUID
    sale_price: Decimal
    cost_price: Decimal
    currency: str
    effective_from: date
    effective_to: date | None = None
    reason: str | None = None
    created_at: datetime


class ProductOut(ProductBase):
    id: UUID
    slug: str | None = None
    status: str
    current_price: PriceVersionOut | None = None
    created_at: datetime
    updated_at: datetime

