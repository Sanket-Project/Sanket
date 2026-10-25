"""Forecast accuracy joins each forecast week to the actuals of that same week (F02).

Weeks are Monday 00:00 UTC to the next Monday. Production accuracy only counts
a forecast that existed before its week began and was not trained on it;
explicit backtests are reported separately. Seeded runs carry explicit
``completed_at`` / ``history_end`` so every rule is exercised deliberately.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text

from app.services.forecast_accuracy import compute_accuracy

NOW = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
W1 = date(2026, 8, 31)  # Monday
W2 = date(2026, 9, 7)


async def _run(db, tenant, *, completed, history_end, mode="zero_shot", calendar="W-MON-UTC"):
    run_id = uuid.uuid4()
    metrics = {"mode": mode, "calendar": calendar,
               "history_end": history_end.isoformat() if history_end else None}
    await db.execute(
        text(
            "INSERT INTO forecast_runs (id, tenant_id, industry, model_stack, horizon_weeks, "
            "granularity, status, started_at, completed_at, metrics) VALUES (:id, :t, 'fashion', "
            "ARRAY['chronos_zero_shot'], 8, 'weekly', 'completed', :c, :c, CAST(:m AS jsonb))"
        ),
        {"id": str(run_id), "t": str(tenant), "c": completed, "m": json.dumps(metrics)},
    )
    return run_id


async def _fc(db, tenant, run_id, sku, week, p50, p10=None, p90=None):
    await db.execute(
        text(
            "INSERT INTO forecast_results (tenant_id, run_id, sku_id, forecast_date, p10, p50, p90, "
            "model_name) VALUES (:t, :r, :s, :d, :p10, :p50, :p90, 'chronos_zero_shot')"
        ),
        {"t": str(tenant), "r": str(run_id), "s": str(sku), "d": week,
         "p10": p10 if p10 is not None else p50 * 0.8, "p50": p50,
         "p90": p90 if p90 is not None else p50 * 1.2},
    )


async def _sale(db, tenant, sku, when, units):
    await db.execute(
        text(
            "INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, channel, units_sold) "
            "VALUES (:t, :s, 'fashion', :w, 'pos', :u)"
        ),
        {"t": str(tenant), "s": str(sku), "w": when, "u": units},
    )


async def _seed(db_session, make_tenant):
    tenant, sku = await make_tenant(), uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO products (id, tenant_id, industry, name, category, status) VALUES "
            "(:p, :t, 'fashion', 'Kurti', 'Kurtis', 'active')"
        ),
        {"p": str(sku), "t": str(tenant)},
    )
    await db_session.execute(
        text(
            "INSERT INTO skus (id, tenant_id, product_id, industry, sku_code) VALUES "
            "(:s, :t, :p, 'fashion', 'KURTI-M')"
        ),
        {"s": str(sku), "t": str(tenant), "p": str(sku)},
    )
    return tenant, sku


async def _accuracy(app_role_db, tenant, now=NOW):
    async with app_role_db.session(str(tenant)) as s:
        return await compute_accuracy(s, tenant_id=tenant, industry="fashion", now=now)


async def test_actuals_cover_the_whole_monday_to_monday_week(db_session, app_role_db, make_tenant):
    tenant, sku = await _seed(db_session, make_tenant)
    run = await _run(db_session, tenant, completed=datetime(2026, 8, 30, 12, tzinfo=UTC),
                     history_end=W1)
    await _fc(db_session, tenant, run, sku, W1, 100)
    await _sale(db_session, tenant, sku, datetime(2026, 8, 31, 0, 0, tzinfo=UTC), 60)
    await _sale(db_session, tenant, sku, datetime(2026, 9, 6, 23, 0, tzinfo=UTC), 20)  # Sunday night
    await _sale(db_session, tenant, sku, datetime(2026, 9, 7, 0, 0, tzinfo=UTC), 999)  # next week
    await db_session.commit()

    result = await _accuracy(app_role_db, tenant)

    row = result["rows"][0]
    assert result["calendar"] == "W-MON-UTC"
    assert row["sku_code"] == "KURTI-M"
    assert row["n_obs"] == 1
    assert row["weeks"][0]["actual"] == 80
    assert row["wape"] == 25.0  # |100 - 80| / 80
    assert row["bias_pct"] == 25.0
    assert result["summary"]["points"] == 1


async def test_forecast_made_after_the_week_began_is_excluded(db_session, app_role_db, make_tenant):
    tenant, sku = await _seed(db_session, make_tenant)
    run = await _run(db_session, tenant, completed=datetime(2026, 9, 2, tzinfo=UTC), history_end=W1)
    await _fc(db_session, tenant, run, sku, W1, 100)
    await _sale(db_session, tenant, sku, datetime(2026, 9, 1, tzinfo=UTC), 80)
    await db_session.commit()

    result = await _accuracy(app_role_db, tenant)

    assert result["rows"] == []
    assert result["excluded"]["generated_after_period_start"] == 1


async def test_run_trained_on_the_week_it_predicts_is_excluded(db_session, app_role_db, make_tenant):
    tenant, sku = await _seed(db_session, make_tenant)
    run = await _run(db_session, tenant, completed=datetime(2026, 8, 30, tzinfo=UTC), history_end=W2)
    await _fc(db_session, tenant, run, sku, W1, 100)
    await _sale(db_session, tenant, sku, datetime(2026, 9, 1, tzinfo=UTC), 80)
    await db_session.commit()

    result = await _accuracy(app_role_db, tenant)

    assert result["rows"] == []
    assert result["excluded"]["trained_on_period"] == 1


async def test_latest_forecast_made_before_the_week_wins(db_session, app_role_db, make_tenant):
    tenant, sku = await _seed(db_session, make_tenant)
    old = await _run(db_session, tenant, completed=datetime(2026, 8, 10, tzinfo=UTC),
                     history_end=date(2026, 8, 10))
    new = await _run(db_session, tenant, completed=datetime(2026, 8, 30, tzinfo=UTC), history_end=W1)
    await _fc(db_session, tenant, old, sku, W1, 500)
    await _fc(db_session, tenant, new, sku, W1, 90)
    await _sale(db_session, tenant, sku, datetime(2026, 9, 1, tzinfo=UTC), 100)
    await db_session.commit()

    result = await _accuracy(app_role_db, tenant)

    week = result["rows"][0]["weeks"][0]
    assert week["p50"] == 90
    assert week["run_id"] == str(new)
    assert week["lead_weeks"] == 0


async def test_legacy_sunday_dated_runs_are_not_scored(db_session, app_role_db, make_tenant):
    tenant, sku = await _seed(db_session, make_tenant)
    run = await _run(db_session, tenant, completed=datetime(2026, 8, 25, tzinfo=UTC),
                     history_end=None, calendar=None)
    await _fc(db_session, tenant, run, sku, date(2026, 8, 30), 100)  # a Sunday
    await _sale(db_session, tenant, sku, datetime(2026, 9, 1, tzinfo=UTC), 80)
    await db_session.commit()

    result = await _accuracy(app_role_db, tenant)

    assert result["rows"] == []
    assert result["excluded"]["legacy_calendar"] == 1


async def test_weeks_that_have_not_finished_are_not_scored(db_session, app_role_db, make_tenant):
    tenant, sku = await _seed(db_session, make_tenant)
    run = await _run(db_session, tenant, completed=datetime(2026, 8, 30, tzinfo=UTC), history_end=W1)
    await _fc(db_session, tenant, run, sku, W1, 100)
    await db_session.commit()

    result = await _accuracy(app_role_db, tenant, now=datetime(2026, 9, 3, tzinfo=UTC))

    assert result["excluded"]["period_not_complete"] == 1


@pytest.mark.parametrize(("feed_extends", "expected"), [(True, "scored_as_zero"), (False, "awaiting")])
async def test_a_week_with_no_sales_rows(db_session, app_role_db, make_tenant, feed_extends, expected):
    tenant, sku = await _seed(db_session, make_tenant)
    run = await _run(db_session, tenant, completed=datetime(2026, 8, 30, tzinfo=UTC), history_end=W1)
    await _fc(db_session, tenant, run, sku, W1, 10)
    other = uuid.uuid4()
    when = datetime(2026, 9, 14, tzinfo=UTC) if feed_extends else datetime(2026, 8, 25, tzinfo=UTC)
    await _sale(db_session, tenant, other, when, 5)  # some other SKU shows how far the feed reaches
    await db_session.commit()

    result = await _accuracy(app_role_db, tenant)

    if expected == "scored_as_zero":
        assert result["rows"][0]["weeks"][0]["actual"] == 0
        assert result["rows"][0]["wape"] is None  # no demand: WAPE undefined, not 0 or infinite
    else:
        assert result["rows"] == []
        assert result["excluded"]["awaiting_actuals"] == 1


async def test_backtests_are_reported_separately(db_session, app_role_db, make_tenant):
    tenant, sku = await _seed(db_session, make_tenant)
    run = await _run(db_session, tenant, completed=NOW - timedelta(hours=1), history_end=W1,
                     mode="backtest")
    await _fc(db_session, tenant, run, sku, W1, 100)
    await _fc(db_session, tenant, run, sku, W2, 50)
    await _sale(db_session, tenant, sku, datetime(2026, 9, 1, tzinfo=UTC), 80)
    await _sale(db_session, tenant, sku, datetime(2026, 9, 8, tzinfo=UTC), 50)
    await db_session.commit()

    result = await _accuracy(app_role_db, tenant)

    assert result["rows"] == []  # never production accuracy
    bt = result["backtest"]["runs"][0]
    assert bt["cutoff"] == "2026-08-31"
    assert bt["points"] == 2
    assert bt["wape"] == pytest.approx(round(20 / 130 * 100, 2))


async def test_accuracy_is_tenant_scoped(db_session, app_role_db, make_tenant):
    a, sku_a = await _seed(db_session, make_tenant)
    b, _ = await _seed(db_session, make_tenant)
    run = await _run(db_session, a, completed=datetime(2026, 8, 30, tzinfo=UTC), history_end=W1)
    await _fc(db_session, a, run, sku_a, W1, 100)
    await _sale(db_session, a, sku_a, datetime(2026, 9, 1, tzinfo=UTC), 80)
    await db_session.commit()

    assert (await _accuracy(app_role_db, b))["rows"] == []
    assert len((await _accuracy(app_role_db, a))["rows"]) == 1


async def test_endpoint_returns_the_date_matched_result(client, db_session, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    r = await client.get("/api/v1/forecast/accuracy", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["calendar"] == "W-MON-UTC"
    assert r.json()["rows"] == []
