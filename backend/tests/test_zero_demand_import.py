"""Explicit zero-demand rows, availability and returns (audit F07).

Data Quality tells users to include zero-sales weeks so "no sales" can be told
apart from "no data"; the importer used to reject exactly those rows.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.models.enums import IndustryCode
from app.services import data_quality_audit
from app.services.integrations import file_import as fi


def _hmap(*headers: str) -> dict[str, str]:
    return fi._build_header_map(list(headers))


def test_zero_quantity_is_observed_zero_demand():
    out = fi.map_sales_row(
        {"sku": "A", "quantity": "0", "timestamp": "2026-06-15"}, _hmap("sku", "quantity", "timestamp")
    )
    assert out["units_sold"] == 0


@pytest.mark.parametrize(
    ("qty", "message"),
    [("-3", "negative quantity"), ("abc", "invalid quantity"), ("", "invalid quantity")],
)
def test_negative_or_unreadable_quantity_is_still_rejected(qty, message):
    with pytest.raises(fi.RowError, match=message):
        fi.map_sales_row(
            {"sku": "A", "quantity": qty, "timestamp": "2026-06-15"},
            _hmap("sku", "quantity", "timestamp"),
        )


def test_negative_quantity_points_at_the_returns_column():
    with pytest.raises(fi.RowError, match="returns column"):
        fi.map_sales_row(
            {"sku": "A", "quantity": "-1", "timestamp": "2026-06-15"},
            _hmap("sku", "quantity", "timestamp"),
        )


def test_availability_returns_and_location_are_mapped():
    hmap = _hmap("sku", "qty", "date", "in_stock", "returns", "location")
    out = fi.map_sales_row(
        {"sku": "A", "qty": "0", "date": "2026-06-15", "in_stock": "no", "returns": "2", "location": "Alwal"},
        hmap,
    )
    assert out["in_stock"] is False
    assert out["returns"] == 2
    assert out["location"] == "Alwal"


@pytest.mark.parametrize(("raw", "expected"), [("yes", False), ("1", False), ("no", True), ("", None)])
def test_stockout_column_is_the_inverse_of_in_stock(raw, expected):
    out = fi.map_sales_row(
        {"sku": "A", "qty": "0", "date": "2026-06-15", "stockout": raw},
        _hmap("sku", "qty", "date", "stockout"),
    )
    assert out["in_stock"] is expected


def test_unreadable_availability_or_negative_returns_are_row_errors():
    hmap = _hmap("sku", "qty", "date", "in_stock", "returns")
    with pytest.raises(fi.RowError, match="in_stock"):
        fi.map_sales_row({"sku": "A", "qty": "1", "date": "2026-06-15", "in_stock": "maybe"}, hmap)
    with pytest.raises(fi.RowError, match="returns"):
        fi.map_sales_row({"sku": "A", "qty": "1", "date": "2026-06-15", "returns": "-2"}, hmap)


# Weeks of 2026 (Mondays), a 9-week span (gap detection needs >= 8):
# leading zero, sale, stockout zero, GAP (07-27), sales, trailing zero.
_SERIES = """
sku,date,quantity,in_stock
ZERO-1,2026-07-06,0,yes
ZERO-1,2026-07-13,5,yes
ZERO-1,2026-07-20,0,no
ZERO-1,2026-08-03,4,yes
ZERO-1,2026-08-10,3,yes
ZERO-1,2026-08-17,2,yes
ZERO-1,2026-08-24,6,yes
ZERO-1,2026-08-31,0,yes
"""


async def test_zero_weeks_are_stored_and_only_the_true_gap_is_missing(app_role_db, make_tenant):
    tenant = await make_tenant()
    headers, records = fi.parse_table("weekly.csv", _SERIES.strip().encode())

    first = await fi.import_rows(
        db=app_role_db, tenant_id=tenant, industry=IndustryCode.fashion, kind="sales",
        headers=headers, records=records, identity="period",
    )
    replay = await fi.import_rows(
        db=app_role_db, tenant_id=tenant, industry=IndustryCode.fashion, kind="sales",
        headers=headers, records=records, identity="period",
    )

    assert first["rows_inserted"] == 8
    assert first["rows_skipped"] == 0
    assert replay["rows_inserted"] == 0
    async with app_role_db.session(str(tenant)) as s:
        rows = (
            await s.execute(
                text("SELECT sale_time::date AS d, units_sold, in_stock FROM historical_sales ORDER BY 1")
            )
        ).all()
        report = await data_quality_audit.audit(s, tenant_id=tenant, industry="fashion")

    assert [(r.d.isoformat(), r.units_sold, r.in_stock) for r in rows] == [
        ("2026-07-06", 0, True),   # leading observed zero survives
        ("2026-07-13", 5, True),
        ("2026-07-20", 0, False),  # stockout, not zero demand
        ("2026-08-03", 4, True),
        ("2026-08-10", 3, True),
        ("2026-08-17", 2, True),
        ("2026-08-24", 6, True),
        ("2026-08-31", 0, True),   # trailing observed zero survives
    ]
    gaps = next(f for f in report["findings"] if f["key"] == "missing_weeks")
    assert gaps["count"] == 1  # only 2026-07-27, which has no row at all
