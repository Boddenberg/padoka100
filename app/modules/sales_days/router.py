from datetime import date
from uuid import UUID

from fastapi import APIRouter, Query

from app.modules.sales_days import service
from app.modules.sales_days.schemas import (
    ProductionItemCreate,
    ProductionItemOut,
    SalesDayClose,
    SalesDayCreate,
    SalesDayOut,
    SalesDayUpdate,
)

router = APIRouter(prefix="/sales-days", tags=["sales-days"])


@router.get("", response_model=list[SalesDayOut])
def list_sales_days(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(open|closed)$"),
) -> list[dict]:
    return service.list_sales_days(start_date=start_date, end_date=end_date, status=status)


@router.post("", response_model=SalesDayOut, status_code=201)
def create_sales_day(payload: SalesDayCreate) -> dict:
    return service.create_sales_day(payload)


@router.get("/current", response_model=SalesDayOut)
def get_current_sales_day(business_date: date | None = Query(default=None)) -> dict:
    return service.get_current_sales_day(business_date=business_date)


@router.get("/{sales_day_id}", response_model=SalesDayOut)
def get_sales_day(sales_day_id: UUID) -> dict:
    return service.get_sales_day(sales_day_id)


@router.patch("/{sales_day_id}", response_model=SalesDayOut)
def update_sales_day(sales_day_id: UUID, payload: SalesDayUpdate) -> dict:
    return service.update_sales_day(sales_day_id, payload)


@router.post("/{sales_day_id}/production-items", response_model=ProductionItemOut)
def upsert_production_item(sales_day_id: UUID, payload: ProductionItemCreate) -> dict:
    return service.upsert_production_item(sales_day_id, payload)


@router.post("/{sales_day_id}/close", response_model=SalesDayOut)
def close_sales_day(sales_day_id: UUID, payload: SalesDayClose) -> dict:
    return service.close_sales_day(sales_day_id, payload)

