"""The sales time series tells "no records yet" apart from "sold nothing" (deep audit F5).

It used to zero-fill every bucket in the window, so a tenant whose history
started last month showed months of observed zero demand before it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.core.calendar import current_week_start


async def _sku(db, tenant):
    pid, sid = uuid.uuid4(), uuid.uuid4()
    await db.execute(
        text("INSERT INTO products (id, tenant_id, industry, name, category, status) "
             "VALUES (:p, :t, 'fashion', 'Kurti', 'Kurtis', 'active')"),
        {"p": str(pid), "t": str(tenant)},
    )
    await db.execute(
        text("INSERT INTO skus (id, tenant_id, product_id, industry, sku_code) "
             "VALUES (:s, :t, :p, 'fashion', 'TS-1')"),
        {"s": str(sid), "t": str(tenant), "p": str(pid)},
    )
    return sid


async def test_weeks_before_the_first_sale_are_null_and_later_gaps_are_zero(
    client, signed_in_workspace, db_session
):
    tenant, headers = await signed_in_workspace("fashion")
    sku = await _sku(db_session, tenant)
    this_week = current_week_start(datetime.now(UTC))
    first = this_week - timedelta(weeks=4)
    for week, units in ((first, 5), (this_week - timedelta(weeks=2), 7)):
        await db_session.execute(
            text("INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, channel, "
                 "units_sold) VALUES (:t, :s, 'fashion', :w, 'store', :u)"),
            {"t": str(tenant), "s": str(sku), "u": units,
             "w": datetime(week.year, week.month, week.day, 12, tzinfo=UTC)},
        )
    await db_session.commit()

    r = await client.get(
        "/api/v1/analytics/sales/timeseries?granularity=week&lookback_days=84", headers=headers
    )

    assert r.status_code == 200, r.text
    body = r.json()
    by_week = {p["bucket"]: p for p in body["series"]}
    assert by_week[(first - timedelta(weeks=1)).isoformat()]["units_sold"] is None
    assert by_week[first.isoformat()]["units_sold"] == 5
    assert by_week[(this_week - timedelta(weeks=3)).isoformat()]["units_sold"] == 0
    assert body["first_sale_at"].startswith(first.isoformat())
    assert body["current_bucket"] == this_week.isoformat()
    assert body["units_basis"] == "gross_units_sold_returns_not_netted"
