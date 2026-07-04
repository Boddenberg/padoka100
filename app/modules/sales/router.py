from uuid import UUID

from fastapi import APIRouter

from app.modules.sales import service
from app.modules.sales.schemas import SaleCreate, SaleOut, SaleVoid

router = APIRouter(prefix="/sales", tags=["sales"])


@router.post("", response_model=SaleOut, status_code=201)
def create_sale(payload: SaleCreate) -> dict:
    return service.create_sale(payload)


@router.get("/by-day/{sales_day_id}", response_model=list[SaleOut])
def list_sales(sales_day_id: UUID) -> list[dict]:
    return service.list_sales(sales_day_id)


@router.get("/{sale_id}", response_model=SaleOut)
def get_sale(sale_id: UUID) -> dict:
    return service.get_sale(sale_id)


@router.post("/{sale_id}/void", response_model=SaleOut)
def void_sale(sale_id: UUID, payload: SaleVoid) -> dict:
    return service.void_sale(sale_id, payload)
