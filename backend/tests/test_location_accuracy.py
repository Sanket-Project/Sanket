from app.services.forecast_accuracy import mase

import uuid
from datetime import UTC, date, datetime, timedelta
import pytest
from sqlalchemy import text
from app.services.forecast_accuracy import compute_location_accuracy


async def test_location_mase_is_weighted_by_units(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    run, sku = uuid.uuid4(), uuid.uuid4()
    first = date(2026, 10, 5)
    await db_session.execute(text(
        "INSERT INTO forecast_runs (id, tenant_id, industry, model_stack, horizon_weeks, "
        "granularity, status, completed_at) VALUES (:r, :t, 'fashion', ARRAY['test'], 2, "
        "'weekly', 'completed', '2026-10-05T00:00:00Z')"
    ), {'r': str(run), 't': str(tenant)})
    for code, factor, predicted in [('a', 1, 20), ('b', 2, 30)]:
        lid = uuid.uuid4()
        await db_session.execute(text(
            "INSERT INTO locations (id, tenant_id, code, name) VALUES (:l, :t, :c, :c)"
        ), {'l': str(lid), 't': str(tenant), 'c': code})
        for i in range(-12, 2):
            week = first + timedelta(weeks=i)
            await db_session.execute(text(
                "INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, channel, "
                "units_sold, location) VALUES (:t, :s, 'fashion', :w, 'store', :u, :l)"
            ), {'t': str(tenant), 's': str(sku), 'w': datetime.combine(week, datetime.min.time(), UTC),
                'u': (i + 20) * factor, 'l': code})
        for i in range(2):
            await db_session.execute(text(
                "INSERT INTO location_forecast_results (tenant_id, run_id, sku_id, location_id, "
                "forecast_date, p10, p50, p90, share, share_basis, method) VALUES "
                "(:t, :r, :s, :l, :w, :p, :p, :p, 0.5, 'sku_history', 'share_split_v1')"
            ), {'t': str(tenant), 'r': str(run), 's': str(sku), 'l': str(lid),
                'w': first + timedelta(weeks=i), 'p': predicted})
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as session:
        result = await compute_location_accuracy(session, tenant_id=tenant, industry='fashion', run_id=run)
    rows = result['locations']
    assert [r['location'] for r in rows] == ['a', 'b']
    assert all(r['mase'] is not None and r['weeks'] == 2 for r in rows)
    assert result['weighted_mase'] == pytest.approx(
        sum(r['mase'] * r['units'] for r in rows) / sum(r['units'] for r in rows), abs=1e-4)


def test_mase_perfect_forecast_is_zero():
    assert mase([5, 6], [5, 6], history=[1, 2, 3, 4, 5], season=1) == 0.0


def test_mase_equals_naive_is_one():
    hist = [1, 2, 3, 4, 5]
    assert mase([7], [6], history=hist, season=1) == 1.0


def test_mase_flat_history_is_undefined():
    assert mase([1], [2], history=[3, 3, 3], season=1) is None
