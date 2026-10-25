"""The ML loader's SQL, executed for real: weekly buckets are Monday 00:00 UTC.

The ML service runs the same text with a sync driver; here it runs through the
test container so the bucketing is proven against PostgreSQL itself, with the
session time zone deliberately set to India — the convention must not depend
on it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import text

import app  # noqa: F401 — puts the ML package on sys.path
from sanket_ml.data.loader import panel_bounds, sales_panel_sql


async def _sale(db, tenant, sku, when, units):
    await db.execute(
        text(
            "INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, channel, units_sold) "
            "VALUES (:t, :s, 'fashion', :w, 'pos', :u)"
        ),
        {"t": str(tenant), "s": str(sku), "w": when, "u": units},
    )


async def test_buckets_are_monday_utc_whatever_the_session_time_zone(db_session, make_tenant):
    tenant, sku = await make_tenant(), uuid.uuid4()
    # Mon 31 Aug 01:30 IST == Sun 30 Aug 20:00 UTC → belongs to the week of 24 Aug.
    await _sale(db_session, tenant, sku, datetime(2026, 8, 30, 20, 0, tzinfo=UTC), 2)
    await _sale(db_session, tenant, sku, datetime(2026, 8, 31, 0, 0, tzinfo=UTC), 3)
    # Sunday 6 Sep 23:30 UTC — the last moment of the week of 31 Aug.
    await _sale(db_session, tenant, sku, datetime(2026, 9, 6, 23, 30, tzinfo=UTC), 4)
    # Monday 7 Sep: the week after the cutoff, must be excluded.
    await _sale(db_session, tenant, sku, datetime(2026, 9, 7, 0, 0, tzinfo=UTC), 99)
    await db_session.commit()

    start, end = panel_bounds(start=date(2026, 8, 1), end=date(2026, 9, 7))
    await db_session.execute(text("SET TIME ZONE 'Asia/Kolkata'"))
    rows = (
        await db_session.execute(
            text(sales_panel_sql(by_sku=False, by_channel=False)),
            {"tenant_id": str(tenant), "industry": "fashion", "start": start, "end": end,
             "bucket": "week"},
        )
    ).all()
    await db_session.execute(text("SET TIME ZONE 'UTC'"))
    await db_session.rollback()

    assert [(r.ds.date().isoformat(), r.y) for r in rows] == [
        ("2026-08-24", 2.0),
        ("2026-08-31", 7.0),
    ]


def test_bounds_are_timezone_aware_utc_instants():
    start, end = panel_bounds(start=date(2026, 8, 1), end=date(2026, 9, 7))
    assert start == datetime(2026, 8, 1, tzinfo=UTC)
    assert end == datetime(2026, 9, 7, tzinfo=UTC)
