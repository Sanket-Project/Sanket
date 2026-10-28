from datetime import UTC, datetime

from sqlalchemy import text

from app.models.enums import IndustryCode
from app.models.sales import HistoricalSale
from tests.test_sales_currency import _sku


async def test_delete_all_is_scoped_and_preserves_catalogue(client, db_session, signed_in_workspace, app_role_db):
    tenant, headers = await signed_in_workspace()
    other, other_headers = await signed_in_workspace()
    sku = await _sku(db_session, tenant, 'DELETE-SALES', 'INR')
    other_sku = await _sku(db_session, other, 'KEEP-SALES', 'INR')
    for owner, item in [(tenant, sku), (other, other_sku)]:
        db_session.add(HistoricalSale(tenant_id=owner, sku_id=item, industry=IndustryCode.fashion,
            sale_time=datetime.now(UTC), channel='test', units_sold=3, returns=0))
    await db_session.execute(text("UPDATE tenants SET settings=settings || CAST(:settings AS jsonb) WHERE id=:t"), {'t': tenant, 'settings': '{"client_reports":{"industry":"fashion"},"keep":true}'})
    await db_session.commit()
    app = client._transport.app
    original_db = app.state.db
    app.state.db = app_role_db
    try:
        response = await client.delete('/api/v1/analytics/sales/all', headers=headers)
    finally:
        app.state.db = original_db
    assert response.status_code == 200, response.text
    assert response.json()['deleted'] == 1
    assert (await client.get('/api/v1/analytics/sales/summary', headers=other_headers)).json()['year']['units_sold'] == 3
    settings = await db_session.scalar(text('SELECT settings FROM tenants WHERE id=:t'), {'t': tenant})
    assert settings['keep']
    assert 'client_reports' not in settings
    assert await db_session.scalar(text('SELECT count(*) FROM skus WHERE id=:s'), {'s': sku}) == 1


async def test_delete_all_requires_authentication(client):
    assert (await client.delete('/api/v1/analytics/sales/all')).status_code == 401


async def test_delete_all_rechecks_demoted_admin(client, db_session, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    await db_session.execute(text("UPDATE users SET role='viewer' WHERE tenant_id=:t"), {'t': tenant})
    await db_session.commit()
    assert (await client.delete('/api/v1/analytics/sales/all', headers=headers)).status_code == 403


async def test_delete_removes_v2_identities_so_import_can_be_replayed(client, db_session, signed_in_workspace, app_role_db):
    from pathlib import Path

    from app.services.integrations.v2.contracts import parse_v2_csv
    from app.services.integrations.v2.event_registry import EventRegistryService
    from app.services.integrations.v2.sales_returns import validate_return_row, validate_sale_row

    tenant, headers = await signed_in_workspace()
    samples = Path(__file__).resolve().parents[2] / 'docs/audit/2026-10-28-retail-v2/samples'
    sale = validate_sale_row(parse_v2_csv((samples / 'sales_v2_SAMPLE_ONLY.csv').read_bytes())[1][0])
    ret = validate_return_row(parse_v2_csv((samples / 'returns_v2_SAMPLE_ONLY.csv').read_bytes())[1][0])
    await _sku(db_session, tenant, sale.sku_code, 'INR')
    await db_session.commit()
    registry = EventRegistryService()
    async with app_role_db.session(str(tenant)) as session:
        await registry.post_sales_group(session, tenant, [sale])
        await registry.post_return_event(session, tenant, ret)
    app = client._transport.app
    original = app.state.db
    app.state.db = app_role_db
    try:
        response = await client.delete('/api/v1/analytics/sales/all', headers=headers)
    finally:
        app.state.db = original
    assert response.status_code == 200, response.text
    async with app_role_db.session(str(tenant)) as session:
        for query in ('SELECT count(*) FROM v2_sales_events WHERE tenant_id=:t',
                      'SELECT count(*) FROM v2_return_events WHERE tenant_id=:t',
                      'SELECT count(*) FROM event_identity_registry WHERE tenant_id=:t'):
            assert await session.scalar(text(query), {'t': tenant}) == 0
        assert (await registry.post_sales_group(session, tenant, [sale]))['inserted'] == 1
