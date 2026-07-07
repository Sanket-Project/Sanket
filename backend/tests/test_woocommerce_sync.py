"""Unit and integration tests for WooCommerce integration."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.config import get_settings
from app.core.crypto import encrypt_secret
from app.models.enums import IndustryCode
from app.models.integration import IntegrationConnection
from app.services.integrations.woocommerce_client import (
    WooCommerceClient,
    normalize_base_url,
)
from app.services.integrations.woocommerce_sync import (
    SALES_SOURCE,
    order_to_sale_rows,
    product_to_row,
    run_woocommerce_sync,
    variation_to_row,
)

SAMPLE_PRODUCT = {
    "id": 101,
    "name": "Standard Widget",
    "slug": "standard-widget",
    "permalink": "https://example.com/product/standard-widget/",
    "type": "simple",
    "status": "publish",
    "price": "19.99",
    "sku": "WIDG-101",
    "manage_stock": True,
    "stock_quantity": 42,
    "categories": [{"id": 1, "name": "Widgets"}],
}

SAMPLE_VARIABLE_PRODUCT = {
    "id": 201,
    "name": "T-Shirt",
    "slug": "t-shirt",
    "permalink": "https://example.com/product/t-shirt/",
    "type": "variable",
    "status": "publish",
    "categories": [{"id": 2, "name": "Apparel"}],
}

SAMPLE_VARIATIONS = [
    {
        "id": 202,
        "sku": "TSHIRT-L",
        "description": "Large T-Shirt",
        "price": "24.99",
        "manage_stock": True,
        "stock_quantity": 15,
        "stock_status": "instock",
    },
    {
        "id": 203,
        "sku": "TSHIRT-M",
        "description": "Medium T-Shirt",
        "price": "22.99",
        "manage_stock": False,
        "stock_quantity": None,
        "stock_status": "instock",
    },
]

SAMPLE_ORDER = {
    "id": 501,
    "number": "501",
    "currency": "USD",
    "date_created_gmt": "2026-06-15T12:00:00",
    "line_items": [
        {"id": 10, "product_id": 101, "variation_id": 0, "quantity": 2, "total": "39.98", "sku": "WIDG-101"},
        {"id": 11, "product_id": 201, "variation_id": 202, "quantity": 1, "total": "24.99", "sku": "TSHIRT-L"},
    ],
}


# ── Mapping Unit Tests ────────────────────────────────────────────────────────
def test_product_to_row_maps_core_fields() -> None:
    row = product_to_row(SAMPLE_PRODUCT, "fashion")
    assert row["external_id"] == "101"
    assert row["name"] == "Standard Widget"
    assert row["brand"] is None
    assert row["category"] == "Widgets"
    assert row["status"] == "active"
    assert row["attributes"]["woocommerce_permalink"] == "https://example.com/product/standard-widget/"


def test_product_to_row_defaults_category_when_blank() -> None:
    row = product_to_row({"id": 1, "name": "Blank", "categories": []}, "fashion")
    assert row["category"] == "Uncategorized"


def test_product_to_row_non_active_status() -> None:
    row = product_to_row({"id": 1, "name": "Draft", "status": "draft"}, "fashion")
    assert row["status"] == "discontinued"


def test_variation_to_row_uses_sku_and_extracts_fields() -> None:
    row = variation_to_row(SAMPLE_VARIATIONS[0], parent_id="201", industry="fashion", currency="USD")
    assert row["sku_code"] == "TSHIRT-L"
    assert row["external_id"] == "202"
    assert row["unit_price"] == 24.99
    assert row["currency"] == "USD"
    assert row["attributes"]["woocommerce_parent_id"] == "201"
    assert row["attributes"]["manage_stock"] is True


def test_variation_to_row_falls_back_to_woocommerce_id_when_sku_blank() -> None:
    row = variation_to_row({"id": 999, "sku": "", "price": "10.00"}, parent_id="201", industry="fashion", currency="EUR")
    assert row["sku_code"] == "woocommerce-999"
    assert row["unit_price"] == 10.0


def test_order_to_sale_rows_resolves_products_and_computes_revenue() -> None:
    sku_a, sku_b = uuid.uuid4(), uuid.uuid4()
    # 101 matches product_id (simple product), 202 matches variation_id
    external_to_sku = {"101": sku_a, "202": sku_b}
    rows = order_to_sale_rows(SAMPLE_ORDER, external_to_sku, "fashion")

    assert len(rows) == 2
    first = rows[0]
    assert first["sku_id"] == sku_a
    assert first["units_sold"] == 2
    assert first["gross_revenue"] == 39.98
    assert first["channel"] == SALES_SOURCE
    assert first["metadata_"]["order_id"] == 501

    second = rows[1]
    assert second["sku_id"] == sku_b
    assert second["units_sold"] == 1
    assert second["gross_revenue"] == 24.99


# ── Client Unit Tests ─────────────────────────────────────────────────────────
def test_normalize_base_url_variants() -> None:
    assert normalize_base_url("example.com") == "https://example.com"
    assert normalize_base_url("http://example.com/") == "http://example.com"
    assert normalize_base_url("  https://my-store.local/shop/  ") == "https://my-store.local/shop"


# ── Database Sync Integration Tests ──────────────────────────────────────────
@pytest_asyncio.fixture
async def db(setup_schema):
    from app.core.database import Database

    get_settings.cache_clear()
    database = Database(get_settings())
    yield database
    await database.close()


@pytest_asyncio.fixture
async def tenant_id(db) -> uuid.UUID:
    tid = uuid.uuid4()
    async with db.session_no_rls() as session:
        await session.execute(
            text(
                """
                INSERT INTO industries (code, display_name, default_horizon_weeks, audit_level)
                VALUES ('fashion', 'Fashion', 26, 'standard')
                ON CONFLICT DO NOTHING
                """
            )
        )
        await session.execute(
            text(
                """
                INSERT INTO tenants (id, slug, display_name, tier, status,
                                     industries, active_industry)
                VALUES (:id, :slug, 'Hub Test', 'enterprise', 'active',
                        ARRAY['fashion']::industry_code[], 'fashion')
                """
            ),
            {"id": str(tid), "slug": f"hub-{tid.hex[:8]}"},
        )
    return tid


@pytest.mark.asyncio
async def test_run_woocommerce_sync_imports_data(db, tenant_id) -> None:
    # 1. Create WooCommerce connection row
    async with db.session_no_rls() as session:
        connection = IntegrationConnection(
            tenant_id=tenant_id,
            provider="woocommerce",
            status="connected",
            shop_domain="https://example.com",
            target_industry=IndustryCode.fashion,
            state={
                "credentials_enc": {
                    "consumer_key": encrypt_secret("ck_mock_key"),
                    "consumer_secret": encrypt_secret("cs_mock_secret"),
                },
                "config": {"base_url": "https://example.com"},
            },
        )
        session.add(connection)
        await session.commit()

    # 2. Mock WooCommerceClient to return sample data
    async def mock_get_products(*args, **kwargs):
        yield SAMPLE_PRODUCT
        yield SAMPLE_VARIABLE_PRODUCT

    async def mock_get_product_variations(self, product_id):
        if product_id == 201:
            return SAMPLE_VARIATIONS
        return []

    async def mock_get_orders(*args, **kwargs):
        yield SAMPLE_ORDER

    async def mock_general_settings(self, path):
        class MockResponse:
            status_code = 200
            def json(self):
                return [{"id": "woocommerce_currency", "value": "USD"}]
        return MockResponse()

    with (
        patch.object(WooCommerceClient, "get_products", mock_get_products),
        patch.object(WooCommerceClient, "get_product_variations", mock_get_product_variations),
        patch.object(WooCommerceClient, "get_orders", mock_get_orders),
        patch.object(WooCommerceClient, "_get", mock_general_settings),
    ):
        stats = await run_woocommerce_sync(
            db=db,
            tenant_id=tenant_id,
            connection=connection,
        )

    # 3. Assert statistics returned
    assert stats["products"] == 2
    # Simple product (1 variant) + Variable product (2 variants) = 3 SKUs
    assert stats["skus"] == 3
    # Inventory items (manage_stock=True): simple product (42) + first variation (15) = 2 inventory levels
    assert stats["inventory_levels"] == 2
    # Order has 2 line items, both SKUs resolved successfully
    assert stats["sales_rows"] == 2
    assert stats["orders"] == 1

    # 4. Assert database persistence
    async with db.session(str(tenant_id)) as session:
        # Check Products
        products = (await session.execute(text("SELECT name, external_id FROM products WHERE tenant_id = :t"), {"t": tenant_id})).all()
        assert len(products) == 2
        assert {p[0] for p in products} == {"Standard Widget", "T-Shirt"}

        # Check SKUs
        skus = (await session.execute(text("SELECT sku_code, unit_price FROM skus WHERE tenant_id = :t"), {"t": tenant_id})).all()
        assert len(skus) == 3
        assert {s[0] for s in skus} == {"WIDG-101", "TSHIRT-L", "TSHIRT-M"}

        # Check Inventory Levels
        inventory = (await session.execute(text("SELECT on_hand_units, location FROM inventory_levels WHERE tenant_id = :t"), {"t": tenant_id})).all()
        assert len(inventory) == 2
        assert {int(i[0]) for i in inventory} == {42, 15}
        assert all(i[1] == "WooCommerce Store" for i in inventory)

        # Check Historical Sales
        sales = (await session.execute(text("SELECT units_sold, gross_revenue FROM historical_sales WHERE tenant_id = :t"), {"t": tenant_id})).all()
        assert len(sales) == 2
        assert {int(s[0]) for s in sales} == {1, 2}
