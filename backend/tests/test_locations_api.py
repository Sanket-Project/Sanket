"""The location network is readable by members and editable by admins."""
from __future__ import annotations

import uuid

from sqlalchemy import text


async def _location(db, tenant, code):
    lid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO locations (id, tenant_id, code, name) VALUES (:i, :t, :c, :c)"
    ), {"i": str(lid), "t": str(tenant), "c": code})
    return str(lid)


async def test_get_registers_sales_locations(client, signed_in_workspace, db_session):
    tenant, headers = await signed_in_workspace()
    pid, sid = uuid.uuid4(), uuid.uuid4()
    await db_session.execute(text(
        "INSERT INTO products (id, tenant_id, industry, name, category, status) "
        "VALUES (:p, :t, 'fashion', 'K', 'Kurtis', 'active')"
    ), {"p": str(pid), "t": str(tenant)})
    await db_session.execute(text(
        "INSERT INTO skus (id, tenant_id, product_id, industry, sku_code) "
        "VALUES (:s, :t, :p, 'fashion', 'K-M')"
    ), {"s": str(sid), "t": str(tenant), "p": str(pid)})
    await db_session.execute(text(
        "INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, channel, "
        "units_sold, location) VALUES (:t, :s, 'fashion', now(), 'store', 1, 'Alwal')"
    ), {"t": str(tenant), "s": str(sid)})
    await db_session.commit()
    response = await client.get('/api/v1/locations', headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [(l['code'], l['kind']) for l in body['locations']] == [('alwal', 'unconfirmed')]
    assert body['network']['allocation_ready'] is False


async def test_admin_can_confirm_network(client, signed_in_workspace, db_session):
    tenant, headers = await signed_in_workspace()
    dc = await _location(db_session, tenant, 'dc')
    store = await _location(db_session, tenant, 'alwal')
    await db_session.commit()
    response = await client.patch(f'/api/v1/locations/{dc}', headers=headers,
                                  json={'kind': 'warehouse'})
    assert response.status_code == 200, response.text
    response = await client.patch(f'/api/v1/locations/{store}', headers=headers,
        json={'kind': 'store', 'parent_location_id': dc, 'lead_time_days_from_parent': 3})
    assert response.status_code == 200, response.text
    response = await client.get('/api/v1/locations', headers=headers)
    assert response.json()['network']['allocation_ready'] is True


async def test_parent_must_be_warehouse(client, signed_in_workspace, db_session):
    tenant, headers = await signed_in_workspace()
    a = await _location(db_session, tenant, 'a')
    b = await _location(db_session, tenant, 'b')
    await db_session.execute(text("UPDATE locations SET kind = 'store' WHERE tenant_id = :t"),
                              {'t': str(tenant)})
    await db_session.commit()
    response = await client.patch(f'/api/v1/locations/{a}', headers=headers,
                                  json={'parent_location_id': b})
    assert response.status_code == 422, response.text
    assert response.json()['detail'] == 'Parent must be a warehouse of this workspace'


async def test_analyst_cannot_patch(client, signed_in_workspace, db_session):
    from app.config import get_settings
    from app.core.security import hash_password

    tenant, _ = await signed_in_workspace()
    loc = await _location(db_session, tenant, 'a')
    email = f'analyst-{tenant.hex}@test.com'
    await db_session.execute(text(
        "INSERT INTO users (id, tenant_id, email, password_hash, full_name, role, "
        "active_industry, is_active) VALUES (:i, :t, :e, :h, 'Analyst', 'analyst', 'fashion', TRUE)"
    ), {'i': str(uuid.uuid4()), 't': str(tenant), 'e': email,
        'h': hash_password('GoodPass123!', get_settings())})
    slug = await db_session.scalar(text('SELECT slug FROM tenants WHERE id = :t'), {'t': str(tenant)})
    await db_session.commit()
    login = await client.post('/api/v1/auth/dev-login', json={
        'email': email, 'password': 'GoodPass123!', 'tenant_slug': slug})
    assert login.status_code == 200, login.text
    response = await client.patch(f'/api/v1/locations/{loc}', json={'kind': 'warehouse'},
        headers={'Authorization': f"Bearer {login.json()['access_token']}"})
    assert response.status_code == 403, response.text
