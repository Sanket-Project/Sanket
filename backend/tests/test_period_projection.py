import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.services.period_projection import period_rate

NOW = datetime(2026, 10, 27, tzinfo=UTC)


def source(units=298, locations=None, **overrides):
    return {"period_sales": {"start": "2026-01-01", "end": "2026-10-25", "source": "client.xlsx", "units": units, "locations": locations or {"alwal": units}, **overrides}}


def test_inclusive_average_and_location_are_distinct():
    attrs = source(locations={"alwal": 149, "other": 149})
    rate = period_rate(attrs, NOW)
    assert rate["days"] == 298
    assert rate["daily_units"] == 1
    assert rate["weekly_units"] == 7
    assert period_rate(attrs, NOW, " ALWAL ")["weekly_units"] == 3.5
    assert period_rate(attrs, NOW, "missing") is None
    assert "p10" not in rate and "p90" not in rate


@pytest.mark.parametrize("attrs", [{}, source(0), source(-1), source("bad"), source(start="2026-10-26"), source(end="2026-10-28"), source(end="2026-06-01"), source(units=float("nan")), {"period_sales": "bad"}])
def test_unsupported_rates_are_unavailable(attrs):
    assert period_rate(attrs, NOW) is None


async def seed(db, tenant, code, attrs, units=10):
    pid, sid = uuid.uuid4(), uuid.uuid4()
    await db.execute(text("INSERT INTO products (id,tenant_id,industry,name,category) VALUES (:p,:t,'fashion',:n,'Kurtis')"), {"p": pid, "t": tenant, "n": code})
    await db.execute(text("INSERT INTO skus (id,tenant_id,product_id,industry,sku_code,attributes) VALUES (:s,:t,:p,'fashion',:c,CAST(:a AS jsonb))"), {"s": sid, "p": pid, "t": tenant, "c": code, "a": json.dumps(attrs)})
    await db.execute(text("INSERT INTO inventory_levels (tenant_id,sku_id,industry,location,on_hand_units,as_of) VALUES (:t,:s,'fashion','alwal',:u,:now)"), {"t": tenant, "s": sid, "u": units, "now": NOW})
    return sid


async def test_projection_endpoint_isolated_paged_and_not_a_model_forecast(client, db_session, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    other, other_headers = await signed_in_workspace()
    # The test dates remain relative to the clock so the stored report is fresh.
    from datetime import date, timedelta
    end = date.today() - timedelta(days=1)
    attrs = source(start=(end - timedelta(days=297)).isoformat(), end=end.isoformat())
    for code in ["A", "B"]:
        await seed(db_session, tenant, code, attrs)
    await seed(db_session, tenant, "MISSING", {})
    await seed(db_session, tenant, "ZERO", {"period_sales": {**attrs["period_sales"], "units": 0}})
    await db_session.commit()
    r = await client.get('/api/v1/forecasts/average-sales?horizon_weeks=4&limit=1', headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['basis'] == 'period_average'
    assert body['eligible_skus'] == 2 and body['catalogue_skus'] == 4
    assert body['missing_skus'] == 1 and body['unsupported_skus'] == 1
    assert body['projected_units'] == 56
    assert len(body['rows']) == 1 and body['rows'][0]['projected_units'] == 28
    assert body['uncertainty'] is None and body['model_run_id'] is None
    assert body['rows'][0]['locations'][0]['estimated_cover_days'] == 10
    assert body['rows'][0]['locations'][0]['weekly_units'] == 7
    next_page = (await client.get('/api/v1/forecasts/average-sales?horizon_weeks=4&offset=1&limit=1', headers=headers)).json()
    assert next_page['rows'][0]['sku_code'] == 'B'
    foreign = (await client.get('/api/v1/forecasts/average-sales', headers=other_headers)).json()
    assert foreign['status'] == 'unavailable' and foreign['rows'] == []
    assert (await client.get('/api/v1/forecasts/average-sales?horizon_weeks=0', headers=headers)).status_code == 422


async def test_inventory_uses_local_period_average_without_fabricating_history(db_session, app_role_db, make_tenant):
    from app.services.coverage import coverage
    tenant = await make_tenant()
    sid = await seed(db_session, tenant, "MATCHED", source(locations={"alwal": 149, "other": 149}))
    await db_session.execute(text("INSERT INTO inventory_levels (tenant_id,sku_id,industry,location,on_hand_units,as_of) VALUES (:t,:s,'fashion','unmapped',50,:now)"), {"t": tenant, "s": sid, "now": NOW})
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as s:
        result = await coverage(s, tenant_id=tenant, industry='fashion', now=NOW)
        assert await s.scalar(text('SELECT count(*) FROM historical_sales WHERE tenant_id=:t'), {'t': tenant}) == 0
    sku = result['skus'][0]
    assert sku['demand']['basis'] == 'period_average'
    assert sku['demand']['weekly_units'] == 7
    locs = {r['location']: r for r in sku['locations']}
    assert locs['alwal']['demand_basis'] == 'period_average'
    assert locs['alwal']['location_demand']['basis'] == 'period_average'
    assert locs['alwal']['location_demand']['weeks_observed'] == 0
    assert locs['alwal']['cover_days'] == 20
    assert '149 reported units / 298 days' in locs['alwal']['reason']
    assert '0 week(s)' not in locs['alwal']['reason']
    assert locs['unmapped']['cover_days'] is None
    assert locs['unmapped']['demand_basis'] is None


async def test_dated_actuals_and_model_forecasts_take_precedence(db_session, app_role_db, make_tenant):
    from tests.test_inventory_coverage import _weekly_sales, _forecast
    from app.services.coverage import coverage
    tenant = await make_tenant()
    sid = await seed(db_session, tenant, "PRECEDENCE", source())
    await _weekly_sales(db_session, tenant, sid, 20, location="alwal")
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as session:
        row = (await coverage(session, tenant_id=tenant, industry="fashion", now=NOW))['skus'][0]
    assert row['demand']['basis'] == 'trailing_actuals'
    assert row['demand']['weekly_units'] == 20
    assert row['locations'][0]['demand_basis'] == 'trailing_actuals'
    await _forecast(db_session, tenant, sid, completed=NOW, weekly_p50=30)
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as session:
        row = (await coverage(session, tenant_id=tenant, industry="fashion", now=NOW))['skus'][0]
    assert row['demand']['basis'] == 'forecast'
    assert row['demand']['weekly_units'] == 30


async def test_stale_stock_has_no_estimated_cover(db_session, app_role_db, make_tenant):
    from app.services.period_projection import projection
    from datetime import timedelta
    tenant = await make_tenant()
    await seed(db_session, tenant, "STALE", source())
    await db_session.execute(text('UPDATE inventory_levels SET as_of=:d WHERE tenant_id=:t'), {'t': tenant, 'd': NOW-timedelta(days=100)})
    await db_session.commit()
    result = await projection(app_role_db, tenant, 'fashion', now=NOW)
    assert result['rows'][0]['estimated_cover_days'] is None
    assert result['rows'][0]['locations'][0]['estimated_cover_days'] is None
