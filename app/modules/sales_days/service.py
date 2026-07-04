from datetime import date, datetime, timezone
from uuid import UUID

from supabase import Client

from app.core.errors import BadRequestError, NotFoundError
from app.db.supabase import get_supabase_client
from app.modules.locations import service as locations_service
from app.modules.products import service as products_service
from app.modules.sales_days.schemas import (
    ProductionItemCreate,
    SalesDayClose,
    SalesDayCreate,
    SalesDayUpdate,
)
from app.shared.db import first_or_none, to_db_payload
from app.shared.timeline import record_timeline_event


def list_sales_days(
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    status: str | None = None,
) -> list[dict]:
    client = get_supabase_client()
    query = client.table("sales_days").select("*").order("business_date", desc=True)
    if start_date:
        query = query.gte("business_date", start_date.isoformat())
    if end_date:
        query = query.lte("business_date", end_date.isoformat())
    if status:
        query = query.eq("status", status)
    days = query.execute().data
    return [_attach_production_items(client, day) for day in days]


def create_sales_day(payload: SalesDayCreate) -> dict:
    client = get_supabase_client()
    location_name_snapshot = payload.location_name
    if payload.location_id:
        location = locations_service.get_location(payload.location_id)
        location_name_snapshot = location["name"]

    day_payload = to_db_payload(
        {
            "business_date": payload.business_date,
            "location_id": payload.location_id,
            "location_name_snapshot": location_name_snapshot,
            "notes": payload.notes,
            "status": "open",
        }
    )
    sales_day = client.table("sales_days").insert(day_payload).execute().data[0]
    record_timeline_event(
        client,
        event_type="sales_day_opened",
        title=f"Dia aberto: {sales_day['business_date']}",
        entity_type="sales_day",
        entity_id=sales_day["id"],
        sales_day_id=sales_day["id"],
        details={"location_name": location_name_snapshot},
    )

    for item in payload.production_items:
        upsert_production_item(UUID(sales_day["id"]), item)

    return get_sales_day(UUID(sales_day["id"]))


def get_current_sales_day(*, business_date: date | None = None) -> dict:
    client = get_supabase_client()
    query = client.table("sales_days").select("*").eq("status", "open").order("opened_at", desc=True)
    if business_date:
        query = query.eq("business_date", business_date.isoformat())
    sales_day = first_or_none(query.limit(1).execute().data)
    if not sales_day:
        raise NotFoundError("Dia de venda aberto", business_date.isoformat() if business_date else "current")
    return _attach_production_items(client, sales_day)


def get_sales_day(sales_day_id: UUID | str) -> dict:
    client = get_supabase_client()
    sales_day = get_sales_day_row(client, sales_day_id)
    return _attach_production_items(client, sales_day)


def get_sales_day_row(client: Client, sales_day_id: UUID | str) -> dict:
    sales_day = first_or_none(
        client.table("sales_days").select("*").eq("id", str(sales_day_id)).limit(1).execute().data
    )
    if not sales_day:
        raise NotFoundError("Dia de venda", str(sales_day_id))
    return sales_day


def update_sales_day(sales_day_id: UUID, payload: SalesDayUpdate) -> dict:
    client = get_supabase_client()
    sales_day = get_sales_day_row(client, sales_day_id)
    if sales_day["status"] == "closed":
        raise BadRequestError("Nao e possivel editar um dia fechado.")

    update_payload = payload.model_dump(exclude_unset=True)
    if payload.location_id:
        location = locations_service.get_location(payload.location_id)
        update_payload["location_name_snapshot"] = location["name"]
    elif payload.location_name is not None:
        update_payload["location_name_snapshot"] = payload.location_name
    update_payload.pop("location_name", None)

    if update_payload:
        sales_day = (
            client.table("sales_days")
            .update(to_db_payload(update_payload))
            .eq("id", str(sales_day_id))
            .execute()
            .data[0]
        )
        record_timeline_event(
            client,
            event_type="sales_day_updated",
            title=f"Dia atualizado: {sales_day['business_date']}",
            entity_type="sales_day",
            entity_id=sales_day_id,
            sales_day_id=sales_day_id,
            details={"changed_fields": sorted(update_payload.keys())},
        )
    return _attach_production_items(client, sales_day)


def upsert_production_item(sales_day_id: UUID, payload: ProductionItemCreate) -> dict:
    client = get_supabase_client()
    sales_day = get_sales_day_row(client, sales_day_id)
    if sales_day["status"] == "closed":
        raise BadRequestError("Nao e possivel alterar a producao de um dia fechado.")

    snapshot = products_service.get_product_snapshot(payload.product_id, date.fromisoformat(sales_day["business_date"]))
    product = snapshot["product"]
    price = snapshot["price"]
    item_payload = to_db_payload(
        {
            "sales_day_id": sales_day_id,
            "product_id": payload.product_id,
            "product_name_snapshot": product["name"],
            "product_image_url_snapshot": product.get("main_image_url"),
            "price_version_id": price["id"],
            "unit_sale_price_snapshot": price["sale_price"],
            "unit_cost_price_snapshot": price["cost_price"],
            "quantity_produced": payload.quantity_produced,
            "notes": payload.notes,
        }
    )

    existing = first_or_none(
        client.table("production_items")
        .select("*")
        .eq("sales_day_id", str(sales_day_id))
        .eq("product_id", str(payload.product_id))
        .limit(1)
        .execute()
        .data
    )
    if existing:
        item = (
            client.table("production_items")
            .update(item_payload)
            .eq("id", existing["id"])
            .execute()
            .data[0]
        )
        event_type = "production_item_updated"
        title = f"Producao atualizada: {product['name']}"
    else:
        item = client.table("production_items").insert(item_payload).execute().data[0]
        event_type = "production_item_added"
        title = f"Producao adicionada: {product['name']}"

    record_timeline_event(
        client,
        event_type=event_type,
        title=title,
        entity_type="production_item",
        entity_id=item["id"],
        sales_day_id=sales_day_id,
        details={
            "product_id": str(payload.product_id),
            "quantity_produced": payload.quantity_produced,
            "unit_sale_price_snapshot": price["sale_price"],
        },
    )
    return item


def close_sales_day(sales_day_id: UUID, payload: SalesDayClose) -> dict:
    client = get_supabase_client()
    sales_day = get_sales_day_row(client, sales_day_id)
    if sales_day["status"] == "closed":
        return _attach_production_items(client, sales_day)

    update_payload = {
        "status": "closed",
        "closed_at": datetime.now(timezone.utc),
    }
    if payload.notes is not None:
        update_payload["notes"] = payload.notes
    closed_day = (
        client.table("sales_days")
        .update(to_db_payload(update_payload))
        .eq("id", str(sales_day_id))
        .execute()
        .data[0]
    )
    record_timeline_event(
        client,
        event_type="sales_day_closed",
        title=f"Dia fechado: {closed_day['business_date']}",
        entity_type="sales_day",
        entity_id=sales_day_id,
        sales_day_id=sales_day_id,
    )
    return _attach_production_items(client, closed_day)


def _attach_production_items(client: Client, sales_day: dict) -> dict:
    items = (
        client.table("production_items")
        .select("*")
        .eq("sales_day_id", sales_day["id"])
        .order("product_name_snapshot")
        .execute()
        .data
    )
    sales_day["production_items"] = items
    return sales_day

