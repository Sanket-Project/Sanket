"""A completed SKU run splits consistently across its recorded locations."""
from __future__ import annotations
import json
import asyncio
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
import pytest
from sqlalchemy import text
from app.models.forecast import ForecastRun
from app.services.location_forecast import ensure_location_split, split_run_by_location
NOW = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
WINDOW = [date(2026, 10, 19) - timedelta(weeks=i) for i in range(12)]
TRAILING_WEEKS = WINDOW

async def _sku(db, tenant, code="KURTI-M", lead=14):
    pid, sid = uuid.uuid4(), uuid.uuid4()
    await db.execute(
        text("INSERT INTO products (id, tenant_id, industry, name, category, status) "
             "VALUES (:p, :t, 'fashion', 'Kurti', 'Kurtis', 'active')"),
        {"p": str(pid), "t": str(tenant)},
    )
    await db.execute(
        text("INSERT INTO skus (id, tenant_id, product_id, industry, sku_code, lead_time_days) "
             "VALUES (:s, :t, :p, 'fashion', :c, :l)"),
        {"s": str(sid), "t": str(tenant), "p": str(pid), "c": code, "l": lead},
    )
    return sid


async def _stock(db, tenant, sku, location, units, as_of=NOW - timedelta(days=1)):
    await db.execute(
        text("INSERT INTO inventory_levels (tenant_id, sku_id, industry, location, on_hand_units, "
             "reserved_units, inbound_units, source, as_of) VALUES (:t, :s, 'fashion', :l, :u, 0, 0, "
             "'synthetic_test', :a)"),
        {"t": str(tenant), "s": str(sku), "l": location, "u": units, "a": as_of},
    )


async def _weekly_sales(db, tenant, sku, per_week, weeks=TRAILING_WEEKS, location=None):
    for wk in weeks:
        await db.execute(
            text("INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, channel, "
                 "units_sold, location) VALUES (:t, :s, 'fashion', :w, 'store', :u, :l)"),
            {"t": str(tenant), "s": str(sku), "u": per_week, "l": location,
             "w": datetime(wk.year, wk.month, wk.day, 12, tzinfo=UTC)},
        )


async def _forecast(db, tenant, sku, *, completed, weekly_p50, mode="zero_shot"):
    run = uuid.uuid4()
    await db.execute(
        text("INSERT INTO forecast_runs (id, tenant_id, industry, model_stack, horizon_weeks, "
             "granularity, status, completed_at, metrics) VALUES (:r, :t, 'fashion', "
             "ARRAY['chronos_zero_shot'], 8, 'weekly', 'completed', :c, CAST(:m AS jsonb))"),
        {"r": str(run), "t": str(tenant), "c": completed,
         "m": json.dumps({"mode": mode, "calendar": "W-MON-UTC", "history_end": "2026-10-26"})},
    )
    for i in range(8):
        await db.execute(
            text("INSERT INTO forecast_results (tenant_id, run_id, sku_id, forecast_date, p10, p50, "
                 "p90, model_name) VALUES (:t, :r, :s, :d, :p, :p, :p, 'chronos_zero_shot')"),
            {"t": str(tenant), "r": str(run), "s": str(sku), "p": weekly_p50,
             "d": date(2026, 10, 26) + timedelta(weeks=i)},
        )
    return run


async def test_split_two_stores_reconciles_to_sku(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku = await _sku(db_session, tenant)
    await _weekly_sales(db_session, tenant, sku, 30, weeks=WINDOW, location="Boduppal")
    await _weekly_sales(db_session, tenant, sku, 10, weeks=WINDOW, location="Alwal")
    run = await _forecast(db_session, tenant, sku, completed=NOW, weekly_p50=40)
    await db_session.commit()

    async with app_role_db.session(str(tenant)) as s:
        summary = await split_run_by_location(s, tenant_id=tenant, industry="fashion",
                                              run_id=run, now=NOW)
        rows = (await s.execute(text(
            "SELECT l.code, f.forecast_date, f.p50, f.share_basis FROM location_forecast_results f "
            "JOIN locations l ON l.id = f.location_id WHERE f.run_id = :r"), {"r": str(run)})).all()

    assert summary.series == 2 and summary.degraded is False
    by_week = defaultdict(float)
    for code, d, p50, _ in rows:
        by_week[d] += float(p50)
    assert all(v == pytest.approx(40.0, abs=1e-3) for v in by_week.values())
    bod = [float(p50) for code, _, p50, _ in rows if code == "boduppal"]
    assert bod[0] == pytest.approx(30.0, abs=1e-3)


async def test_unassigned_over_five_percent_is_degraded(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku = await _sku(db_session, tenant)
    await _weekly_sales(db_session, tenant, sku, 9, weeks=WINDOW, location="Alwal")
    await _weekly_sales(db_session, tenant, sku, 1, weeks=WINDOW, location=None)
    run = await _forecast(db_session, tenant, sku, completed=NOW, weekly_p50=10)
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as s:
        summary = await split_run_by_location(s, tenant_id=tenant, industry="fashion",
                                              run_id=run, now=NOW)
    assert summary.degraded is True
    assert summary.unassigned_share == pytest.approx(0.1, abs=1e-6)


async def test_split_is_idempotent(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku = await _sku(db_session, tenant)
    await _weekly_sales(db_session, tenant, sku, 5, weeks=WINDOW, location="Alwal")
    run = await _forecast(db_session, tenant, sku, completed=NOW, weekly_p50=5)
    await db_session.commit()
    count_sql = text("SELECT count(*) FROM location_forecast_results WHERE run_id = :r")
    async with app_role_db.session(str(tenant)) as s:
        await split_run_by_location(s, tenant_id=tenant, industry="fashion", run_id=run, now=NOW)
        first = await s.scalar(count_sql, {"r": str(run)})
        await split_run_by_location(s, tenant_id=tenant, industry="fashion", run_id=run, now=NOW)
        second = await s.scalar(count_sql, {"r": str(run)})
        run_row = await s.get(ForecastRun, run)
        again = await ensure_location_split(s, tenant_id=tenant, industry="fashion",
                                            run=run_row, now=NOW)
    assert first == second == 8
    assert again is None


async def test_entirely_unassigned_sku_is_not_allocated_by_category(
    db_session, app_role_db, make_tenant
):
    tenant = await make_tenant()
    assigned = await _sku(db_session, tenant, code="ASSIGNED")
    unassigned = await _sku(db_session, tenant, code="UNASSIGNED")
    await _weekly_sales(db_session, tenant, assigned, 10, weeks=WINDOW, location="Alwal")
    await _weekly_sales(db_session, tenant, unassigned, 10, weeks=WINDOW, location=None)
    run = await _forecast(db_session, tenant, unassigned, completed=NOW, weekly_p50=10)
    # Include the category's assigned SKU in this run.
    await db_session.execute(text(
        "INSERT INTO forecast_results (tenant_id, run_id, sku_id, forecast_date, p10, p50, "
        "p90, model_name) VALUES (:t, :r, :s, '2026-10-26', 5, 10, 15, 'test')"
    ), {"t": str(tenant), "r": str(run), "s": str(assigned)})
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as s:
        await split_run_by_location(s, tenant_id=tenant, industry="fashion", run_id=run, now=NOW)
        allocated = await s.scalar(text(
            "SELECT coalesce(sum(p50), 0) FROM location_forecast_results "
            "WHERE run_id = :r AND sku_id = :s"
        ), {"r": str(run), "s": str(unassigned)})
    assert allocated == 0


async def test_category_prior_does_not_reintroduce_stockout_bias(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku = await _sku(db_session, tenant)
    await _weekly_sales(db_session, tenant, sku, 10, weeks=WINDOW, location='a')
    await _weekly_sales(db_session, tenant, sku, 10, weeks=WINDOW[6:], location='b')
    await _weekly_sales(db_session, tenant, sku, 0, weeks=WINDOW[:6], location='b')
    await db_session.execute(text("UPDATE historical_sales SET in_stock = FALSE WHERE tenant_id = :t "
        "AND location = 'b' AND units_sold = 0"), {'t': str(tenant)})
    run = await _forecast(db_session, tenant, sku, completed=NOW, weekly_p50=20)
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as s:
        await split_run_by_location(s, tenant_id=tenant, industry='fashion', run_id=run, now=NOW)
        values = (await s.execute(text('SELECT DISTINCT p50 FROM location_forecast_results WHERE run_id = :r'),
                                  {'r': str(run)})).scalars().all()
    assert values == [10]


async def test_new_sku_uses_category_sales_outside_forecast_run(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    old = await _sku(db_session, tenant, code='OLD')
    new = await _sku(db_session, tenant, code='NEW')
    await _weekly_sales(db_session, tenant, old, 10, weeks=WINDOW, location='a')
    run = await _forecast(db_session, tenant, new, completed=NOW, weekly_p50=10)
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as s:
        summary = await split_run_by_location(s, tenant_id=tenant, industry='fashion', run_id=run, now=NOW)
    assert summary.series == 1


async def test_missing_sales_do_not_claim_zero_unassigned_share(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku = await _sku(db_session, tenant)
    run = await _forecast(db_session, tenant, sku, completed=NOW, weekly_p50=10)
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as s:
        summary = await split_run_by_location(s, tenant_id=tenant, industry='fashion', run_id=run, now=NOW)
    assert summary.unassigned_share is None
    assert summary.excluded[0]['reason'] == 'No sales history for this SKU or its category'


async def test_empty_location_split_is_completed_once(db_session, app_role_db, make_tenant):
    """No eligible location is a completed, auditable result, not pending work."""
    tenant = await make_tenant()
    sku = await _sku(db_session, tenant)
    run_id = await _forecast(db_session, tenant, sku, completed=NOW, weekly_p50=10)
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as session:
        run = await session.get(ForecastRun, run_id)
        first = await ensure_location_split(
            session, tenant_id=tenant, industry="fashion", run=run, now=NOW,
        )
        second = await ensure_location_split(
            session, tenant_id=tenant, industry="fashion", run=run, now=NOW,
        )
        metrics = await session.scalar(text("SELECT metrics FROM forecast_runs WHERE id = :r"),
                                       {"r": str(run_id)})
    assert first is not None and first.series == 0
    assert second is None
    assert metrics["location_split_completed_at"]


async def test_location_output_insert_buffers_are_bounded(
    db_session, app_role_db, make_tenant, monkeypatch,
):
    """Flush output while producing it, rather than retaining the location expansion."""
    from app.models.location import LocationForecastResult
    from sqlalchemy.sql.dml import Insert

    tenant = await make_tenant()
    sku = await _sku(db_session, tenant)
    # One SKU expanded across 300 real location codes produces 2,400 rows.
    for i in range(300):
        await _weekly_sales(db_session, tenant, sku, 1, weeks=WINDOW[:1], location=f"store-{i}")
    run_id = await _forecast(db_session, tenant, sku, completed=NOW, weekly_p50=300)
    await db_session.commit()
    lengths = []
    async with app_role_db.session(str(tenant)) as session:
        original_execute = session.execute

        async def record_execute(statement, params=None, **kwargs):
            if isinstance(statement, Insert) and statement.table.name == LocationForecastResult.__tablename__:
                lengths.append(len(params))
            return await original_execute(statement, params, **kwargs)

        monkeypatch.setattr(session, "execute", record_execute)
        await split_run_by_location(
            session, tenant_id=tenant, industry="fashion", run_id=run_id, now=NOW,
        )
    assert sum(lengths) == 2400
    assert max(lengths) <= 1000


async def test_concurrent_empty_split_repairs_do_not_repeat_work(
    db_session, app_role_db, make_tenant, monkeypatch,
):
    from app.services import location_forecast

    tenant = await make_tenant()
    sku = await _sku(db_session, tenant)
    run_id = await _forecast(db_session, tenant, sku, completed=NOW, weekly_p50=10)
    await db_session.commit()
    calls = 0
    original_split = location_forecast.split_run_by_location

    async def slow_split(*args, **kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.2)
        return await original_split(*args, **kwargs)

    monkeypatch.setattr(location_forecast, "split_run_by_location", slow_split)

    async def repair():
        async with app_role_db.session(str(tenant)) as session:
            run = await session.get(ForecastRun, run_id)
            return await ensure_location_split(
                session, tenant_id=tenant, industry="fashion", run=run, now=NOW,
            )

    results = await asyncio.gather(repair(), repair())
    assert calls == 1
    assert sum(result is None for result in results) == 1


async def test_legacy_split_rows_are_marked_complete_without_recomputing(
    db_session, app_role_db, make_tenant, monkeypatch,
):
    from app.services import location_forecast

    tenant = await make_tenant()
    sku = await _sku(db_session, tenant)
    await _weekly_sales(db_session, tenant, sku, 5, weeks=WINDOW, location="alwal")
    run_id = await _forecast(db_session, tenant, sku, completed=NOW, weekly_p50=5)
    await split_run_by_location(db_session, tenant_id=tenant, industry="fashion", run_id=run_id, now=NOW)
    await db_session.execute(text(
        "UPDATE forecast_runs SET metrics=metrics - 'location_split_completed_at' WHERE id=:r"
    ), {"r": str(run_id)})
    await db_session.commit()

    async def unexpected_recompute(*args, **kwargs):
        pytest.fail("A legacy persisted split must not be recomputed")

    monkeypatch.setattr(location_forecast, "split_run_by_location", unexpected_recompute)
    async with app_role_db.session(str(tenant)) as session:
        run = await session.get(ForecastRun, run_id)
        result = await ensure_location_split(
            session, tenant_id=tenant, industry="fashion", run=run, now=NOW,
        )
        metrics = await session.scalar(text("SELECT metrics FROM forecast_runs WHERE id=:r"),
                                       {"r": str(run_id)})
    assert result is None
    assert metrics.get("location_split_completed_at")
    assert metrics["location_series"] == 1
