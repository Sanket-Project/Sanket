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
        confidence={sku: (80, 'high')}, policy=policy, now=NOW, include_transfers=True)


async def _transfer_network(db, tenant):
    sku, run, locs = await _network(db, tenant, supply=0)
    await db.execute(text("UPDATE locations SET lead_time_days_from_parent = 5 WHERE tenant_id = :t "
                          "AND kind = 'store'"), {'t': str(tenant)})
    for loc, units in [('a', 0), ('b', 24), ('c', 12), ('d', 12), ('e', 12), ('f', 80)]:
        await db.execute(text('UPDATE inventory_levels SET on_hand_units = :u WHERE tenant_id = :t '
                              'AND location = :l'), {'t': str(tenant), 'l': loc, 'u': units})
    await db.commit()
    return sku, run, locs


async def test_transfer_moves_f_to_a(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku, run, locs = await _transfer_network(db_session, tenant)
    async with app_role_db.session(str(tenant)) as s:
        result = await _build(s, tenant, sku, run)
    [transfer] = [d for d in result.decisions if d.kind == 'transfer']
    assert (transfer.source_location_id, transfer.location_id) == (str(locs['f']), str(locs['a']))
    assert transfer.recommended_units == math.floor(min(24, 80 - 9.1 * 12 / 7))


async def test_unknown_cost_is_null_with_reason(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku, run, _ = await _transfer_network(db_session, tenant)
    async with app_role_db.session(str(tenant)) as s:
        result = await _build(s, tenant, sku, run)
    [transfer] = [d for d in result.decisions if d.kind == 'transfer']
    assert transfer.economics['net_value'] is None
    assert any(r.text == 'Transfer cost not known' for r in transfer.reasons)


async def test_unprofitable_transfer_is_excluded(db_session, app_role_db, make_tenant):
    from dataclasses import replace
    tenant = await make_tenant()
    sku, run, _ = await _transfer_network(db_session, tenant)
    async with app_role_db.session(str(tenant)) as s:
        result = await _build(s, tenant, sku, run, replace(POLICY, transfer_cost_per_unit=1000))
    assert not [d for d in result.decisions if d.kind == 'transfer']
    assert any('not worth its cost' in r['reason'] for r in result.skipped)


async def test_transfer_requires_two_confirmed_stores(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku, run, _ = await _transfer_network(db_session, tenant)
    await db_session.execute(text("UPDATE locations SET kind = 'unconfirmed' "
        "WHERE tenant_id = :t AND code NOT IN ('dc', 'a')"), {'t': str(tenant)})
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as s:
        result = await _build(s, tenant, sku, run)
    assert not [d for d in result.decisions if d.kind == 'transfer']


async def test_coverage_points_to_real_transfer(db_session, app_role_db, make_tenant):
    from app.services.coverage import coverage
    tenant = await make_tenant()
    await _transfer_network(db_session, tenant)
    async with app_role_db.session(str(tenant)) as s:
        await refresh(s, tenant_id=tenant, industry='fashion',
            tenant_settings={'decisions': {'review_period_days': 7}}, now=NOW)
        result = await coverage(s, tenant_id=tenant, industry='fashion', now=NOW)
    donor = next(l for l in result['skus'][0]['locations'] if l['location'] == 'f')
    assert donor['open_transfer'] == {'units': 24, 'destination': 'a'}


