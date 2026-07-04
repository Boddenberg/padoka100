from datetime import date
from uuid import UUID

from fastapi import APIRouter, Query

from app.modules.products import service
from app.modules.products.schemas import (
    PriceVersionCreate,
    PriceVersionOut,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
def list_products(
    active_only: bool = True,
    price_date: date | None = Query(default=None),
) -> list[dict]:
    return service.list_products(active_only=active_only, price_date=price_date)


@router.post("", response_model=ProductOut, status_code=201)
def create_product(payload: ProductCreate) -> dict:
    return service.create_product(payload)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: UUID, price_date: date | None = Query(default=None)) -> dict:
    return service.get_product(product_id, price_date=price_date)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(product_id: UUID, payload: ProductUpdate) -> dict:
    return service.update_product(product_id, payload)


@router.get("/{product_id}/prices", response_model=list[PriceVersionOut])
def list_price_versions(product_id: UUID) -> list[dict]:
    return service.list_price_versions(product_id)


@router.post("/{product_id}/prices", response_model=PriceVersionOut, status_code=201)
def create_price_version(product_id: UUID, payload: PriceVersionCreate) -> dict:
    return service.create_price_version(product_id, payload)

