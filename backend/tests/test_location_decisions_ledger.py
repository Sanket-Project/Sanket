"""Location-aware uniqueness, policy defaults and ROI accounting."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.services.decision_builder import load_policy, persist_decisions, serialize
from app.services.decision_engine import Decision
from app.services.roi import summary


async def _seed(db, tenant):
    pid, sid = uuid.uuid4(), uuid.uuid4()
    await db.execute(text("INSERT INTO products (id, tenant_id, industry, name, category, status) "
        "VALUES (:p, :t, 'fashion', 'K', 'Kurtis', 'active')"), {'p': str(pid), 't': str(tenant)})
    await db.execute(text("INSERT INTO skus (id, tenant_id, product_id, industry, sku_code) "
        "VALUES (:s, :t, :p, 'fashion', 'K-M')"), {'s': str(sid), 't': str(tenant), 'p': str(pid)})
    locs = []
    for code in ['dc', 'a', 'b']:
        lid = uuid.uuid4()
        await db.execute(text("INSERT INTO locations (id, tenant_id, code, name) VALUES (:l, :t, :c, :c)"),
            {'l': str(lid), 't': str(tenant), 'c': code})
        locs.append(lid)
    await db.commit()
    return sid, locs


def _decision(sku, kind, dest=None, source=None):
    return Decision(kind=kind, sku_id=str(sku), sku_code='K-M', headline='Send 10',
        recommended_units=10, baseline_units=20, urgency='high', confidence=80,
        confidence_band='high', economics={'currency': 'INR', 'working_capital_released': 4000},
        inputs={'unit_cost': 400, 'unit_price': 960},
        location_id=str(dest) if dest else None, source_location_id=str(source) if source else None)


async def test_distinct_allocation_destinations_persist(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku, (dc, a, b) = await _seed(db_session, tenant)
    async with app_role_db.session(str(tenant)) as s:
        rows = await persist_decisions(s, tenant_id=tenant, industry='fashion', run_id=None,
            decisions=[_decision(sku, 'allocation', a, dc), _decision(sku, 'allocation', b, dc)])
        assert len(rows) == 2 and all(str(r.status) == 'open' for r in rows)
        assert {serialize(r)['location_id'] for r in rows} == {str(a), str(b)}


async def test_purchase_order_uniqueness_remains(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku, _ = await _seed(db_session, tenant)
    with pytest.raises(IntegrityError):
        async with app_role_db.session(str(tenant)) as s:
            await persist_decisions(s, tenant_id=tenant, industry='fashion', run_id=None,
                decisions=[_decision(sku, 'purchase_order'), _decision(sku, 'purchase_order')])


def test_network_policy_defaults_and_overrides():
    policy = load_policy({'decisions': {'min_transfer_units': 5, 'transfer_cost_per_unit': 12.5}})
    assert policy.min_transfer_units == 5
    assert policy.transfer_cost_per_unit == 12.5
    assert load_policy(None).transfer_cost_per_unit is None


async def test_roi_ignores_network_money(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku, (dc, a, b) = await _seed(db_session, tenant)
    async with app_role_db.session(str(tenant)) as s:
        before = await summary(s, tenant_id=tenant, industry='fashion')
        rows = await persist_decisions(s, tenant_id=tenant, industry='fashion', run_id=None,
            decisions=[_decision(sku, 'allocation', a, dc), _decision(sku, 'transfer', b, a)])
        for row in rows:
            row.status = 'accepted'
            row.decided_at = datetime.now(UTC)
        await s.flush()
        after = await summary(s, tenant_id=tenant, industry='fashion')
    for tier in ('opportunity', 'estimated_at_approval'):
        assert before['tiers'][tier]['lines'] == after['tiers'][tier]['lines']


async def test_network_kind_filter_and_route_codes(client, signed_in_workspace, db_session):
    tenant, headers = await signed_in_workspace()
    sku, (dc, a, _) = await _seed(db_session, tenant)
    await persist_decisions(db_session, tenant_id=tenant, industry='fashion', run_id=None,
                           decisions=[_decision(sku, 'allocation', a, dc)])
    await db_session.commit()
    response = await client.get('/api/v1/decisions?kind=allocation', headers=headers)
    assert response.status_code == 200, response.text
    [row] = response.json()['decisions']
    assert (row['source_location_code'], row['location_code']) == ('dc', 'a')
