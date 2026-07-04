from fastapi import APIRouter

from app.modules.locations.router import router as locations_router
from app.modules.products.router import router as products_router
from app.modules.sales.router import router as sales_router
from app.modules.sales_days.router import router as sales_days_router

api_router = APIRouter()
api_router.include_router(products_router)
api_router.include_router(locations_router)
api_router.include_router(sales_days_router)
api_router.include_router(sales_router)
