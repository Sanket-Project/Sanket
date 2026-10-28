"""V1 Import Frozen Contract Tests.

These tests lock in the documented V1 behavior so that introducing Fashion Retail V2
does not break, silently alter, or re-interpret legacy V1 imports.

Invariants frozen here:
1. V1 Sales:
   - Header aliases match loosely normalized columns.
   - Quantity must be nonnegative integer (0 is valid observed zero demand since F07).
   - Negative quantity (< 0) is strictly rejected with RowError.
   - Legacy combined returns field is accepted (must be nonnegative integer).
   - Negative returns (< 0) is rejected with RowError.
   - Gross revenue = price * quantity; Net revenue = gross - discount.
   - Missing SKU falls back to slugified product name.
2. V1 Inventory:
   - Header aliases map 'available_stock' / 'current_stock' to 'on_hand_units'.
   - Omitted warehouse/location defaults to 'default'.
   - Negative available/reserved/inbound is silently clamped to 0 (legacy behavior).
3. V1 Products:
   - Category defaults to 'Uncategorized' if blank or missing.
   - Name-only rows generate a slugified deterministic SKU code.
4. V1 Replay:
   - Replay identity produces stable keys for duplicate detection.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import pytest

from app.services.integrations import file_import as fi
from app.services import sales_identity as si


# ── V1 Sales Contract Freeze ──────────────────────────────────────────────────

def test_v1_sales_legacy_combined_returns_accepted():
    """In V1, a sales row can carry both units_sold and legacy returns."""
    hmap = fi._build_header_map(["sku", "quantity", "selling_price", "discount", "timestamp", "returns"])
    row = {
        "sku": "LEGACY-001",
        "quantity": "5",
        "selling_price": "1000",
        "discount": "50",
        "timestamp": "2026-06-15T12:00:00Z",
        "returns": "1",
    }
    out = fi.map_sales_row(row, hmap)
    assert out["_sku_code"] == "LEGACY-001"
    assert out["units_sold"] == 5
    assert out["returns"] == 1
    assert out["gross_revenue"] == Decimal("5000")
    assert out["net_revenue"] == Decimal("4950")


def test_v1_sales_rejects_negative_quantity():
    """V1 rejects negative sale quantity."""
    hmap = fi._build_header_map(["sku", "quantity", "selling_price", "timestamp"])
    row = {
        "sku": "LEGACY-001",
        "quantity": "-2",
        "selling_price": "1000",
        "timestamp": "2026-06-15T12:00:00Z",
    }
    with pytest.raises(fi.RowError, match="negative quantity"):
        fi.map_sales_row(row, hmap)


def test_v1_sales_rejects_negative_returns():
    """V1 rejects negative return quantity."""
    hmap = fi._build_header_map(["sku", "quantity", "selling_price", "timestamp", "returns"])
    row = {
        "sku": "LEGACY-001",
        "quantity": "5",
        "selling_price": "1000",
        "timestamp": "2026-06-15T12:00:00Z",
        "returns": "-1",
    }
    with pytest.raises(fi.RowError, match="cannot be negative"):
        fi.map_sales_row(row, hmap)


def test_v1_sales_allows_zero_quantity_as_censored_or_zero_demand():
    """V1 allows quantity=0."""
    hmap = fi._build_header_map(["sku", "quantity", "selling_price", "timestamp"])
    row = {
        "sku": "LEGACY-001",
        "quantity": "0",
        "selling_price": "1000",
        "timestamp": "2026-06-15T12:00:00Z",
    }
    out = fi.map_sales_row(row, hmap)
    assert out["units_sold"] == 0
    assert out["gross_revenue"] == Decimal("0")


def test_v1_sales_slugifies_name_when_sku_is_absent():
    """In V1, if SKU column is absent, a slugified code is generated from product name."""
    hmap = fi._build_header_map(["name", "quantity", "selling_price", "timestamp"])
    row = {
        "name": "Classic Cotton Kurti",
        "quantity": "2",
        "selling_price": "899",
        "timestamp": "2026-06-15T12:00:00Z",
    }
    out = fi.map_sales_row(row, hmap)
    assert out["_sku_code"].startswith("classic-cotton-kurti-")
    assert out["units_sold"] == 2


# ── V1 Inventory Contract Freeze ──────────────────────────────────────────────

def test_v1_inventory_clamps_negative_stock_to_zero():
    """V1 clamps negative available/reserved/inbound stock to Decimal('0')."""
    hmap = fi._build_header_map(["sku", "available_stock", "reserved_stock", "inbound_stock", "warehouse"])
    row = {
        "sku": "LEGACY-001",
        "available_stock": "-15",
        "reserved_stock": "-5",
        "inbound_stock": "-10",
        "warehouse": "WH-NORTH",
    }
    out = fi.map_inventory_row(row, hmap)
    assert out["_sku_code"] == "LEGACY-001"
    assert out["location"] == "WH-NORTH"
    assert out["on_hand_units"] == Decimal("0"), "V1 legacy behavior silently clamps negative stock"
    assert out["reserved_units"] == Decimal("0")
    assert out["inbound_units"] == Decimal("0")


def test_v1_inventory_defaults_location_to_default():
    """V1 defaults location to 'default' if omitted or empty."""
    hmap = fi._build_header_map(["sku", "available_stock"])
    row = {
        "sku": "LEGACY-001",
        "available_stock": "50",
    }
    out = fi.map_inventory_row(row, hmap)
    assert out["location"] == "default"
    assert out["on_hand_units"] == Decimal("50")


# ── V1 Products Contract Freeze ───────────────────────────────────────────────

def test_v1_products_defaults_category_to_uncategorized():
    """V1 defaults missing category to 'Uncategorized'."""
    hmap = fi._build_header_map(["sku", "name"])
    row = {
        "sku": "LEGACY-001",
        "name": "Test Item",
    }
    out = fi.map_product_row(row, hmap)
    assert out["_sku_code"] == "LEGACY-001"
    assert out["name"] == "Test Item"
    assert out["category"] == "Uncategorized"


def test_v1_products_slugifies_name_when_sku_missing():
    """V1 generates a deterministic sku_code when sku is missing."""
    hmap = fi._build_header_map(["name", "brand"])
    row = {
        "name": "Embroidered Tunic",
        "brand": "DemoBrand",
    }
    out = fi.map_product_row(row, hmap)
    assert out["_sku_code"].startswith("embroidered-tunic-")
    assert out["name"] == "Embroidered Tunic"
    assert out["brand"] == "DemoBrand"


# ── V1 Replay Protection Freeze ───────────────────────────────────────────────

def test_v1_sales_identity_transaction_key():
    """V1 sales_identity builds order-based or occurrence-based keys."""
    import uuid
    dummy_sku = uuid.uuid4()
    key = si.base_key(
        source="upload",
        mode="transaction",
        sku_id=dummy_sku,
        sale_time=datetime(2026, 6, 15, 12, 0, tzinfo=UTC),
        channel="pos",
        region="south",
        location="store-1",
        units=2,
        gross=Decimal("2000"),
        net=Decimal("1900"),
        order_id="ORD-100",
        line_id="LINE-1",
    )
    assigned = si.assign_record_keys([key, key], mode="transaction")
    assert assigned[0] == f"upload|o|ORD-100|LINE-1#1"
    assert assigned[1] == f"upload|o|ORD-100|LINE-1#2"
