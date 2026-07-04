from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.shared.schemas import ApiModel


class ProductDaySummary(ApiModel):
    product_id: UUID
    product_name: str
    product_image_url: str | None = None
    quantity_produced: int = 0
    quantity_sold: int = 0
    quantity_left: int = 0
    gross_revenue: Decimal = Decimal("0")
    estimated_cost: Decimal = Decimal("0")
    estimated_profit: Decimal = Decimal("0")


class SalesDaySummary(ApiModel):
    sales_day_id: UUID
    business_date: date
    location_name: str | None = None
    status: str
    total_produced: int = 0
    total_sold: int = 0
    total_left: int = 0
    gross_revenue: Decimal = Decimal("0")
    estimated_cost: Decimal = Decimal("0")
    estimated_profit: Decimal = Decimal("0")
    products: list[ProductDaySummary] = Field(default_factory=list)


class PeriodSummary(ApiModel):
    start_date: date
    end_date: date
    total_produced: int = 0
    total_sold: int = 0
    total_left: int = 0
    gross_revenue: Decimal = Decimal("0")
    estimated_cost: Decimal = Decimal("0")
    estimated_profit: Decimal = Decimal("0")
    days: list[SalesDaySummary] = Field(default_factory=list)

