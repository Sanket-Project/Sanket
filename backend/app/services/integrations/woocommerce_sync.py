"""WooCommerce → SANKET sync: map and upsert products, SKUs, inventory, and orders.

Idempotent sync design matching Shopify:
* Products are upserted keyed on (tenant_id, external_id).
* SKUs are upserted keyed on (tenant_id, sku_code).
* Inventory is upserted keyed on (tenant_id, sku_id, location).
* Orders delete and re-insert the sync window to prevent duplicates.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.crypto import decrypt_secret
from app.models.enums import IndustryCode
from app.models.inventory import InventoryLevel
from app.models.product import Product, Sku
from app.models.sales import HistoricalSale
from app.services.integrations.woocommerce_client import WooCommerceClient

log = structlog.get_logger(__name__)

SALES_SOURCE = "woocommerce"
DEFAULT_ORDER_LOOKBACK_DAYS = 540


# ── Pure mapping helpers ──────────────────────────────────────────────────────
def product_to_row(wp: dict, industry: str) -> dict:
    """Map a WooCommerce product to a `products` row."""
    # Categories parsing
    categories = wp.get("categories")
    category = "Uncategorized"
    if categories and isinstance(categories, list):
        category = (categories[0].get("name") or "Uncategorized").strip()

    status = "active"
    if wp.get("status") != "publish":
        status = "discontinued"

    return {
        "external_id": str(wp["id"]),
        "name": (wp.get("name") or "Untitled product").strip(),
        "brand": None,  # WooCommerce does not support brand out-of-the-box
        "category": category,
        "status": status,
        "attributes": {
            "woocommerce_permalink": wp.get("permalink"),
            "slug": wp.get("slug"),
            "type": wp.get("type"),
        },
    }


def variation_to_row(wv: dict, *, parent_id: str, industry: str, currency: str) -> dict:
    """Map a WooCommerce variation (or simple product) to a `skus` row."""
    vid = str(wv["id"])
    sku_code = (wv.get("sku") or "").strip() or f"woocommerce-{vid}"
    price = wv.get("price")
    return {
        "external_id": vid,
        "sku_code": sku_code,
        "description": (wv.get("description") or None),
        "unit_price": float(price) if (price is not None and price != "") else None,
        "currency": currency,
        "attributes": {
            "woocommerce_parent_id": parent_id,
            "barcode": wv.get("barcode") or None,
            "manage_stock": wv.get("manage_stock"),
            "stock_status": wv.get("stock_status"),
        },
    }


def _parse_woocommerce_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(tz=UTC)
    try:
        # WooCommerce returns date strings like '2016-11-21T16:11:58'
        # Since WooCommerce returns date_created_gmt, we assume UTC
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(tz=UTC)


def order_to_sale_rows(
    order: dict, external_to_sku: dict[str, uuid.UUID], industry: str
) -> list[dict]:
    """Map a WooCommerce order's line items to `historical_sales` rows."""
    sale_time = _parse_woocommerce_dt(order.get("date_created_gmt") or order.get("date_created"))
    rows: list[dict] = []
    order_id = order.get("id")

    for li in order.get("line_items", []):
        # Resolve which SKU code we matched: variation_id (if not 0) or product_id
        var_id = li.get("variation_id")
        prod_id = li.get("product_id")
        ext_id = str(var_id) if var_id and int(var_id) > 0 else str(prod_id)

        sku_id = external_to_sku.get(ext_id)
        if sku_id is None:
            continue

        qty = int(li.get("quantity") or 0)
        if qty <= 0:
            continue

        revenue = float(li.get("total") or 0.0)

        rows.append(
            {
                "sku_id": sku_id,
                "sale_time": sale_time,
                "units_sold": qty,
                "gross_revenue": revenue,
                "channel": SALES_SOURCE,
                "industry": industry,
                "metadata_": {
                    "source": SALES_SOURCE,
                    "order_id": order_id,
                    "order_number": order.get("number"),
                },
            }
        )
    return rows


# ── DB sync helpers ───────────────────────────────────────────────────────────
async def _upsert_products_and_skus(
    session,
    tenant_id: uuid.UUID,
    industry: IndustryCode,
    products: list[dict],
    variations_map: dict[int, list[dict]],
    currency: str,
) -> tuple[int, int, dict[str, uuid.UUID], list[tuple[uuid.UUID, int]]]:
    """Upsert products and variants. Returns (#products, #skus, external_id->sku_id, inventory_levels)."""
    external_to_sku: dict[str, uuid.UUID] = {}
    inventory_items: list[tuple[uuid.UUID, int]] = []
    n_products = 0
    n_skus = 0

    for wp in products:
        prow = product_to_row(wp, industry.value)
        stmt = (
            pg_insert(Product)
            .values(tenant_id=tenant_id, industry=industry, **prow)
            .on_conflict_do_update(
                index_elements=[Product.tenant_id, Product.external_id],
                index_where=Product.external_id.isnot(None),
                set_={
                    "name": prow["name"],
                    "brand": prow["brand"],
                    "category": prow["category"],
                    "status": prow["status"],
                    "attributes": prow["attributes"],
                },
            )
            .returning(Product.id)
        )
        product_id = (await session.execute(stmt)).scalar_one()
        n_products += 1

        is_variable = wp.get("type") == "variable"
        variants = variations_map.get(wp["id"], []) if is_variable else [wp]

        for wv in variants:
            vrow = variation_to_row(
                wv, parent_id=str(wp["id"]), industry=industry.value, currency=currency
            )
            sku_stmt = (
                pg_insert(Sku)
                .values(
                    tenant_id=tenant_id,
                    product_id=product_id,
                    industry=industry,
                    **vrow,
                )
                .on_conflict_do_update(
                    index_elements=[Sku.tenant_id, Sku.sku_code],
                    set_={
                        "product_id": product_id,
                        "external_id": vrow["external_id"],
                        "description": vrow["description"],
                        "unit_price": vrow["unit_price"],
                        "currency": vrow["currency"],
                        "attributes": vrow["attributes"],
                        "is_active": True,
                    },
                )
                .returning(Sku.id)
            )
            sku_id = (await session.execute(sku_stmt)).scalar_one()
            n_skus += 1
            external_to_sku[vrow["external_id"]] = sku_id

            # Inventory mapping (if manage_stock is enabled)
            if wv.get("manage_stock"):
                stock_qty = wv.get("stock_quantity")
                if stock_qty is not None:
                    inventory_items.append((sku_id, int(stock_qty)))

    return n_products, n_skus, external_to_sku, inventory_items


async def _upsert_inventory(
    session,
    tenant_id: uuid.UUID,
    industry: IndustryCode,
    inventory_items: list[tuple[uuid.UUID, int]],
) -> int:
    n = 0
    for sku_id, stock_qty in inventory_items:
        stmt = (
            pg_insert(InventoryLevel)
            .values(
                tenant_id=tenant_id,
                sku_id=sku_id,
                industry=industry,
                location="WooCommerce Store",
                on_hand_units=max(0, stock_qty),
                source=SALES_SOURCE,
                as_of=datetime.now(tz=UTC),
            )
            .on_conflict_do_update(
                constraint="uq_inventory_tenant_sku_loc",
                set_={
                    "on_hand_units": max(0, stock_qty),
                    "source": SALES_SOURCE,
                    "as_of": datetime.now(tz=UTC),
                },
            )
        )
        await session.execute(stmt)
        n += 1
    return n


async def _replace_sales(session, tenant_id: uuid.UUID, sale_rows: list[dict]) -> int:
    """Delete prior WooCommerce-sourced sales for the tenant, then bulk insert."""
    await session.execute(
        delete(HistoricalSale).where(
            HistoricalSale.tenant_id == tenant_id,
            HistoricalSale.metadata_["source"].astext == SALES_SOURCE,
        )
    )
    if not sale_rows:
        return 0
    for row in sale_rows:
        session.add(HistoricalSale(tenant_id=tenant_id, **row))
    return len(sale_rows)


# ── Execution Entrypoint ──────────────────────────────────────────────────────
async def run_woocommerce_sync(
    *,
    db,
    tenant_id: uuid.UUID,
    connection,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Run a full backfill/sync for a WooCommerce connection."""
    # Resolve target industry
    industry = (
        connection.target_industry.value
        if hasattr(connection.target_industry, "value")
        else str(connection.target_industry)
    )
    industry_enum = IndustryCode(industry)

    # Decrypt key/secret
    creds_enc = (connection.state or {}).get("credentials_enc", {})
    key_enc = creds_enc.get("consumer_key")
    secret_enc = creds_enc.get("consumer_secret")
    config = (connection.state or {}).get("config", {})
    base_url = config.get("base_url")

    if not key_enc or not secret_enc or not base_url:
        raise ValueError("Missing WooCommerce configuration or credentials")

    consumer_key = decrypt_secret(key_enc)
    consumer_secret = decrypt_secret(secret_enc)

    stats: dict[str, Any] = {"products": 0, "skus": 0, "inventory_levels": 0, "sales_rows": 0}

    async with WooCommerceClient(
        base_url, consumer_key, consumer_secret, http_client=http_client
    ) as client:
        # Determine store currency (fallback to USD)
        currency = "USD"
        try:
            resp = await client._get("settings/general")
            for item in resp.json():
                if item.get("id") == "woocommerce_currency":
                    currency = item.get("value", "USD")
                    break
        except Exception:
            log.warning("woocommerce.sync.currency_fetch_failed", tenant=str(tenant_id))

        # Fetch products & variable variations
        products = []
        variations_map = {}
        async for wp in client.get_products():
            products.append(wp)
            if wp.get("type") == "variable":
                variations = await client.get_product_variations(wp["id"])
                variations_map[wp["id"]] = variations

        # Fetch orders
        since = datetime.now(tz=UTC) - timedelta(days=DEFAULT_ORDER_LOOKBACK_DAYS)
        orders = []
        async for order in client.get_orders(since_date=since):
            orders.append(order)

    # Commit mapping results to DB in a single transaction
    async with db.session(str(tenant_id)) as session:
        n_products, n_skus, external_to_sku, inventory_items = await _upsert_products_and_skus(
            session, tenant_id, industry_enum, products, variations_map, currency
        )
        stats["products"] = n_products
        stats["skus"] = n_skus

        stats["inventory_levels"] = await _upsert_inventory(
            session, tenant_id, industry_enum, inventory_items
        )

        sale_rows = []
        for order in orders:
            sale_rows.extend(order_to_sale_rows(order, external_to_sku, industry_enum))

        stats["sales_rows"] = await _replace_sales(session, tenant_id, sale_rows)
        stats["orders"] = len(orders)

    log.info(
        "woocommerce.sync.completed",
        tenant=str(tenant_id),
        **{k: v for k, v in stats.items() if isinstance(v, int)},
    )
    return stats
