import json
from sqlalchemy import text


async def test_client_reports_are_tenant_scoped(client, db_session, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    _, other_headers = await signed_in_workspace()
    report = {"industry": "fashion", "currency": "INR", "sales": {"net_amount": 100}, "limitations": ["No dated SKU sales"]}
    await db_session.execute(text("UPDATE tenants SET settings=settings || CAST(:s AS jsonb) WHERE id=:t"), {"t": tenant, "s": json.dumps({"client_reports": report, "private_setting": "never disclose"})})
    await db_session.commit()
    response = await client.get('/api/v1/analytics/sales/client-reports', headers=headers)
    assert response.status_code == 200
    assert response.json() == {"status": "available", "report": report}
    assert 'private_setting' not in response.text
    empty = await client.get('/api/v1/analytics/sales/client-reports', headers=other_headers)
    assert empty.json() == {"status": "unavailable", "report": None}
    assert (await client.get('/api/v1/analytics/sales/client-reports')).status_code == 401


async def test_client_reports_require_matching_industry(client, db_session, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    await db_session.execute(text("UPDATE tenants SET settings=CAST(:s AS jsonb) WHERE id=:t"), {"t": tenant, "s": json.dumps({"client_reports": {"industry": "electronics", "sales": {"net_amount": 99}}})})
    await db_session.commit()
    response = await client.get('/api/v1/analytics/sales/client-reports', headers=headers)
    assert response.json() == {"status": "unavailable", "report": None}
