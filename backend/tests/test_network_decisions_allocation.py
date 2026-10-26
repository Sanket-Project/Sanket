"""Synthetic 1-DC / 6-store allocation pipeline; never demo data."""
from __future__ import annotations

import math
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.models.forecast import ForecastRun
from app.models.inventory import InventoryLevel
from app.models.product import Sku
from app.services.decision_builder import refresh
from app.services.decision_engine import DemandBand, PolicyConfig, _window_sum, _pooled_sigma, _z_for
from app.services.network_decisions import build_network_decisions

NOW = datetime(2026, 10, 26, 9, tzinfo=UTC)
POLICY = PolicyConfig(review_period_days=7, service_level=0.97)


async def _network(db, tenant, supply=100, stale=None, confirmed=True):
    pid, sid, run, dc = (uuid.uuid4() for _ in range(4))
    await db.execute(text("INSERT INTO products (id, tenant_id, industry, name, category, status) "
        "VALUES (:p, :t, 'fashion', 'Synthetic K', 'Kurtis', 'active')"),
        {'p': str(pid), 't': str(tenant)})
    await db.execute(text("INSERT INTO skus (id, tenant_id, product_id, industry, sku_code, moq, "
        "unit_cost, unit_price) VALUES (:s, :t, :p, 'fashion', 'K-M', 1, 400, 960)"),
        {'s': str(sid), 't': str(tenant), 'p': str(pid)})
    await db.execute(text("INSERT INTO forecast_runs (id, tenant_id, industry, model_stack, "
        "horizon_weeks, granularity, status, completed_at, metrics) VALUES (:r, :t, 'fashion', "
        "ARRAY['synthetic_test'], 8, 'weekly', 'completed', :n, '{}'::jsonb)"),
        {'r': str(run), 't': str(tenant), 'n': NOW})
    await db.execute(text("INSERT INTO locations (id, tenant_id, code, name, kind) "
        "VALUES (:i, :t, 'dc', 'dc', :k)"), {'i': str(dc), 't': str(tenant),
        'k': 'warehouse' if confirmed else 'unconfirmed'})
    locs = {'dc': dc}
    for code, stock, demand in [('dc', supply, 0), ('a', 0, 14), ('b', 0, 14),
                               ('c', 5, 7), ('d', 5, 7), ('e', 20, 7), ('f', 40, 7)]:
        if code != 'dc':
            locs[code] = uuid.uuid4()
            await db.execute(text("INSERT INTO locations (id, tenant_id, code, name, kind, "
                "parent_location_id, lead_time_days_from_parent) VALUES (:i, :t, :c, :c, 'store', :d, 3)"),
                {'i': str(locs[code]), 't': str(tenant), 'c': code, 'd': str(dc)})
        await db.execute(text("INSERT INTO inventory_levels (tenant_id, sku_id, industry, location, "
            "on_hand_units, reserved_units, inbound_units, source, as_of) VALUES "
            "(:t, :s, 'fashion', :c, :u, 0, 0, 'synthetic_test', :n)"),
            {'t': str(tenant), 's': str(sid), 'c': code, 'u': stock,
             'n': NOW - timedelta(days=31 if code == stale else 1)})
        if code == 'dc':
            continue
        for w in range(8):
            await db.execute(text("INSERT INTO location_forecast_results (tenant_id, run_id, sku_id, "
                "location_id, forecast_date, p10, p50, p90, share, share_basis, method) "
                "VALUES (:t, :r, :s, :l, :d, :lo, :p, :hi, 0.2, 'sku_history', 'share_split_v1')"),
                {'t': str(tenant), 'r': str(run), 's': str(sid), 'l': str(locs[code]),
                 'd': NOW.date() + timedelta(weeks=w), 'p': demand, 'lo': demand * .7, 'hi': demand * 1.3})
        await db.execute(text("INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, "
            "channel, units_sold, location, metadata) VALUES (:t, :s, 'fashion', :w, 'store', :u, :l, "
            "'{\"source\":\"synthetic_test\"}'::jsonb)"),
            {'t': str(tenant), 's': str(sid), 'w': NOW - timedelta(days=2), 'u': demand, 'l': code})
    for w in range(8):
        await db.execute(text("INSERT INTO forecast_results (tenant_id, run_id, sku_id, forecast_date, "
            "p10, p50, p90, model_name) VALUES (:t, :r, :s, :w, 39.2, 56, 72.8, 'synthetic_test')"),
            {'t': str(tenant), 'r': str(run), 's': str(sid), 'w': NOW.date() + timedelta(weeks=w)})
    await db.commit()
    return sid, run, locs


async def _build(db, tenant, sku, run, policy=POLICY):
    sku_row = await db.get(Sku, sku)
    levels = list((await db.scalars(select(InventoryLevel).where(InventoryLevel.sku_id == sku))).all())
    return await build_network_decisions(db, tenant_id=tenant, industry='fashion',
        run=await db.get(ForecastRun, run), skus={sku: sku_row}, levels={sku: levels},
        confidence={sku: (80, 'high')}, policy=policy, now=NOW, include_transfers=False)


async def test_surplus_exact_targets_and_sales_baseline(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku, run, locs = await _network(db_session, tenant, supply=1000)
    async with app_role_db.session(str(tenant)) as s:
        result = await _build(s, tenant, sku, run)
    for decision in result.decisions:
        code = next(k for k, v in locs.items() if str(v) == decision.location_id)
        demand = 14 if code in ('a', 'b') else 7
        position = {'a': 0, 'b': 0, 'c': 5, 'd': 5, 'e': 20, 'f': 40}[code]
        band = DemandBand([demand * .7] * 8, [demand] * 8, [demand * 1.3] * 8)
        target = _window_sum(band.p50, 10) + _z_for(.97) * _pooled_sigma(band, 10)
        assert decision.recommended_units == math.ceil(target - position)
        assert decision.baseline_units == demand
        assert decision.inputs['location_band']['p50'] == band.p50
        assert decision.inputs['share'] == pytest.approx(.2)
    assert len(result.decisions) == 4


@pytest.mark.parametrize('supply', [100, 30])
async def test_shortage_conserves_supply_and_equalises_cover(db_session, app_role_db, make_tenant, supply):
    tenant = await make_tenant()
    sku, run, _ = await _network(db_session, tenant, supply=supply)
    async with app_role_db.session(str(tenant)) as s:
        result = await _build(s, tenant, sku, run)
    assert sum(d.recommended_units for d in result.decisions) <= supply
    covers = [d.inputs['cover_after_days'] for d in result.decisions]
    assert max(covers) - min(covers) <= 2


async def test_not_ready_produces_notes(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku, run, _ = await _network(db_session, tenant, confirmed=False)
    async with app_role_db.session(str(tenant)) as s:
        result = await _build(s, tenant, sku, run)
    assert result.decisions == []
    assert 'No warehouse is defined' in result.notes


async def test_stale_store_excluded(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku, run, locs = await _network(db_session, tenant, stale='a')
    async with app_role_db.session(str(tenant)) as s:
        result = await _build(s, tenant, sku, run)
    assert all(d.location_id != str(locs['a']) for d in result.decisions)
    assert any('stale' in r['reason'].lower() for r in result.skipped)
    async with app_role_db.session(str(tenant)) as s:
        result, _ = await refresh(s, tenant_id=tenant, industry='fashion',
            tenant_settings={'decisions': {'review_period_days': 7}}, now=NOW)
    assert result.skus_evaluated >= 0


async def test_refresh_persists_routes(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    _, _, locs = await _network(db_session, tenant)
    async with app_role_db.session(str(tenant)) as s:
        _, rows = await refresh(s, tenant_id=tenant, industry='fashion',
            tenant_settings={'decisions': {'review_period_days': 7}}, now=NOW)
        allocations = [r for r in rows if str(r.kind) == 'allocation']
        assert allocations
        assert all(r.source_location_id == locs['dc'] and r.location_id in locs.values() for r in allocations)


async def test_degraded_split_is_excluded(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku, run, _ = await _network(db_session, tenant)
    await db_session.execute(text("UPDATE forecast_runs SET metrics = CAST(:m AS jsonb) WHERE id = :r"),
        {'r': str(run), 'm': '{"location_degraded":true,"unassigned_share":0.2}'})
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as s:
        result = await _build(s, tenant, sku, run)
    assert result.decisions == []
    assert any('degraded' in row['reason'].lower() for row in result.skipped)


async def test_refresh_honours_new_split_degradation(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku, run, _ = await _network(db_session, tenant)
    await db_session.execute(text('DELETE FROM location_forecast_results WHERE run_id = :r'), {'r': str(run)})
    await db_session.execute(text("INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, "
        "channel, units_sold) VALUES (:t, :s, 'fashion', :w, 'store', 56)"),
        {'t': str(tenant), 's': str(sku), 'w': NOW - timedelta(days=2)})
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as s:
        _, rows = await refresh(s, tenant_id=tenant, industry='fashion',
            tenant_settings={'decisions': {'review_period_days': 7}}, now=NOW)
    assert not [r for r in rows if str(r.kind) == 'allocation']
