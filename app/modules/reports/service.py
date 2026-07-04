from datetime import date
from decimal import Decimal
from uuid import UUID

from app.db.supabase import get_supabase_client
from app.modules.sales_days import service as sales_days_service


def get_sales_day_summary(sales_day_id: UUID) -> dict:
    client = get_supabase_client()
    sales_day = sales_days_service.get_sales_day_row(client, sales_day_id)
    production_items = (
        client.table("production_items")
        .select("*")
        .eq("sales_day_id", str(sales_day_id))
        .execute()
        .data
    )
    active_sales = (
        client.table("sales")
        .select("id")
        .eq("sales_day_id", str(sales_day_id))
        .eq("status", "active")
        .execute()
        .data
    )
    sale_ids = [sale["id"] for sale in active_sales]
    sale_items = []
    if sale_ids:
        sale_items = client.table("sale_items").select("*").in_("sale_id", sale_ids).execute().data

    products = _build_product_summaries(production_items, sale_items)
    totals = _sum_products(products)
    return {
        "sales_day_id": sales_day["id"],
        "business_date": sales_day["business_date"],
        "location_name": sales_day.get("location_name_snapshot"),
        "status": sales_day["status"],
        **totals,
        "products": products,
    }


def get_period_summary(start_date: date, end_date: date) -> dict:
    client = get_supabase_client()
    days = (
        client.table("sales_days")
        .select("id")
        .gte("business_date", start_date.isoformat())
        .lte("business_date", end_date.isoformat())
        .order("business_date")
        .execute()
        .data
    )
    day_summaries = [get_sales_day_summary(UUID(day["id"])) for day in days]
    totals = _sum_days(day_summaries)
    return {
        "start_date": start_date,
        "end_date": end_date,
        **totals,
        "days": day_summaries,
    }


def _build_product_summaries(production_items: list[dict], sale_items: list[dict]) -> list[dict]:
    summaries: dict[str, dict] = {}

    for item in production_items:
        product_id = item["product_id"]
        summaries[product_id] = {
            "product_id": product_id,
            "product_name": item["product_name_snapshot"],
            "product_image_url": item.get("product_image_url_snapshot"),
            "quantity_produced": item["quantity_produced"],
            "quantity_sold": 0,
            "quantity_left": item["quantity_produced"],
            "gross_revenue": Decimal("0"),
            "estimated_cost": Decimal("0"),
            "estimated_profit": Decimal("0"),
        }

    for item in sale_items:
        product_id = item["product_id"]
        if product_id not in summaries:
            summaries[product_id] = {
                "product_id": product_id,
                "product_name": item["product_name_snapshot"],
                "product_image_url": item.get("product_image_url_snapshot"),
                "quantity_produced": 0,
                "quantity_sold": 0,
                "quantity_left": 0,
                "gross_revenue": Decimal("0"),
                "estimated_cost": Decimal("0"),
                "estimated_profit": Decimal("0"),
            }
        summary = summaries[product_id]
        summary["quantity_sold"] += item["quantity"]
        summary["gross_revenue"] += Decimal(str(item["total_sale_amount"]))
        summary["estimated_cost"] += Decimal(str(item["total_cost_amount"]))
        summary["estimated_profit"] = summary["gross_revenue"] - summary["estimated_cost"]
        summary["quantity_left"] = summary["quantity_produced"] - summary["quantity_sold"]

    return sorted(summaries.values(), key=lambda product: product["product_name"])


def _sum_products(products: list[dict]) -> dict:
    return {
        "total_produced": sum(product["quantity_produced"] for product in products),
        "total_sold": sum(product["quantity_sold"] for product in products),
        "total_left": sum(product["quantity_left"] for product in products),
        "gross_revenue": sum((product["gross_revenue"] for product in products), Decimal("0")),
        "estimated_cost": sum((product["estimated_cost"] for product in products), Decimal("0")),
        "estimated_profit": sum((product["estimated_profit"] for product in products), Decimal("0")),
    }


def _sum_days(days: list[dict]) -> dict:
    return {
        "total_produced": sum(day["total_produced"] for day in days),
        "total_sold": sum(day["total_sold"] for day in days),
        "total_left": sum(day["total_left"] for day in days),
        "gross_revenue": sum((day["gross_revenue"] for day in days), Decimal("0")),
        "estimated_cost": sum((day["estimated_cost"] for day in days), Decimal("0")),
        "estimated_profit": sum((day["estimated_profit"] for day in days), Decimal("0")),
    }

