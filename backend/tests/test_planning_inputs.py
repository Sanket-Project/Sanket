"""One dated input-readiness contract for coverage, decisions and the simulator (deep audit F6).

Coverage rejected forecasts older than 14 days and stock older than 30, while
decisions and the simulator used the same run with no age check and read every
week in it — including weeks already in the past.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import text

from app.services.planning_inputs import (
    FORECAST_MAX_AGE_DAYS,
    STALE_STOCK_DAYS,
    future_forecast_bands,
    is_run_fresh,
    stock_is_stale,
)

NOW = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)  # Monday


def test_contract_matches_the_published_coverage_policy():
    assert FORECAST_MAX_AGE_DAYS == 14
    assert STALE_STOCK_DAYS == 30


def test_run_freshness():
    assert is_run_fresh(SimpleNamespace(completed_at=NOW - timedelta(days=13)), NOW)
    assert not is_run_fresh(SimpleNamespace(completed_at=NOW - timedelta(days=15)), NOW)
    assert not is_run_fresh(SimpleNamespace(completed_at=None), NOW)
    assert not is_run_fresh(None, NOW)
    naive = (NOW - timedelta(days=2)).replace(tzinfo=None)
    assert is_run_fresh(SimpleNamespace(completed_at=naive), NOW)


def test_stock_staleness():
    assert stock_is_stale(None, NOW)
    assert stock_is_stale(NOW - timedelta(days=31), NOW)
    assert not stock_is_stale(NOW - timedelta(days=29), NOW)


async def test_future_bands_start_at_the_current_week(app_role_db, make_tenant, db_session):
    tenant = await make_tenant("fashion")
    pid, sku = uuid.uuid4(), uuid.uuid4()
    run = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO products (id, tenant_id, industry, name, category, status) "
             "VALUES (:p, :t, 'fashion', 'Kurti', 'Kurtis', 'active')"),
        {"p": str(pid), "t": str(tenant)},
    )
    await db_session.execute(
        text("INSERT INTO skus (id, tenant_id, product_id, industry, sku_code) "
             "VALUES (:s, :t, :p, 'fashion', 'PI-1')"),
        {"s": str(sku), "t": str(tenant), "p": str(pid)},
    )
    await db_session.execute(
        text("INSERT INTO forecast_runs (id, tenant_id, industry, model_stack, horizon_weeks, "
             "granularity, status, completed_at, metrics) VALUES (:r, :t, 'fashion', "
             "ARRAY['chronos_zero_shot'], 6, 'weekly', 'completed', :c, CAST(:m AS jsonb))"),
        {"r": str(run), "t": str(tenant), "c": NOW - timedelta(days=3),
         "m": json.dumps({"mode": "zero_shot"})},
    )
    # Weeks start three weeks before the current one; p50 encodes the offset.
    for offset in range(-3, 3):
        await db_session.execute(
            text("INSERT INTO forecast_results (tenant_id, run_id, sku_id, forecast_date, p10, "
                 "p50, p90, model_name) VALUES (:t, :r, :s, :d, :p, :p, :p, 'chronos_zero_shot')"),
            {"t": str(tenant), "r": str(run), "s": str(sku), "p": 100 + offset,
             "d": date(2026, 10, 26) + timedelta(weeks=offset)},
        )
    await db_session.commit()

    async with app_role_db.session(str(tenant)) as s:
        bands = await future_forecast_bands(s, tenant, run, NOW)

    assert bands[sku].p50 == [100.0, 101.0, 102.0]
