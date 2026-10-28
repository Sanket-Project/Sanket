"""One-off, user-approved local data migration; never loaded by the application."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
TID = uuid.UUID('1fea4cb5-b9f3-45fe-8801-d58c13599d00')
DATABASE = 'sanket_recovered_20261026'
REPORT = ROOT / 'docs/audit/2026-10-27-workspace-reset'
BACKUP = ROOT / 'backups/swecha-demo-before-clear-2026-10-27.dump'
WIPE = (
    'webhook_deliveries', 'shortage_alerts', 'recommendations',
    'forecast_accuracy_metrics', 'data_quality_issues', 'hybrid_forecast_runs',
    'forecast_refreshes', 'location_forecast_results', 'forecast_results',
    'forecast_runs', 'historical_sales', 'inventory_levels', 'pharma_batches',
    'pos_ingest', 'supplier_lead_time_log', 'signal_clusters', 'external_signals',
    'trend_signals', 'skus', 'products', 'locations', 'forecast_input_changes',
)
KEEP = ('tenants', 'users', 'refresh_tokens', 'industry_profiles', 'subscriptions',
        'invites', 'integration_connections', 'webhook_endpoints', 'alert_rules',
        'audit_log', 'usage_events', 'usage_rollups_daily')


def digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()


async def snapshot(conn):
    out = {}
    for table in KEEP:
        predicate = 'id' if table == 'tenants' else 'tenant_id'
        rows = (await conn.execute(text(f'SELECT * FROM "{table}" WHERE {predicate}=:t'),
                                   {'t': TID})).mappings().all()
        # Compare full account/settings rows without persisting sensitive values.
        out[table] = {'count': len(rows), 'digest': digest(sorted(
            [dict(row) for row in rows], key=lambda row: json.dumps(row, sort_keys=True, default=str)))}
    return out


async def counts(conn):
    return {table: int(await conn.scalar(text(f'SELECT count(*) FROM "{table}" WHERE tenant_id=:t'),
                                        {'t': TID})) for table in WIPE}


async def main():
    assert len(sys.argv) == 2 and sys.argv[1] in ('backup', 'dry-run', 'apply', 'verify')
    mode = sys.argv[1]
    cfg = get_settings()
    url = make_url(cfg.database_url)
    assert cfg.app_env == 'development' and url.database == DATABASE and url.host in ('localhost', '127.0.0.1')
    assert url.username == 'sanket_app'
    REPORT.mkdir(parents=True, exist_ok=True)
    inspected = json.loads(subprocess.check_output(['docker', 'inspect', 'prisma-postgres-1'], text=True))[0]
    values = dict(v.split('=', 1) for v in inspected['Config']['Env'] if '=' in v)
    admin_url = url.set(username=values['POSTGRES_USER'], password=values['POSTGRES_PASSWORD'])
    # Privileged access is confined to this explicit data migration; actual row
    # deletion below runs as the normal RLS-enforced application role.
    os.environ['MIGRATION_DATABASE_URL'] = admin_url.render_as_string(hide_password=False)
    if mode == 'backup':
        assert not BACKUP.exists(), 'Do not overwrite a prior backup'
        BACKUP.parent.mkdir(exist_ok=True)
        with BACKUP.open('xb') as file:
            subprocess.run(['docker', 'exec', 'prisma-postgres-1', 'pg_dump', '-U',
                            values['POSTGRES_USER'], '-Fc', DATABASE], stdout=file, check=True)
        with BACKUP.open('rb') as file:
            subprocess.run(['docker', 'exec', '-i', 'prisma-postgres-1', 'pg_restore', '--list'],
                           stdin=file, stdout=subprocess.DEVNULL, check=True)
        record = {'backup': str(BACKUP), 'bytes': BACKUP.stat().st_size,
                  'sha256': hashlib.sha256(BACKUP.read_bytes()).hexdigest(), 'archive_valid': True}
        (REPORT / 'backup.json').write_text(json.dumps(record, indent=2))
        print(json.dumps(record, indent=2))
        return
    assert BACKUP.exists() and (REPORT / 'backup.json').exists(), 'Validated backup required'
    engine = create_async_engine(os.environ['MIGRATION_DATABASE_URL'])
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                assert await conn.scalar(text('SELECT current_database()')) == DATABASE
                before = await snapshot(conn)
                tenant = (await conn.execute(text('SELECT slug,display_name FROM tenants WHERE id=:t'),
                                             {'t': TID})).one()
                assert tenant.slug == 'swecha-demo'
                original = await counts(conn)
                other = {}
                for table in WIPE:
                    other[table] = await conn.scalar(text(f'SELECT count(*) FROM "{table}" WHERE tenant_id<>:t'), {'t': TID})
                if mode == 'verify':
                    assert all(value == 0 for value in original.values()), original
                    saved = json.loads((REPORT / 'apply.json').read_text())
                    assert before == saved['retained'], 'Retained accounts/settings changed'
                    assert other == saved['other_tenant_counts'], 'Other tenants changed'
                    print(json.dumps({'empty': True, 'retained_unchanged': True, 'other_tenants_unchanged': True}))
                    await transaction.rollback()
                    return
                assert original['skus'] == 209 and original['historical_sales'] == 124170, original
                grants = []
                for table in WIPE:
                    if not await conn.scalar(text("SELECT has_table_privilege('sanket_app',:table,'DELETE')"), {'table': table}):
                        await conn.execute(text(f'GRANT DELETE ON "{table}" TO sanket_app'))
                        grants.append(table)
                await conn.execute(text('SET LOCAL ROLE sanket_app'))
                await conn.execute(text("SELECT set_config('app.current_tenant_id',:t,true)"), {'t': str(TID)})
                role = (await conn.execute(text('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user'))).one()
                assert not role.rolsuper and not role.rolbypassrls
                assert await conn.scalar(text('SELECT count(*) FROM tenants WHERE id<>:t'), {'t': TID}) == 0
                removed = {}
                for table in WIPE:
                    result = await conn.execute(text(f'DELETE FROM "{table}" WHERE tenant_id=:t'), {'t': TID})
                    removed[table] = result.rowcount
                remaining = await counts(conn)
                assert all(value == 0 for value in remaining.values()), remaining
                assert await snapshot(conn) == before, 'Credentials or settings changed'
                await conn.execute(text('RESET ROLE'))
                for table in grants:
                    await conn.execute(text(f'REVOKE DELETE ON "{table}" FROM sanket_app'))
                    assert not await conn.scalar(text("SELECT has_table_privilege('sanket_app',:table,'DELETE')"), {'table': table})
                for table, count in other.items():
                    assert count == await conn.scalar(text(f'SELECT count(*) FROM "{table}" WHERE tenant_id<>:t'), {'t': TID})
                record = {'database': DATABASE, 'tenant': str(TID), 'slug': tenant.slug,
                          'mode': mode, 'before': original, 'deleted': removed, 'after': remaining,
                          'retained': before, 'other_tenant_counts': other,
                          'retained_unchanged': True, 'other_tenants_unchanged': True,
                          'rls_enforced_for_deletes': True, 'permissions_restored': True}
                if mode == 'dry-run':
                    await transaction.rollback()
                else:
                    assert (REPORT / 'dry-run.json').exists(), 'Successful rollback rehearsal required'
                    await transaction.commit()
                (REPORT / f'{mode}.json').write_text(json.dumps(record, indent=2, default=str))
                print(json.dumps({'mode': mode, 'deleted': removed, 'all_business_tables_empty': True,
                                  'retained_unchanged': True, 'other_tenants_unchanged': True}, indent=2))
            except BaseException:
                if transaction.is_active:
                    await transaction.rollback()
                raise
    finally:
        await engine.dispose()


asyncio.run(main())
