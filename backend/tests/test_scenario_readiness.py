"""The simulator discloses stale and missing inputs instead of hiding them (deep audit F6).

It still runs — a what-if on yesterday's numbers is useful — but the response
says which inputs are stale, missing or assumed, and marks itself advisory.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.core.calendar import current_week_start


async def _sku(db, tenant, code, lead=14, cost=40):
    pid, sid = uuid.uuid4(), uuid.uuid4()
    await db.execute(
        text("INSERT INTO products (id, tenant_id, industry, name, category, status) "
             "VALUES (:p, :t, 'fashion', 'Kurti', 'Kurtis', 'active')"),
        {"p": str(pid), "t": str(tenant)},
    )
    await db.execute(
        text("INSERT INTO skus (id, tenant_id, product_id, industry, sku_code, lead_time_days, "
             "unit_cost, unit_price) VALUES (:s, :t, :p, 'fashion', :c, :l, :uc, 100)"),
        {"s": str(sid), "t": str(tenant), "p": str(pid), "c": code, "l": lead, "uc": cost},
    )
    return sid


async def _seed(db, tenant, *, run_age_days):
    now = datetime.now(UTC)
    stocked = await _sku(db, tenant, "SR-STOCKED")
    bare = await _sku(db, tenant, "SR-NOSTOCK", lead=None, cost=None)
    await db.execute(
        text("INSERT INTO inventory_levels (tenant_id, sku_id, industry, location, on_hand_units, "
             "reserved_units, inbound_units, source, as_of) VALUES (:t, :s, 'fashion', 'WH', 500, "
             "0, 0, 'synthetic_test', :a)"),
        {"t": str(tenant), "s": str(stocked), "a": now - timedelta(days=1)},
    )
    run = uuid.uuid4()
    await db.execute(
        text("INSERT INTO forecast_runs (id, tenant_id, industry, model_stack, horizon_weeks, "
             "granularity, status, completed_at, metrics) VALUES (:r, :t, 'fashion', "
             "ARRAY['chronos_zero_shot'], 12, 'weekly', 'completed', :c, CAST(:m AS jsonb))"),
        {"r": str(run), "t": str(tenant), "c": now - timedelta(days=run_age_days),
         "m": json.dumps({"mode": "zero_shot"})},
    )
    first = current_week_start(now)
    for sku in (stocked, bare):
        for i in range(12):
            await db.execute(
                text("INSERT INTO forecast_results (tenant_id, run_id, sku_id, forecast_date, p10, "
                     "p50, p90, model_name) VALUES (:t, :r, :s, :d, 8, 10, 12, 'chronos_zero_shot')"),
                {"t": str(tenant), "r": str(run), "s": str(sku), "d": first + timedelta(weeks=i)},
            )
    await db.commit()


async def test_stale_forecast_is_disclosed_and_marks_the_run_advisory(
    client, signed_in_workspace, db_session
):
    tenant, headers = await signed_in_workspace("fashion")
    await _seed(db_session, tenant, run_age_days=20)

    r = await client.post("/api/v1/scenarios/simulate", json={"horizon_weeks": 26}, headers=headers)

    assert r.status_code == 200, r.text
    body = r.json()
    readiness = body["readiness"]
    assert readiness["forecast_stale"] is True
    assert readiness["forecast_age_days"] >= 20
    assert readiness["advisory"] is True
    assert readiness["skus_missing_stock"] == ["SR-NOSTOCK"]
    assert readiness["skus_lead_time_assumed"] == ["SR-NOSTOCK"]
    assert readiness["skus_missing_cost"] == ["SR-NOSTOCK"]
    assert body["config"]["horizon_weeks"] == 12
    assert body["baseline"]["purchase_spend"] is None


async def test_current_complete_inputs_are_not_advisory(client, signed_in_workspace, db_session):
    tenant, headers = await signed_in_workspace("fashion")
    await _seed(db_session, tenant, run_age_days=1)

    r = await client.post(
        "/api/v1/scenarios/simulate", json={"horizon_weeks": 8}, headers=headers
    )

    readiness = r.json()["readiness"]
    assert readiness["forecast_stale"] is False
    # Still advisory: one SKU has no stock, no cost and an assumed lead time.
    assert readiness["advisory"] is True
    assert readiness["skus_stale_stock"] == []
