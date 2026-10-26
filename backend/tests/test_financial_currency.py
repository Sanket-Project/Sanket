"""Financial exposure is stated in its currency and never summed across currencies (F03).

The Financial Impact page formatted every figure as USD; for an INR workspace
that labelled rupee amounts as dollars. It also picked its own "latest" run,
which could be an after-the-fact backtest.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text


async def _sku(db, tenant, code, currency):
    pid, sid = uuid.uuid4(), uuid.uuid4()
    await db.execute(
        text("INSERT INTO products (id, tenant_id, industry, name, category, status) "
             "VALUES (:p, :t, 'fashion', 'Kurti', 'Kurtis', 'active')"),
        {"p": str(pid), "t": str(tenant)},
    )
    await db.execute(
        text("INSERT INTO skus (id, tenant_id, product_id, industry, sku_code, currency, unit_price, "
             "unit_cost, safety_stock) VALUES (:s, :t, :p, 'fashion', :c, :cur, 500, 200, 50)"),
        {"s": str(sid), "t": str(tenant), "p": str(pid), "c": code, "cur": currency},
    )
    return sid


async def _run(db, tenant, skus, *, mode="zero_shot", completed=None, p50=10.0, p90=14.0):
    run = uuid.uuid4()
    await db.execute(
        text("INSERT INTO forecast_runs (id, tenant_id, industry, model_stack, horizon_weeks, granularity, "
             "status, completed_at, metrics) VALUES (:r, :t, 'fashion', ARRAY['chronos_zero_shot'], 1, "
             "'weekly', 'completed', :c, CAST(:m AS jsonb))"),
        {"r": str(run), "t": str(tenant), "c": completed or datetime.now(UTC),
         "m": json.dumps({"mode": mode, "calendar": "W-MON-UTC", "history_end": "2026-10-26"})},
    )
    for sku in skus:
        await db.execute(
            text("INSERT INTO forecast_results (tenant_id, run_id, sku_id, forecast_date, p10, p50, p90, "
                 "model_name) VALUES (:t, :r, :s, :d, :p10, :p50, :p90, 'chronos_zero_shot')"),
            {"t": str(tenant), "r": str(run), "s": str(sku), "d": date(2026, 10, 26),
             "p10": p50 / 2, "p50": p50, "p90": p90},
        )


async def test_single_currency_exposure_names_its_currency(client, db_session, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    sku = await _sku(db_session, tenant, "K-M", "INR")
    await _run(db_session, tenant, [sku])
    await db_session.commit()

    body = (await client.get("/api/v1/financial/impact?horizon_weeks=1", headers=headers)).json()

    assert body["currency"] == "INR"
    assert body["total_revenue_at_risk"] == 2000.0  # (14 - 10) x 500
    assert body["by_sku"][0]["currency"] == "INR"


async def test_mixed_currencies_get_per_currency_totals(client, db_session, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    a = await _sku(db_session, tenant, "K-INR", "INR")
    b = await _sku(db_session, tenant, "K-USD", "USD")
    await _run(db_session, tenant, [a, b])
    await db_session.commit()

    impact = (await client.get("/api/v1/financial/impact?horizon_weeks=1", headers=headers)).json()
    costs = (await client.get("/api/v1/inventory/cost-analysis", headers=headers)).json()

    assert impact["currency"] is None
    assert impact["total_revenue_at_risk"] is None
    assert impact["totals_by_currency"]["INR"]["revenue_at_risk"] == 2000.0
    assert impact["totals_by_currency"]["USD"]["revenue_at_risk"] == 2000.0
    assert costs["currency"] is None
    assert costs["totals"]["total_impact"] is None
    assert set(costs["totals_by_currency"]) == {"INR", "USD"}


async def test_exposure_ignores_a_newer_backtest(client, db_session, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    sku = await _sku(db_session, tenant, "K-M", "INR")
    await _run(db_session, tenant, [sku], completed=datetime.now(UTC) - timedelta(days=1))
    await _run(db_session, tenant, [sku], mode="backtest", p50=1000, p90=5000)
    await db_session.commit()

    body = (await client.get("/api/v1/financial/impact?horizon_weeks=1", headers=headers)).json()

    assert body["total_revenue_at_risk"] == 2000.0
