from datetime import date, timedelta
from uuid import UUID

from supabase import Client

from app.core.errors import ConflictError, NotFoundError
from app.db.supabase import get_supabase_client
from app.modules.products.schemas import ProductCreate, ProductUpdate, PriceVersionCreate
from app.shared.db import first_or_none, to_db_payload
from app.shared.slugs import slugify
from app.shared.timeline import record_timeline_event


def list_products(*, active_only: bool = True, price_date: date | None = None) -> list[dict]:
    client = get_supabase_client()
    query = client.table("products").select("*").order("sort_order").order("name")
    if active_only:
        query = query.eq("status", "active")
    products = query.execute().data
    target_date = price_date or date.today()
    return [_attach_current_price(client, product, target_date) for product in products]


def get_product(product_id: UUID, *, price_date: date | None = None) -> dict:
    client = get_supabase_client()
    product = _get_product_row(client, product_id)
    return _attach_current_price(client, product, price_date or date.today())


def create_product(payload: ProductCreate) -> dict:
    client = get_supabase_client()
    product_payload = to_db_payload(
        {
            "name": payload.name,
            "slug": _unique_slug(client, payload.name),
            "description": payload.description,
            "visual_description": payload.visual_description,
            "main_image_url": payload.main_image_url,
            "button_color": payload.button_color,
            "sort_order": payload.sort_order,
            "status": "active",
        }
    )
    product = client.table("products").insert(product_payload).execute().data[0]

    price_payload = to_db_payload(
        {
            "product_id": product["id"],
            "sale_price": payload.sale_price,
            "cost_price": payload.cost_price,
            "effective_from": payload.effective_from,
            "reason": payload.price_reason,
        }
    )
    price = client.table("product_price_versions").insert(price_payload).execute().data[0]

    record_timeline_event(
        client,
        event_type="product_created",
        title=f"Produto criado: {product['name']}",
        entity_type="product",
        entity_id=product["id"],
        details={"initial_price": price},
    )
    product["current_price"] = price
    return product


def update_product(product_id: UUID, payload: ProductUpdate) -> dict:
    client = get_supabase_client()
    product = _get_product_row(client, product_id)
    update_payload = payload.model_dump(exclude_unset=True)
    if "name" in update_payload and update_payload["name"] != product["name"]:
        update_payload["slug"] = _unique_slug(client, update_payload["name"], ignore_id=product_id)
    if not update_payload:
        return _attach_current_price(client, product, date.today())

    updated = (
        client.table("products")
        .update(to_db_payload(update_payload))
        .eq("id", str(product_id))
        .execute()
        .data[0]
    )
    record_timeline_event(
        client,
        event_type="product_updated",
        title=f"Produto atualizado: {updated['name']}",
        entity_type="product",
        entity_id=product_id,
        details={"changed_fields": sorted(update_payload.keys())},
    )
    return _attach_current_price(client, updated, date.today())


def list_price_versions(product_id: UUID) -> list[dict]:
    client = get_supabase_client()
    _get_product_row(client, product_id)
    return (
        client.table("product_price_versions")
        .select("*")
        .eq("product_id", str(product_id))
        .order("effective_from", desc=True)
        .execute()
        .data
    )


def create_price_version(product_id: UUID, payload: PriceVersionCreate) -> dict:
    client = get_supabase_client()
    product = _get_product_row(client, product_id)
    existing_versions = (
        client.table("product_price_versions")
        .select("*")
        .eq("product_id", str(product_id))
        .order("effective_from")
        .execute()
        .data
    )
    if any(version["effective_from"] == payload.effective_from.isoformat() for version in existing_versions):
        raise ConflictError(
            "Ja existe um preco cadastrado para esse produto nessa data.",
            {"product_id": str(product_id), "effective_from": payload.effective_from.isoformat()},
        )

    previous = _find_previous_price(existing_versions, payload.effective_from)
    next_version = _find_next_price(existing_versions, payload.effective_from)
    new_effective_to = None
    if next_version:
        new_effective_to = date.fromisoformat(next_version["effective_from"]) - timedelta(days=1)

    if previous and _price_covers_date(previous, payload.effective_from):
        previous_effective_to = payload.effective_from - timedelta(days=1)
        (
            client.table("product_price_versions")
            .update(to_db_payload({"effective_to": previous_effective_to}))
            .eq("id", previous["id"])
            .execute()
        )

    price_payload = to_db_payload(
        {
            "product_id": product_id,
            "sale_price": payload.sale_price,
            "cost_price": payload.cost_price,
            "effective_from": payload.effective_from,
            "effective_to": new_effective_to,
            "reason": payload.reason,
        }
    )
    price = client.table("product_price_versions").insert(price_payload).execute().data[0]
    record_timeline_event(
        client,
        event_type="product_price_changed",
        title=f"Preco alterado: {product['name']}",
        entity_type="product",
        entity_id=product_id,
        details={
            "new_price": price,
            "effective_from": payload.effective_from.isoformat(),
            "reason": payload.reason,
        },
    )
    return price


def get_price_as_of(product_id: UUID | str, target_date: date) -> dict:
    client = get_supabase_client()
    return _get_price_as_of(client, product_id, target_date)


def _attach_current_price(client: Client, product: dict, target_date: date) -> dict:
    product["current_price"] = _get_price_as_of(client, product["id"], target_date, required=False)
    return product


def _get_product_row(client: Client, product_id: UUID | str) -> dict:
    product = first_or_none(
        client.table("products").select("*").eq("id", str(product_id)).limit(1).execute().data
    )
    if not product:
        raise NotFoundError("Produto", str(product_id))
    return product


def _get_price_as_of(
    client: Client, product_id: UUID | str, target_date: date, *, required: bool = True
) -> dict | None:
    rows = (
        client.table("product_price_versions")
        .select("*")
        .eq("product_id", str(product_id))
        .lte("effective_from", target_date.isoformat())
        .or_(f"effective_to.is.null,effective_to.gte.{target_date.isoformat()}")
        .order("effective_from", desc=True)
        .limit(1)
        .execute()
        .data
    )
    price = first_or_none(rows)
    if required and not price:
        raise NotFoundError("Preco vigente do produto", str(product_id))
    return price


def _unique_slug(client: Client, name: str, *, ignore_id: UUID | None = None) -> str:
    base_slug = slugify(name)
    candidate = base_slug
    suffix = 2
    while True:
        rows = client.table("products").select("id").eq("slug", candidate).limit(1).execute().data
        existing = first_or_none(rows)
        if not existing or (ignore_id and existing["id"] == str(ignore_id)):
            return candidate
        candidate = f"{base_slug}-{suffix}"
        suffix += 1


def _find_previous_price(versions: list[dict], target_date: date) -> dict | None:
    previous_versions = [
        version for version in versions if date.fromisoformat(version["effective_from"]) < target_date
    ]
    return previous_versions[-1] if previous_versions else None


def _find_next_price(versions: list[dict], target_date: date) -> dict | None:
    next_versions = [
        version for version in versions if date.fromisoformat(version["effective_from"]) > target_date
    ]
    return next_versions[0] if next_versions else None


def _price_covers_date(version: dict, target_date: date) -> bool:
    effective_to = version.get("effective_to")
    return effective_to is None or date.fromisoformat(effective_to) >= target_date

