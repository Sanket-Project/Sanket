"""Decisions act only on current inputs (deep audit F6).

Before this fix ``build_decisions`` took the newest completed run of any age,
read forecast weeks already in the past as upcoming demand, and treated a SKU
with no recorded stock as holding zero — so it could order a SKU's entire
demand on the strength of a missing row.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text

from app.services.decision_builder import build_decisions, refresh
from app.services.decision_engine import PolicyConfig

NOW = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)  # Monday


async def _sku(db, tenant, code, cost=40, price=100):
    pid, sid = uuid.uuid4(), uuid.uuid4()
    await db.execute(
        text("INSERT INTO products (id, tenant_id, industry, name, category, status) "
             "VALUES (:p, :t, 'fashion', 'Kurti', 'Kurtis', 'active')"),
        {"p": str(pid), "t": str(tenant)},
    )
    await db.execute(
        text("INSERT INTO skus (id, tenant_id, product_id, industry, sku_code, lead_time_days, "
             "unit_cost, unit_price) VALUES (:s, :t, :p, 'fashion', :c, 14, :uc, :up)"),
        {"s": str(sid), "t": str(tenant), "p": str(pid), "c": code, "uc": cost, "up": price},
    )
    return sid


async def _stock(db, tenant, sku, units, as_of):
    await db.execute(
        text("INSERT INTO inventory_levels (tenant_id, sku_id, industry, location, on_hand_units, "
             "reserved_units, inbound_units, source, as_of) VALUES (:t, :s, 'fashion', 'WH', :u, 0, "
             "0, 'synthetic_test', :a)"),
        {"t": str(tenant), "s": str(sku), "u": units, "a": as_of},
    )


async def _run(db, tenant, skus, completed, first_week_offset=0, weeks=12, p50=None):
    run = uuid.uuid4()
    await db.execute(
        text("INSERT INTO forecast_runs (id, tenant_id, industry, model_stack, horizon_weeks, "
             "granularity, status, completed_at, metrics) VALUES (:r, :t, 'fashion', "
             "ARRAY['chronos_zero_shot'], :h, 'weekly', 'completed', :c, CAST(:m AS jsonb))"),
        {"r": str(run), "t": str(tenant), "h": weeks, "c": completed,
         "m": json.dumps({"mode": "zero_shot"})},
    )
    for sku in skus:
        for i in range(weeks):
            offset = first_week_offset + i
            value = p50(offset) if p50 else 50
            await db.execute(
                text("INSERT INTO forecast_results (tenant_id, run_id, sku_id, forecast_date, p10, "
                     "p50, p90, model_name) VALUES (:t, :r, :s, :d, :lo, :p, :hi, "
                     "'chronos_zero_shot')"),
                {"t": str(tenant), "r": str(run), "s": str(sku), "p": value, "lo": value * 0.8,
                 "hi": value * 1.2, "d": date(2026, 10, 26) + timedelta(weeks=offset)},
            )
    return run


async def _build(app_role_db, tenant):
    async with app_role_db.session(str(tenant)) as s:
        return await build_decisions(s, tenant_id=tenant, industry="fashion",
                                     policy=PolicyConfig(), now=NOW)


async def test_a_stale_forecast_run_produces_no_decisions(app_role_db, make_tenant, db_session):
    tenant = await make_tenant("fashion")
    sku = await _sku(db_session, tenant, "RD-STALE")
    await _stock(db_session, tenant, sku, 0, NOW - timedelta(days=1))
    await _run(db_session, tenant, [sku], NOW - timedelta(days=20))
    await db_session.commit()

    result = await _build(app_role_db, tenant)

    assert result.decisions == []
    assert "older than 14 days" in result.reason


async def test_sku_without_recorded_stock_is_skipped_not_zeroed(app_role_db, make_tenant, db_session):
    tenant = await make_tenant("fashion")
    stocked = await _sku(db_session, tenant, "RD-STOCKED")
    missing = await _sku(db_session, tenant, "RD-MISSING")
    await _stock(db_session, tenant, stocked, 0, NOW - timedelta(days=1))
    await _run(db_session, tenant, [stocked, missing], NOW - timedelta(days=1))
    await db_session.commit()

    result = await _build(app_role_db, tenant)

    assert any(d.sku_code == "RD-STOCKED" for d in result.decisions)
    assert all(d.sku_code != "RD-MISSING" for d in result.decisions)
    skipped = {s["sku_code"]: s["reason"] for s in result.skipped}
    assert "no recorded stock" in skipped["RD-MISSING"].lower()


async def test_sku_with_stale_stock_is_skipped(app_role_db, make_tenant, db_session):
    tenant = await make_tenant("fashion")
    sku = await _sku(db_session, tenant, "RD-OLDSTOCK")
    await _stock(db_session, tenant, sku, 0, NOW - timedelta(days=40))
    await _run(db_session, tenant, [sku], NOW - timedelta(days=1))
    await db_session.commit()

    result = await _build(app_role_db, tenant)

    assert result.decisions == []
    skipped = {s["sku_code"]: s["reason"] for s in result.skipped}
    assert "40 days ago" in skipped["RD-OLDSTOCK"]


async def test_past_forecast_weeks_are_not_treated_as_upcoming_demand(
    app_role_db, make_tenant, db_session
):
    tenant = await make_tenant("fashion")
    sku = await _sku(db_session, tenant, "RD-PAST")
    await _stock(db_session, tenant, sku, 0, NOW - timedelta(days=1))
    # Past weeks carry a huge spike; current and future weeks are 10/week.
    await _run(db_session, tenant, [sku], NOW - timedelta(days=1), first_week_offset=-4,
               weeks=16, p50=lambda off: 1000 if off < 0 else 10)
    await db_session.commit()

    result = await _build(app_role_db, tenant)

    order = next(d for d in result.decisions if d.kind == "purchase_order")
    # 14-day lead + 28-day review = 6 weeks of 10 units.
    assert order.inputs["demand_p50_over_window"] == 60


def test_totals_do_not_count_unknown_money_as_zero():
    from app.routers.decisions import _totals

    def po(capital, revenue):
        return {"kind": "purchase_order", "recommended_units": 10, "urgency": "high",
                "currency": "INR", "economics": {"capital_committed": capital,
                                                 "working_capital_released": capital,
                                                 "revenue_protected": revenue}}

    complete = _totals([po(100.0, 500.0), po(50.0, 250.0)])
    assert complete["capital_committed"] == 150.0
    assert complete["money_complete"] is True

    partial = _totals([po(100.0, 500.0), po(None, None)])
    assert partial["capital_committed"] is None
    assert partial["revenue_protected"] is None
    assert partial["money_complete"] is False
    assert partial["units_to_order"] == 20


def test_serialized_recommendation_keeps_unknown_cost_unknown():
    from types import SimpleNamespace

    from app.services.decision_builder import serialize

    rec = SimpleNamespace(
        id=uuid.uuid4(), sku_id=uuid.uuid4(), kind="purchase_order", status="open",
        urgency="high", headline="h", recommended_units=1, baseline_units=1,
        accepted_units=None, confidence=70, confidence_band="moderate", currency="INR",
        unit_cost=0, unit_price=100, reasons=[], economics={},
        inputs={"unit_cost": None, "unit_price": 100.0}, linked_alert_id=None,
        created_at=None, decided_at=None, expires_at=None,
    )
    item = serialize(rec)
    assert item["unit_cost"] is None
    assert item["unit_price"] == 100.0


async def test_missing_unit_cost_is_carried_as_unknown(app_role_db, make_tenant, db_session):
    tenant = await make_tenant("fashion")
    sku = await _sku(db_session, tenant, "RD-NOCOST", cost=None)
    await _stock(db_session, tenant, sku, 0, NOW - timedelta(days=1))
    await _run(db_session, tenant, [sku], NOW - timedelta(days=1))
    await db_session.commit()

    result = await _build(app_role_db, tenant)

    order = next(d for d in result.decisions if d.kind == "purchase_order")
    assert order.economics["capital_committed"] is None
    assert order.inputs["unit_cost"] is None
    assert order.inputs["lead_time_assumed"] is False


# ── Review follow-ups: stale inputs never leave an acceptable queue ─────────


async def _open_rec(db, tenant, sku):
    rid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO recommendations (id, tenant_id, industry, sku_id, kind, status, urgency, "
             "headline, recommended_units, expires_at) VALUES (:r, :t, 'fashion', :s, "
             "'purchase_order', 'open', 'high', 'old order', 10, :e)"),
        {"r": str(rid), "t": str(tenant), "s": str(sku), "e": NOW + timedelta(days=10)},
    )
    return rid


async def _status(db, rid):
    return await db.scalar(text("SELECT status::text FROM recommendations WHERE id = :i"), {"i": str(rid)})


async def test_refresh_on_a_stale_forecast_expires_the_old_queue(app_role_db, make_tenant, db_session):
    tenant = await make_tenant("fashion")
    sku = await _sku(db_session, tenant, "RD-OLDQ")
    await _stock(db_session, tenant, sku, 0, NOW - timedelta(days=1))
    await _run(db_session, tenant, [sku], NOW - timedelta(days=20))
    rid = await _open_rec(db_session, tenant, sku)
    await db_session.commit()

    async with app_role_db.session(str(tenant)) as s:
        result, rows = await refresh(s, tenant_id=tenant, industry="fashion", tenant_settings={}, now=NOW)

    assert rows == []
    assert "older than 14 days" in result.reason
    assert await _status(db_session, rid) == "expired"


async def test_refresh_with_nothing_to_do_expires_the_old_queue(app_role_db, make_tenant, db_session):
    tenant = await make_tenant("fashion")
    sku = await _sku(db_session, tenant, "RD-NOTHING")
    await _stock(db_session, tenant, sku, 5, NOW - timedelta(days=1))  # covers the window; not excess
    await _run(db_session, tenant, [sku], NOW - timedelta(days=1), p50=lambda off: 0.5)
    rid = await _open_rec(db_session, tenant, sku)
    await db_session.commit()

    async with app_role_db.session(str(tenant)) as s:
        await refresh(s, tenant_id=tenant, industry="fashion", tenant_settings={}, now=NOW)

    assert await _status(db_session, rid) == "expired"


async def test_recommendation_expires_when_its_inputs_go_stale(app_role_db, make_tenant, db_session):
    tenant = await make_tenant("fashion")
    sku = await _sku(db_session, tenant, "RD-AGE")
    await _stock(db_session, tenant, sku, 0, NOW - timedelta(days=25))  # stale in 5 days
    await _run(db_session, tenant, [sku], NOW - timedelta(days=12))     # stale in 2 days
    await db_session.commit()

    async with app_role_db.session(str(tenant)) as s:
        _, rows = await refresh(s, tenant_id=tenant, industry="fashion", tenant_settings={}, now=NOW)
        expiries = {r.expires_at for r in rows}

    assert rows
    assert expiries == {NOW + timedelta(days=2)}
