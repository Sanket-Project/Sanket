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


def test_header_map_fashion_retail_sales_columns():
    """Validate that the exact column names from a fashion retail Excel sales ledger
    are resolved to canonical fields by _build_header_map."""
    headers = [
        "Order ID",
        "Order Timestamp",
        "SKU Code",
        "Category",
        "Quantity",
        "Selling Price",
        "Total Revenue",
        "Sales Channel",
    ]
    hmap = fi._build_header_map(headers)
    assert hmap.get("order_id") == "Order ID"
    assert hmap.get("timestamp") == "Order Timestamp"
    assert hmap.get("sku") == "SKU Code"
    assert hmap.get("category") == "Category"
    assert hmap.get("quantity") == "Quantity"
    assert hmap.get("price") == "Selling Price"
    assert hmap.get("revenue") == "Total Revenue"
    assert hmap.get("channel") == "Sales Channel"


def test_header_map_fashion_retail_inventory_columns():
    """Validate that the exact column names from the Warehouse Inventory tab resolve."""
    headers = [
        "SKU Code",
        "Location",
        "Current Stock",
        "Reorder Threshold",
    ]
    hmap = fi._build_header_map(headers)
    assert hmap.get("sku") == "SKU Code"
    assert hmap.get("warehouse") == "Location"
    assert hmap.get("available") == "Current Stock"
    assert hmap.get("reorder_point") == "Reorder Threshold"


def test_header_map_unit_velocity_alias():
    """'Unit Velocity' should resolve to quantity (common in fashion sell-through sheets)."""
    hmap = fi._build_header_map(["SKU Code", "Unit Velocity", "Order Timestamp"])
    assert hmap.get("quantity") == "Unit Velocity"


def test_quantity_column_does_not_pollute_available():
    """A column literally named 'Quantity' in a sales file must map ONLY to the
    'quantity' canonical field, not simultaneously to 'available' (inventory).
    The earlier session had 'quantity' in both sets which caused silent conflicts."""
    hmap = fi._build_header_map(["SKU Code", "Quantity", "Order Date", "Selling Price"])
    assert hmap.get("quantity") == "Quantity", "quantity canonical must map to 'Quantity'"
    assert hmap.get("available") is None, (
        "'available' must NOT be set when the column is called 'Quantity' on a sales sheet "
        "— it was erroneously double-mapped before this fix"
    )


@pytest.mark.parametrize("col_name", [
    "Unit Velocity",
    "Units Velocity",
    "Quantity",
    "Qty",
    "Units",
    "Units Sold",
    "Quantity Sold",
    "Quantity Ordered",
    "Order Qty",
    "Ordered Qty",
    "Sales Qty",
    "Items Sold",
    "Total Units",
    "Number of Units",
    "No. of Units",
    "Units Ordered",
    "Pieces",
    "Pcs",
])
def test_quantity_alias_variants(col_name):
    """Every common fashion/retail column name for quantity must auto-map."""
    hmap = fi._build_header_map(["SKU", col_name, "Order Date"])
    assert hmap.get("quantity") == col_name, (
        f"Column '{col_name}' should resolve to 'quantity' canonical field"
    )


# ── Multi-sheet Excel parsing ─────────────────────────────────────────────────
import io as _stdlib_io  # noqa: E402


def _make_multi_sheet_xlsx() -> bytes:
    """Build an in-memory XLSX with two sheets:
    - Sheet 1 ("Executive Summary"): dashboard KPIs with no canonical headers
    - Sheet 2 ("Sales Ledger"): tabular data with recognized column names
    """
    try:
        from openpyxl import Workbook
    except ImportError:
        pytest.skip("openpyxl not installed")

    wb = Workbook()
    ws1 = wb.worksheets[0]          # wb.active can be None in openpyxl ≥ 3.1
    ws1.title = "Executive Summary"
    ws1.append(["Total Annual Revenue", "Gross Profit Margin", "Network Units On Hand"])
    ws1.append([50000000, 0.38, 12400])

    ws2 = wb.create_sheet("Sales Ledger")
    ws2.append(["Order ID", "Order Timestamp", "SKU Code", "Quantity", "Selling Price"])
    ws2.append(["ORD-001", "2025-07-15", "DRS-001-M", 2, 4999])
    ws2.append(["ORD-002", "2025-07-16", "OUT-002-L", 1, 8499])

    buf = _stdlib_io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_xlsx_picks_data_sheet_over_dashboard():
    """_parse_xlsx must select the Sales Ledger sheet, not the Executive Summary."""
    try:
        content = _make_multi_sheet_xlsx()
    except Exception:
        pytest.skip("openpyxl not installed")

    headers, records = fi.parse_table("workbook.xlsx", content)
    assert "SKU Code" in headers, f"Expected data sheet headers, got: {headers}"
    assert "Order Timestamp" in headers
    assert len(records) == 2
    assert records[0]["SKU Code"] == "DRS-001-M"


def test_parse_xlsx_single_sheet_still_works():
    """A single-sheet XLSX must be read as before."""
    try:
        from openpyxl import Workbook
    except ImportError:
        pytest.skip("openpyxl not installed")

    wb = Workbook()
    ws = wb.worksheets[0]           # wb.active can be None in openpyxl ≥ 3.1
    ws.title = "Data"
    ws.append(["SKU", "Quantity", "Selling Price", "Order Timestamp"])
    ws.append(["SKU-001", 3, 1200, "2026-06-15"])
    buf = _stdlib_io.BytesIO()
    wb.save(buf)
    content = buf.getvalue()

    headers, records = fi.parse_table("data.xlsx", content)
    assert headers == ["SKU", "Quantity", "Selling Price", "Order Timestamp"]
    assert records[0]["SKU"] == "SKU-001"


# ── Value coercion ───────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1,200", Decimal("1200")), ("$1200.50", Decimal("1200.50")), ("", None), ("abc", None)],
)
def test_to_decimal(raw, expected):
    assert fi._to_decimal(raw) == expected


def test_to_datetime_formats():
    dt_date = fi._to_datetime("2026-06-15")
    assert dt_date is not None
    assert dt_date.date().isoformat() == "2026-06-15"

    dt_dmy = fi._to_datetime("15/06/2026")
    assert dt_dmy is not None
    assert dt_dmy.date().isoformat() == "2026-06-15"

    dt_utc = fi._to_datetime("2026-06-15T14:20:00Z")
    assert dt_utc is not None
    assert dt_utc.hour == 14

    dt_utc_lz = fi._to_datetime("2026-06-15T14:20:00z")
    assert dt_utc_lz is not None
    assert dt_utc_lz.hour == 14

    dt_offset = fi._to_datetime("2026-06-15T14:20:00-05:00")
    assert dt_offset is not None
    assert dt_offset.hour == 19

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
    # "0" is valid observed zero demand since F07; an unreadable value is not.
    hmap = _sales_hmap()
    with pytest.raises(fi.RowError, match="invalid quantity"):
        fi.map_sales_row({"sku": "A", "quantity": "n/a", "timestamp": "2026-06-15"}, hmap)


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


def test_to_decimal_european():
    assert fi._to_decimal("1.234,56") == Decimal("1234.56")
    assert fi._to_decimal("45,99") == Decimal("45.99")
    assert fi._to_decimal("$ 12.345,67 USD") == Decimal("12345.67")
    assert fi._to_decimal("45,99 €") == Decimal("45.99")
    assert fi._to_decimal("1,234.56") == Decimal("1234.56")


def test_to_datetime_extended():
    dt_mon_year = fi._to_datetime("Jul 15, 2026")
    assert dt_mon_year is not None
    assert dt_mon_year.date().isoformat() == "2026-07-15"

    dt_dmy_abbr = fi._to_datetime("15-Jul-2026")
    assert dt_dmy_abbr is not None
    assert dt_dmy_abbr.date().isoformat() == "2026-07-15"

    dt_day_tz = fi._to_datetime("Monday, Jul 15, 2026 EST")
    assert dt_day_tz is not None
    assert dt_day_tz.date().isoformat() == "2026-07-15"

    dt_compact = fi._to_datetime("20260715")
    assert dt_compact is not None
    assert dt_compact.date().isoformat() == "2026-07-15"


def test_map_sales_row_derives_sku_from_name():
    hmap = {"name": "product_name", "quantity": "qty", "timestamp": "date"}
    row = {"product_name": "Premium T-Shirt", "qty": "10", "date": "2026-07-15"}
    out = fi.map_sales_row(row, hmap)
    assert out["_sku_code"].startswith("premium-t-shirt-")
    assert out["units_sold"] == 10
    assert out["sale_time"].date().isoformat() == "2026-07-15"


@pytest.mark.asyncio
async def test_import_rows_custom_mapping():
    from unittest.mock import MagicMock
    db = MagicMock()
    
    with pytest.raises(ValueError, match="Missing mapping for required column"):
        await fi.import_rows(
            db=db,
            tenant_id=MagicMock(),
            industry=MagicMock(),
            kind="sales",
            headers=["a", "b"],
            records=[],
            column_mapping={"sku": "a"}
        )
