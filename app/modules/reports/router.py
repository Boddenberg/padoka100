from datetime import date
from uuid import UUID

from fastapi import APIRouter, Query

from app.modules.reports import service
from app.modules.reports.schemas import PeriodSummary, SalesDaySummary

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/days/{sales_day_id}/summary", response_model=SalesDaySummary)
def get_sales_day_summary(sales_day_id: UUID) -> dict:
    return service.get_sales_day_summary(sales_day_id)


@router.get("/period", response_model=PeriodSummary)
def get_period_summary(
    start_date: date = Query(...),
    end_date: date = Query(...),
) -> dict:
    return service.get_period_summary(start_date, end_date)

