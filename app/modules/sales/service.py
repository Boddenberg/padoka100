from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from supabase import Client

from app.core.errors import BadRequestError, NotFoundError
from app.db.supabase import get_supabase_client
from app.modules.products import service as products_service
from app.modules.sales.schemas import SaleCreate, SaleVoid
from app.modules.sales_days import service as sales_days_service
from app.shared.db import first_or_none, to_db_payload
from app.shared.timeline import record_timeline_event


def create_sale(payload: SaleCreate) -> dict:
    client = get_supabase_client()
    sales_day = sales_days_service.get_sales_day_row(client, payload.sales_day_id)
    if sales_day["status"] == "closed":
        raise BadRequestError("Nao e possivel registrar venda em um dia fechado.")

    sale_payload = to_db_payload(
        {
            "sales_day_id": payload.sales_day_id,
            "input_type": payload.input_type,
            "ai_interaction_id": payload.ai_interaction_id,
            "raw_text": payload.raw_text,
            "audio_url": payload.audio_url,
            "notes": payload.notes,
            "occurred_at": payload.occurred_at,
            "status": "active",
        }
    )
    sale = client.table("sales").insert(sale_payload).execute().data[0]
    item_rows = [
        _build_sale_item_payload(sale["id"], sales_day, item.product_id, item.quantity)
        for item in payload.items
    ]
    client.table("sale_items").insert(item_rows).execute()

    record_timeline_event(
        client,
        event_type="sale_registered",
        title="Venda registrada",
        entity_type="sale",
        entity_id=sale["id"],
        sales_day_id=payload.sales_day_id,
        details={
            "input_type": payload.input_type,
            "items": [
                {"product_id": str(item.product_id), "quantity": item.quantity}
                for item in payload.items
            ],
        },
    )
    return get_sale(UUID(sale["id"]))


def list_sales(sales_day_id: UUID) -> list[dict]:
    client = get_supabase_client()
    sales_days_service.get_sales_day_row(client, sales_day_id)
    sales = (
        client.table("sales")
        .select("*")
        .eq("sales_day_id", str(sales_day_id))
        .order("occurred_at", desc=True)
        .execute()
        .data
    )
    return _attach_items_to_sales(client, sales)


def get_sale(sale_id: UUID) -> dict:
    client = get_supabase_client()
    sale = _get_sale_row(client, sale_id)
    return _attach_items_to_sales(client, [sale])[0]


def void_sale(sale_id: UUID, payload: SaleVoid) -> dict:
    client = get_supabase_client()
    sale = _get_sale_row(client, sale_id)
    if sale["status"] == "voided":
        return _attach_items_to_sales(client, [sale])[0]

    updated = (
        client.table("sales")
        .update(
            to_db_payload(
                {
                    "status": "voided",
                    "voided_at": datetime.now(timezone.utc),
                    "void_reason": payload.reason,
                }
            )
        )
        .eq("id", str(sale_id))
        .execute()
        .data[0]
    )
    record_timeline_event(
        client,
        event_type="sale_voided",
        title="Venda cancelada",
        entity_type="sale",
        entity_id=sale_id,
        sales_day_id=updated["sales_day_id"],
        details={"reason": payload.reason},
    )
    return _attach_items_to_sales(client, [updated])[0]


def _get_sale_row(client: Client, sale_id: UUID | str) -> dict:
    sale = first_or_none(
        client.table("sales").select("*").eq("id", str(sale_id)).limit(1).execute().data
    )
    if not sale:
        raise NotFoundError("Venda", str(sale_id))
    return sale


def _attach_items_to_sales(client: Client, sales: list[dict]) -> list[dict]:
    sale_ids = [sale["id"] for sale in sales]
    if not sale_ids:
        return []
    items = client.table("sale_items").select("*").in_("sale_id", sale_ids).execute().data
    grouped_items = defaultdict(list)
    for item in items:
        grouped_items[item["sale_id"]].append(item)
    for sale in sales:
        sale["items"] = grouped_items[sale["id"]]
    return sales


def _build_sale_item_payload(sale_id: str, sales_day: dict, product_id: UUID, quantity: int) -> dict:
    business_date = date.fromisoformat(sales_day["business_date"])
    snapshot = products_service.get_product_snapshot(product_id, business_date)
    product = snapshot["product"]
    price = snapshot["price"]
    sale_price = Decimal(str(price["sale_price"]))
    cost_price = Decimal(str(price["cost_price"]))
    return to_db_payload(
        {
            "sale_id": sale_id,
            "sales_day_id": sales_day["id"],
            "product_id": product_id,
            "product_name_snapshot": product["name"],
            "product_image_url_snapshot": product.get("main_image_url"),
            "price_version_id": price["id"],
            "unit_sale_price_snapshot": sale_price,
            "unit_cost_price_snapshot": cost_price,
            "quantity": quantity,
            "total_sale_amount": sale_price * quantity,
            "total_cost_amount": cost_price * quantity,
        }
    )

