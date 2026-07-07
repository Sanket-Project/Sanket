"""Shopify → SANKET sync: map and upsert products, SKUs, inventory, and orders.

Design notes
------------
* The pure ``*_to_row`` helpers contain all the field mapping and have no DB or
  network dependency, so they're unit-tested against recorded Shopify payloads.
* Upserts are idempotent: products key on ``(tenant_id, external_id)``, SKUs on
  ``(tenant_id, sku_code)``, inventory on ``(tenant_id, sku_id, location)``.
* Orders → ``historical_sales`` can't easily ON CONFLICT (the table is
  range-partitioned), so a re-sync deletes the tenant's prior Shopify-sourced
  rows and re-inserts — keeping the feed idempotent without duplicates.
* The Shopify ``barcode`` is stored in ``attributes`` rather than the ``gtin``
  column to avoid tripping the partial-unique gtin index on dirty catalogs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.crypto import decrypt_secret
from app.models.enums import IndustryCode
from app.models.inventory import InventoryLevel
from app.models.product import Product, Sku
from app.models.sales import HistoricalSale
from app.realtime.events import EVENT_SALE_CREATED, RealtimeEvent
from app.services.integrations.shopify_client import ShopifyClient

log = structlog.get_logger(__name__)

SALES_SOURCE = "shopify"
DEFAULT_ORDER_LOOKBACK_DAYS = 540  # ~18 months of order history


# ── Pure mapping helpers (unit-tested) ──────────────────────────────────────
def product_to_row(sp: dict, industry: str) -> dict:
    """Map a Shopify product to a `products` row (without id/tenant)."""
    return {
        "external_id": str(sp["id"]),
        "name": (sp.get("title") or "Untitled product").strip(),
        "brand": (sp.get("vendor") or None) or None,
        "category": (sp.get("product_type") or "").strip() or "Uncategorized",
        "status": "active" if sp.get("status", "active") == "active" else "discontinued",
        "attributes": {
            "shopify_handle": sp.get("handle"),
            "tags": sp.get("tags"),
        },
    }


def variant_to_row(sv: dict, *, industry: str, currency: str) -> dict:
    """Map a Shopify variant to a `skus` row (without id/tenant/product_id)."""
    vid = str(sv["id"])
    sku_code = (sv.get("sku") or "").strip() or f"shopify-{vid}"
    price = sv.get("price")
    return {
        "external_id": vid,
        "sku_code": sku_code,
        "description": (sv.get("title") or None),
        "unit_price": float(price) if price not in (None, "") else None,  # type: ignore[arg-type]
        "currency": currency,
        "attributes": {
            "shopify_variant_id": vid,
            "barcode": sv.get("barcode") or None,
            "option": sv.get("title"),
            "grams": sv.get("grams"),
            "inventory_item_id": sv.get("inventory_item_id"),
        },
    }


def _parse_shopify_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(tz=UTC)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(tz=UTC)


def order_to_sale_rows(
    order: dict, variant_to_sku: dict[str, uuid.UUID], industry: str
) -> list[dict]:
    """Map a Shopify order's line items to `historical_sales` rows.

    Line items whose variant can't be resolved to a known SKU are skipped.
    """
    sale_time = _parse_shopify_dt(order.get("created_at"))
    rows: list[dict] = []
    for li in order.get("line_items", []):
        vid = li.get("variant_id")
        sku_id = variant_to_sku.get(str(vid)) if vid is not None else None
        if sku_id is None:
            continue
        qty = int(li.get("quantity") or 0)
        if qty <= 0:
            continue
        price = li.get("price")
        gross = float(price) * qty if price not in (None, "") else None
        rows.append(
            {
                "id": uuid.uuid4(),
                "sku_id": sku_id,
                "industry": industry,
                "sale_time": sale_time,
                "channel": SALES_SOURCE,
                "units_sold": qty,
                "gross_revenue": gross,
                "net_revenue": gross,
                "metadata_": {
                    "source": SALES_SOURCE,
                    "order_id": order.get("id"),
                    "line_item_id": li.get("id"),
                },
            }
        )
    return rows


# ── DB orchestration ────────────────────────────────────────────────────────
async def _upsert_products_and_skus(
    session, tenant_id: uuid.UUID, industry: str, products: list[dict], currency: str
) -> tuple[int, int, dict[str, uuid.UUID], dict[str, uuid.UUID]]:
    """Upsert products + variants. Returns (#products, #skus, variant→sku_id,
    inventory_item_id→sku_id)."""
    variant_to_sku: dict[str, uuid.UUID] = {}
    inv_item_to_sku: dict[str, uuid.UUID] = {}
    n_products = 0
    n_skus = 0

    for sp in products:
        prow = product_to_row(sp, industry)
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

        for sv in sp.get("variants", []):
            vrow = variant_to_row(sv, industry=industry, currency=currency)
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
            variant_to_sku[vrow["external_id"]] = sku_id
            inv_item = sv.get("inventory_item_id")
            if inv_item is not None:
                inv_item_to_sku[str(inv_item)] = sku_id

    return n_products, n_skus, variant_to_sku, inv_item_to_sku


async def _upsert_inventory(
    session,
    tenant_id: uuid.UUID,
    industry: str,
    levels: list[dict],
    inv_item_to_sku: dict[str, uuid.UUID],
    location_names: dict[int, str],
) -> int:
    n = 0
    for lvl in levels:
        sku_id = inv_item_to_sku.get(str(lvl.get("inventory_item_id")))
        if sku_id is None:
            continue
        available = lvl.get("available")
        if available is None:
            continue
        location = location_names.get(lvl.get("location_id"), "shopify")  # type: ignore[arg-type]
        stmt = (
            pg_insert(InventoryLevel)
            .values(
                tenant_id=tenant_id,
                sku_id=sku_id,
                industry=industry,
                location=location,
                on_hand_units=max(0, int(available)),
                source=SALES_SOURCE,
                as_of=datetime.now(tz=UTC),
            )
            .on_conflict_do_update(
                constraint="uq_inventory_tenant_sku_loc",
                set_={
                    "on_hand_units": max(0, int(available)),
                    "source": SALES_SOURCE,
                    "as_of": datetime.now(tz=UTC),
                },
            )
        )
        await session.execute(stmt)
        n += 1
    return n


async def _replace_sales(session, tenant_id: uuid.UUID, sale_rows: list[dict]) -> int:
    """Delete prior Shopify-sourced sales for the tenant, then bulk insert."""
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


async def run_shopify_sync(
    *,
    db,
    tenant_id: uuid.UUID,
    connection,
    scope: dict[str, bool],
    http_client: httpx.AsyncClient | None = None,
    api_version: str = "2024-10",
) -> dict[str, Any]:
    """Run a full backfill for the given connection. Returns row-count stats.

    ``scope`` flags: products, inventory, orders.
    """
    token = decrypt_secret(connection.access_token_encrypted)
    industry = (
        connection.target_industry.value
        if hasattr(connection.target_industry, "value")
        else str(connection.target_industry)
    )
    # Use the enum member for ORM inserts so SQLAlchemy binds the PG enum cleanly.
    industry_enum = IndustryCode(industry)
    stats: dict[str, Any] = {"products": 0, "skus": 0, "inventory_levels": 0, "sales_rows": 0}

    async with ShopifyClient(
        connection.shop_domain, token, api_version=api_version, http_client=http_client
    ) as client:
        shop = await client.get_shop()
        currency = shop.get("currency", "USD")
        stats["shop_name"] = shop.get("name")

        want_products = scope.get("products", True)
        want_inventory = scope.get("inventory", True)
        want_orders = scope.get("orders", True)

        # Inventory + orders both need the variant maps, so pull products if any
        # downstream phase is requested.
        need_catalog = want_products or want_inventory or want_orders
        products = [p async for p in client.iter_products()] if need_catalog else []

        locations = await client.get_locations() if want_inventory else []
        location_names = {loc["id"]: loc.get("name", "shopify") for loc in locations}
        levels: list[dict] = []
        if want_inventory and locations:
            levels = [
                lvl async for lvl in client.iter_inventory_levels(list(location_names.keys()))
            ]

        orders: list[dict] = []
        if want_orders:
            since = (datetime.now(tz=UTC) - timedelta(days=DEFAULT_ORDER_LOOKBACK_DAYS)).isoformat()
            orders = [o async for o in client.iter_orders(created_at_min=since)]

    # All network IO is done; now write in a single tenant-scoped transaction.
    async with db.session(str(tenant_id)) as session:
        n_products, n_skus, variant_to_sku, inv_item_to_sku = await _upsert_products_and_skus(
            session, tenant_id, industry_enum, products, currency
        )
        if want_products:
            stats["products"] = n_products
            stats["skus"] = n_skus

        if want_inventory:
            stats["inventory_levels"] = await _upsert_inventory(
                session, tenant_id, industry_enum, levels, inv_item_to_sku, location_names
            )

        if want_orders:
            sale_rows: list[dict] = []
            for order in orders:
                sale_rows.extend(order_to_sale_rows(order, variant_to_sku, industry_enum))
            stats["sales_rows"] = await _replace_sales(session, tenant_id, sale_rows)
            stats["orders"] = len(orders)

    log.info(
        "shopify.sync.completed",
        tenant=str(tenant_id),
        **{k: v for k, v in stats.items() if isinstance(v, int)},
    )
    return stats


# ── Incremental / live ingestion (polling + webhooks) ───────────────────────
async def _load_variant_sku_map(session, tenant_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """Map Shopify variant id (stored as sku.external_id) → sku_id for the
    tenant's already-synced Shopify catalog."""
    rows = await session.execute(
        select(Sku.external_id, Sku.id).where(
            Sku.tenant_id == tenant_id, Sku.external_id.isnot(None)
        )
    )
    return {str(ext): sid for ext, sid in rows.all() if ext}


async def _replace_order_sales(
    session, tenant_id: uuid.UUID, order_id: Any, rows: list[dict]
) -> None:
    """Idempotent per-order upsert: delete prior rows for this order then insert.

    Handles both polling cursor overlap and webhook redelivery without dupes.
    """
    await session.execute(
        delete(HistoricalSale).where(
            HistoricalSale.tenant_id == tenant_id,
            HistoricalSale.metadata_["source"].astext == SALES_SOURCE,
            HistoricalSale.metadata_["order_id"].astext == str(order_id),
        )
    )
    for row in rows:
        session.add(HistoricalSale(tenant_id=tenant_id, **row))


async def _publish_sale_event(realtime, tenant_id: uuid.UUID, industry: str, summary: dict) -> None:
    if realtime is None:
        return
    try:
        await realtime.publish(
            RealtimeEvent(
                type=EVENT_SALE_CREATED,
                tenant_id=tenant_id,
                industry=industry,
                data=summary,
            )
        )
    except Exception as exc:  # noqa: BLE001 - realtime is best-effort
        log.warning("shopify.sale_event.publish_failed", error=str(exc))


async def ingest_orders_incremental(
    *,
    db,
    tenant_id: uuid.UUID,
    connection,
    http_client: httpx.AsyncClient | None = None,
    api_version: str = "2024-10",
    realtime=None,
) -> dict[str, Any]:
    """Pull orders created since the saved cursor, upsert as sales, advance the
    cursor. Used by the 5-minute poller. Returns counts for new sales."""
    if not connection.access_token_encrypted:
        return {"orders": 0, "units": 0, "revenue": 0.0}
    token = decrypt_secret(connection.access_token_encrypted)
    industry = (
        connection.target_industry.value
        if hasattr(connection.target_industry, "value")
        else str(connection.target_industry)
    )
    cursor = (connection.state or {}).get("orders_cursor")

    async with ShopifyClient(
        connection.shop_domain, token, api_version=api_version, http_client=http_client
    ) as client:
        orders = [o async for o in client.iter_orders(created_at_min=cursor)]

    if not orders:
        return {"orders": 0, "units": 0, "revenue": 0.0}

    total_units = 0
    total_revenue = 0.0
    latest = cursor
    async with db.session(str(tenant_id)) as session:
        variant_to_sku = await _load_variant_sku_map(session, tenant_id)
        for order in orders:
            rows = order_to_sale_rows(order, variant_to_sku, industry)
            if rows:
                await _replace_order_sales(session, tenant_id, order.get("id"), rows)
                total_units += sum(r["units_sold"] for r in rows)
                total_revenue += sum((r["gross_revenue"] or 0) for r in rows)
            created = order.get("created_at")
            if created and (latest is None or created > latest):
                latest = created
        # Persist the advanced cursor on the connection row.
        from app.models.integration import IntegrationConnection

        new_state = {**(connection.state or {}), "orders_cursor": latest}
        await session.execute(
            IntegrationConnection.__table__.update()  # type: ignore[attr-defined]
            .where(
                IntegrationConnection.tenant_id == tenant_id,
                IntegrationConnection.provider == connection.provider,
            )
            .values(state=new_state)
        )

    summary = {"orders": len(orders), "units": total_units, "revenue": round(total_revenue, 2)}
    if total_units > 0:
        await _publish_sale_event(realtime, tenant_id, industry, summary)
    log.info("shopify.incremental.done", tenant=str(tenant_id), **summary)
    return summary


async def ingest_single_order(
    *,
    db,
    tenant_id: uuid.UUID,
    connection,
    order_payload: dict,
    realtime=None,
) -> dict[str, Any]:
    """Ingest one order (from a webhook) into sales and emit a live event."""
    industry = (
        connection.target_industry.value
        if hasattr(connection.target_industry, "value")
        else str(connection.target_industry)
    )
    async with db.session(str(tenant_id)) as session:
        variant_to_sku = await _load_variant_sku_map(session, tenant_id)
        rows = order_to_sale_rows(order_payload, variant_to_sku, industry)
        if rows:
            await _replace_order_sales(session, tenant_id, order_payload.get("id"), rows)

    units = sum(r["units_sold"] for r in rows)
    revenue = round(sum((r["gross_revenue"] or 0) for r in rows), 2)
    summary = {"orders": 1, "units": units, "revenue": revenue}
    if units > 0:
        await _publish_sale_event(realtime, tenant_id, industry, summary)
    log.info("shopify.webhook.ingested", tenant=str(tenant_id), **summary)
    return summary
