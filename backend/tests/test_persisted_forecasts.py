"""Saved forecasts are reads; slow inference belongs to the durable worker."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from sqlalchemy import text

from tests.test_location_forecast_split import _forecast, _sku


async def test_latest_empty_does_not_infer(client, signed_in_workspace):
    _, headers = await signed_in_workspace()
    r = await client.get('/api/v1/forecasts/latest', headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == {'forecast': None, 'refresh': None, 'stale': True}


async def test_latest_saved_pages_summary_and_backtest_exclusion(
    client, db_session, signed_in_workspace, monkeypatch,
):
    tenant, headers = await signed_in_workspace()
    now = datetime.now(UTC)
    a = await _sku(db_session, tenant, 'A')
    b = await _sku(db_session, tenant, 'B')
    run = await _forecast(db_session, tenant, a, completed=now, weekly_p50=10)
    await db_session.execute(text(
        "INSERT INTO forecast_results (tenant_id,run_id,sku_id,forecast_date,p10,p50,p90,model_name) "
        "SELECT tenant_id,run_id,:s,forecast_date,p10*2,p50*2,p90*2,model_name "
        "FROM forecast_results WHERE run_id=:r"
    ), {'s': b, 'r': run})
    await _forecast(db_session, tenant, a, completed=now+timedelta(seconds=1),
                    weekly_p50=999, mode='backtest')
    await db_session.commit()
    post = AsyncMock(side_effect=AssertionError('Read must not call ML'))
    monkeypatch.setattr('app.routers.forecasts._post_to_ml', post)
    r = await client.get('/api/v1/forecasts/latest?limit=1', headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    f = data['forecast']
    assert f['run_id'] == str(run)
    assert f['total_skus'] == 2
    assert f['has_more'] is True
    assert len(f['rows']) == 8
    assert f['horizon_weeks'] == 8
    assert f['age_seconds'] >= 0
    assert f['completed_at']
    assert data['stale'] is False
    assert f['location_status'] == 'pending'
    page = (await client.get('/api/v1/forecasts/latest', headers=headers,
                            params={'limit': 1, 'offset': 1, 'run_id': str(run)})).json()['forecast']
    assert {x['sku_id'] for x in f['rows']}.isdisjoint(x['sku_id'] for x in page['rows'])
    summary = (await client.get('/api/v1/forecasts/latest?view=summary', headers=headers)).json()['forecast']
    assert len(summary['rows']) == 8
    assert all(x['p50'] == 30 for x in summary['rows'])
    post.assert_not_called()


async def test_latest_cannot_pin_another_tenants_run(client, db_session, signed_in_workspace):
    tenant, _ = await signed_in_workspace()
    _, headers = await signed_in_workspace()
    sku = await _sku(db_session, tenant)
    run = await _forecast(db_session, tenant, sku, completed=datetime.now(UTC), weekly_p50=4)
    await db_session.commit()
    r = await client.get(f'/api/v1/forecasts/latest?run_id={run}', headers=headers)
    assert r.status_code == 404, r.text


async def test_refresh_deduplicates_concurrent_requests(client, signed_in_workspace, monkeypatch):
    from app.routers import forecasts
    _, headers = await signed_in_workspace()
    queue = AsyncMock()
    monkeypatch.setattr(forecasts, '_forecast_queue', lambda request: queue)
    replies = await asyncio.gather(*[
        client.post('/api/v1/forecasts/refresh', headers=headers, json={'horizon': 12})
        for _ in range(4)
    ])
    assert all(r.status_code == 202 for r in replies), [r.text for r in replies]
    ids = {r.json()['refresh']['id'] for r in replies}
    assert len(ids) == 1
    assert queue.enqueue_job.await_count == 1


async def test_missing_queue_is_honest(client, signed_in_workspace):
    _, headers = await signed_in_workspace()
    r = await client.post('/api/v1/forecasts/refresh', headers=headers, json={})
    assert r.status_code == 503, r.text
    assert 'queue' in r.json()['detail'].lower()
    latest = (await client.get('/api/v1/forecasts/latest', headers=headers)).json()
    assert latest['refresh'] is None


async def test_failed_enqueue_is_recorded(client, signed_in_workspace, monkeypatch):
    from app.routers import forecasts
    _, headers = await signed_in_workspace()
    queue = AsyncMock()
    queue.enqueue_job.side_effect = RuntimeError('redis unavailable')
    monkeypatch.setattr(forecasts, '_forecast_queue', lambda request: queue)
    r = await client.post('/api/v1/forecasts/refresh', headers=headers, json={})
    assert r.status_code == 503, r.text
    latest = (await client.get('/api/v1/forecasts/latest', headers=headers)).json()
    assert latest['refresh']['status'] == 'failed'
    assert 'queue' in latest['refresh']['error'].lower()


async def test_fresh_run_does_not_enqueue_unless_forced(client, db_session, signed_in_workspace, monkeypatch):
    from app.routers import forecasts
    tenant, headers = await signed_in_workspace()
    sku = await _sku(db_session, tenant)
    run = await _forecast(db_session, tenant, sku, completed=datetime.now(UTC), weekly_p50=4)
    await db_session.execute(text("UPDATE forecast_runs SET metrics=metrics || "
                                 "'{\"location_split_completed_at\":\"2026-10-26\"}'::jsonb WHERE id=:r"), {'r': run})
    await db_session.commit()
    queue = AsyncMock()
    monkeypatch.setattr(forecasts, '_forecast_queue', lambda request: queue)
    r = await client.post('/api/v1/forecasts/refresh', headers=headers, json={'horizon': 8})
    assert r.status_code == 202, r.text
    queue.enqueue_job.assert_not_called()
    r = await client.post('/api/v1/forecasts/refresh', headers=headers, json={'horizon': 8, 'force': True})
    assert r.status_code == 202, r.text
    queue.enqueue_job.assert_awaited_once()


async def test_refresh_state_rls(app_role_db, make_tenant):
    a, b = await make_tenant(), await make_tenant()
    async with app_role_db.session(str(a)) as s:
        await s.execute(text("INSERT INTO forecast_refreshes (tenant_id,industry,horizon_weeks) "
                             "VALUES (:t,'fashion',12)"), {'t': a})
    async with app_role_db.session(str(b)) as s:
        assert await s.scalar(text('SELECT count(*) FROM forecast_refreshes')) == 0


async def test_sales_import_marks_saved_forecast_stale(client, db_session, app_role_db, signed_in_workspace):
    from app.models.enums import IndustryCode
    from app.services.integrations import file_import as fi
    tenant, headers = await signed_in_workspace()
    sku = await _sku(db_session, tenant)
    await _forecast(db_session, tenant, sku, completed=datetime.now(UTC), weekly_p50=4)
    await db_session.commit()
    assert (await client.get('/api/v1/forecasts/latest', headers=headers)).json()['stale'] is False
    columns, records = fi.parse_table('sales.csv', b'sku,date,quantity\nKURTI-M,2026-10-19,7')
    await fi.import_rows(db=app_role_db, tenant_id=tenant, industry=IndustryCode.fashion,
                         kind='sales', headers=columns, records=records)
    assert (await client.get('/api/v1/forecasts/latest', headers=headers)).json()['stale'] is True


async def test_worker_recovers_committed_ml_run_without_reinference(app_role_db, db_session, make_tenant, monkeypatch):
    from app.services.persisted_forecasts import execute_baseline_refresh, request_refresh
    tenant = await make_tenant()
    queued = await request_refresh(app_role_db, AsyncMock(), tenant, 'fashion', horizon=8)
    refresh_id = queued['refresh']['id']
    sku = await _sku(db_session, tenant)
    run = await _forecast(db_session, tenant, sku, completed=datetime.now(UTC), weekly_p50=4)
    await db_session.execute(text("UPDATE forecast_runs SET metrics=metrics || "
                                 "jsonb_build_object('refresh_id',CAST(:f AS text)) WHERE id=:r"),
                             {'r': run, 'f': str(refresh_id)})
    await db_session.commit()
    from app.services import location_forecast
    ensure = location_forecast.ensure_location_split

    async def split_with_heartbeat_available(*args, **kwargs):
        # Location expansion can take minutes. The independent heartbeat must
        # remain able to update the refresh row while the split is in progress.
        async with app_role_db.session(str(tenant)) as s:
            await s.execute(text('SELECT id FROM forecast_refreshes WHERE id=:f FOR UPDATE NOWAIT'),
                            {'f': refresh_id})
        return await ensure(*args, **kwargs)

    monkeypatch.setattr(location_forecast, 'ensure_location_split', split_with_heartbeat_available)
    http = AsyncMock(side_effect=AssertionError('Recovery must not re-infer'))
    await execute_baseline_refresh({'db': app_role_db, 'http': http}, str(refresh_id), str(tenant))
    async with app_role_db.session(str(tenant)) as s:
        row = (await s.execute(text('SELECT * FROM forecast_refreshes WHERE id=:f'),
                                {'f': refresh_id})).mappings().one()
        assert row['status'] == 'completed'
        assert row['base_run_id'] == run
        metrics = await s.scalar(text('SELECT metrics FROM forecast_runs WHERE id=:r'), {'r': run})
        assert metrics['location_split_completed_at']
    http.post.assert_not_called()


async def test_worker_failure_keeps_saved_forecast(app_role_db, db_session, make_tenant):
    from app.services.persisted_forecasts import (
        execute_baseline_refresh,
        read_latest,
        request_refresh,
    )
    tenant = await make_tenant()
    sku = await _sku(db_session, tenant)
    run = await _forecast(db_session, tenant, sku, completed=datetime.now(UTC), weekly_p50=4)
    await db_session.commit()
    queued = await request_refresh(app_role_db, AsyncMock(), tenant, 'fashion', force=True)
    http = AsyncMock()
    http.post.side_effect = RuntimeError('ML test failure')
    await execute_baseline_refresh({'db': app_role_db, 'http': http},
                                    str(queued['refresh']['id']), str(tenant))
    data = await read_latest(app_role_db, tenant, 'fashion')
    assert data['forecast']['run_id'] == str(run)
    assert data['refresh']['status'] == 'failed'
    assert 'ML test failure' in data['refresh']['error']


async def test_dead_worker_is_reported_and_retryable(app_role_db, make_tenant):
    from app.services.persisted_forecasts import read_latest, request_refresh
    tenant = await make_tenant()
    queue = AsyncMock()
    queued = await request_refresh(app_role_db, queue, tenant, 'fashion')
    async with app_role_db.session(str(tenant)) as s:
        await s.execute(text("UPDATE forecast_refreshes SET status='running', "
                             "updated_at=clock_timestamp()-interval '3 minutes' WHERE id=:r"),
                        {'r': queued['refresh']['id']})
    data = await read_latest(app_role_db, tenant, 'fashion')
    assert data['refresh']['status'] == 'failed'
    assert 'interrupted' in data['refresh']['error']
    retry = await request_refresh(app_role_db, queue, tenant, 'fashion', force=True)
    assert retry['refresh']['status'] == 'pending'
    assert retry['refresh']['id'] != queued['refresh']['id']


async def test_pending_reservation_recovers_missing_enqueue(app_role_db, make_tenant):
    from app.services.persisted_forecasts import request_refresh
    tenant = await make_tenant()
    queue = AsyncMock()
    queued = await request_refresh(app_role_db, queue, tenant, 'fashion')
    async with app_role_db.session(str(tenant)) as s:
        await s.execute(text("UPDATE forecast_refreshes SET updated_at=clock_timestamp()-interval '1 minute' "
                             "WHERE id=:r"), {'r': queued['refresh']['id']})
    retried = await request_refresh(app_role_db, queue, tenant, 'fashion')
    assert retried['refresh']['id'] == queued['refresh']['id']
    assert queue.enqueue_job.await_count == 2
    assert queue.enqueue_job.await_args.kwargs['_job_id'] == f"forecast-refresh:{queued['refresh']['id']}"


async def test_reads_report_actual_persisted_point_count(client, db_session, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    sku = await _sku(db_session, tenant)
    run = await _forecast(db_session, tenant, sku, completed=datetime.now(UTC), weekly_p50=4)
    await db_session.execute(text("DELETE FROM forecast_results WHERE run_id=:r "
                                 "AND forecast_date='2026-10-26'"), {'r': run})
    await db_session.commit()
    f = (await client.get('/api/v1/forecasts/latest', headers=headers)).json()['forecast']
    assert f['n_predictions'] == 7


async def test_connector_sales_invalidate_forecasts(app_role_db, db_session, make_tenant):
    from app.services.persisted_forecasts import read_latest
    from tests.test_location_forecast_split import _weekly_sales
    tenant = await make_tenant()
    sku = await _sku(db_session, tenant)
    await _forecast(db_session, tenant, sku, completed=datetime.now(UTC), weekly_p50=4)
    await db_session.commit()
    assert (await read_latest(app_role_db, tenant, 'fashion'))['stale'] is False
    async with app_role_db.session(str(tenant)) as s:
        await _weekly_sales(s, tenant, sku, 10, location='alwal')
    assert (await read_latest(app_role_db, tenant, 'fashion'))['stale'] is True


async def test_other_industry_can_observe_tenant_slot_until_free(app_role_db, make_tenant):
    from app.services.persisted_forecasts import read_latest, request_refresh
    tenant = await make_tenant()
    queued = await request_refresh(app_role_db, AsyncMock(), tenant, 'fashion')
    waiting = await read_latest(app_role_db, tenant, 'electronics')
    assert waiting['refresh']['id'] == queued['refresh']['id']
    assert waiting['refresh']['industry'] == 'fashion'
    async with app_role_db.session(str(tenant)) as s:
        await s.execute(text("UPDATE forecast_refreshes SET status='completed' WHERE tenant_id=:t"), {'t': tenant})
    assert (await read_latest(app_role_db, tenant, 'electronics'))['refresh'] is None


async def test_import_committed_after_forecast_snapshot_is_stale(app_role_db, db_session, make_tenant):
    from app.services.persisted_forecasts import read_latest, request_refresh
    from tests.test_location_forecast_split import _weekly_sales
    tenant = await make_tenant()
    sku = await _sku(db_session, tenant)
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as importing:
        # The marker's timestamp precedes the job, but these sales remain
        # invisible to the model's other connection until the transaction exits.
        await _weekly_sales(importing, tenant, sku, 10, location='alwal')
        queued = await request_refresh(app_role_db, AsyncMock(), tenant, 'fashion', horizon=8)
        run = await _forecast(db_session, tenant, sku, completed=datetime.now(UTC), weekly_p50=4)
        await db_session.execute(text("UPDATE forecast_runs SET metrics=metrics || "
                                     "jsonb_build_object('refresh_id',CAST(:f AS text)) WHERE id=:r"),
                                 {'r': run, 'f': str(queued['refresh']['id'])})
        await db_session.commit()
    assert (await read_latest(app_role_db, tenant, 'fashion'))['stale'] is True
