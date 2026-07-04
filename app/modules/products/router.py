from datetime import date
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, UploadFile

from app.modules.media import service as media_service
from app.modules.media.schemas import MediaAssetOut
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


@router.post("/{product_id}/media", response_model=MediaAssetOut, status_code=201)
async def upload_product_media(
    product_id: UUID,
    file: UploadFile = File(...),
    description: str | None = Form(default=None),
    alt_text: str | None = Form(default=None),
    set_as_main: bool = Form(default=True),
) -> dict:
    return await media_service.upload_media(
        owner_type="product",
        owner_id=product_id,
        file=file,
        description=description,
        alt_text=alt_text,
        set_as_main=set_as_main,
    )
