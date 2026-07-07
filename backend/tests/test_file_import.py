"""Tests for the CSV/Excel → canonical-schema import (pure parsing + mapping)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.services.integrations import file_import as fi


# ── Parsing ──────────────────────────────────────────────────────────────────
def test_parse_csv_basic():
    content = b"SKU,Quantity,Selling Price,Timestamp\nSKU001,5,1200,2026-06-15\n"
    headers, records = fi.parse_table("orders.csv", content)
    assert headers == ["SKU", "Quantity", "Selling Price", "Timestamp"]
    assert records[0]["SKU"] == "SKU001"


def test_parse_csv_skips_blank_rows():
    content = b"sku,qty,date\nA,1,2026-01-02\n,,\nB,2,2026-01-03\n"
    _, records = fi.parse_table("x.csv", content)
    assert len(records) == 2


def test_parse_semicolon_delimited():
    content = b"sku;units;date\nA;3;2026-02-02\n"
    headers, records = fi.parse_table("x.csv", content)
    assert records[0]["units"] == "3"
    assert headers == ["sku", "units", "date"]


def test_unsupported_type_raises():
    with pytest.raises(ValueError, match="Unsupported file type"):
        fi.parse_table("data.pdf", b"x")


# ── Header alias resolution ──────────────────────────────────────────────────
def test_header_map_aliases():
    hmap = fi._build_header_map(["Item Code", "Units Sold", "Unit Price", "Order Date"])
    assert hmap["sku"] == "Item Code"
    assert hmap["quantity"] == "Units Sold"
    assert hmap["price"] == "Unit Price"
    assert hmap["timestamp"] == "Order Date"


# ── Value coercion ───────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1,200", Decimal("1200")), ("$1200.50", Decimal("1200.50")), ("", None), ("abc", None)],
)
def test_to_decimal(raw, expected):
    assert fi._to_decimal(raw) == expected


def test_to_datetime_formats():
    assert fi._to_datetime("2026-06-15").date().isoformat() == "2026-06-15"
    assert fi._to_datetime("15/06/2026").date().isoformat() == "2026-06-15"
    assert fi._to_datetime("2026-06-15T14:20:00Z").hour == 14
    assert fi._to_datetime("garbage") is None


# ── Sales row mapping ────────────────────────────────────────────────────────
def _sales_hmap():
    return fi._build_header_map(["sku", "quantity", "selling_price", "discount", "timestamp"])


def test_map_sales_row_computes_revenue_and_net():
    hmap = _sales_hmap()
    row = {"sku": "SKU001", "quantity": "5", "selling_price": "1200", "discount": "100", "timestamp": "2026-06-15"}
    out = fi.map_sales_row(row, hmap)
    assert out["_sku_code"] == "SKU001"
    assert out["units_sold"] == 5
    assert out["gross_revenue"] == Decimal("6000")
    assert out["net_revenue"] == Decimal("5900")
    assert out["metadata_"]["source"] == "upload"


def test_map_sales_row_rejects_missing_sku():
    hmap = _sales_hmap()
    with pytest.raises(fi.RowError, match="missing SKU"):
        fi.map_sales_row({"sku": "", "quantity": "1", "timestamp": "2026-06-15"}, hmap)


def test_map_sales_row_rejects_bad_quantity():
    hmap = _sales_hmap()
    with pytest.raises(fi.RowError, match="invalid quantity"):
        fi.map_sales_row({"sku": "A", "quantity": "0", "timestamp": "2026-06-15"}, hmap)


def test_map_sales_row_rejects_out_of_window_date():
    hmap = _sales_hmap()
    with pytest.raises(fi.RowError, match="outside the supported range"):
        fi.map_sales_row({"sku": "A", "quantity": "1", "timestamp": "1999-01-01"}, hmap)


# ── Inventory + product row mapping ──────────────────────────────────────────
def test_map_inventory_row():
    hmap = fi._build_header_map(["sku", "available_stock", "reserved_stock", "warehouse_id"])
    out = fi.map_inventory_row(
        {"sku": "SKU001", "available_stock": "250", "reserved_stock": "40", "warehouse_id": "WH01"}, hmap
    )
    assert out["on_hand_units"] == Decimal("250")
    assert out["reserved_units"] == Decimal("40")
    assert out["location"] == "WH01"


def test_map_product_row_defaults_category():
    hmap = fi._build_header_map(["sku", "name", "brand"])
    out = fi.map_product_row({"sku": "SKU001", "name": "Widget", "brand": "Acme"}, hmap)
    assert out["name"] == "Widget"
    assert out["category"] == "Uncategorized"


def test_sale_window_bounds():
    assert fi._MIN_SALE_DATE.year == 2022
    assert fi._max_sale_date().year == datetime.now(tz=UTC).year + 1
