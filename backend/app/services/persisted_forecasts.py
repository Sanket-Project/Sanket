"""Bounded reads and atomic admission for durable baseline forecasts."""
from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, text

from app.config import get_settings
from app.models.enums import IndustryCode
from app.models.forecast import ForecastRun
from app.services.decision_builder import latest_completed_run


async def refresh_status(session, tenant_id, industry) -> dict | None:
    row = (await session.execute(text(
        "SELECT * FROM forecast_refreshes WHERE tenant_id=:t AND "
        "(industry=CAST(:i AS industry_code) OR status='pending' OR "
        "(status='running' AND updated_at >= clock_timestamp()-interval '2 minutes')) "
        "ORDER BY (status IN ('pending','running')) DESC, created_at DESC LIMIT 1"
    ), {'t': tenant_id, 'i': industry})).mappings().first()
    if not row:
        return None
    result = dict(row)
    if result['status'] == 'running' and result['updated_at'] < datetime.now(UTC) - timedelta(minutes=2):
        result['status'] = 'failed'
        result['error'] = 'Forecast worker interrupted; retry to recover or regenerate.'
    return result


async def run_is_stale(session, tenant_id, industry, run: ForecastRun | None) -> bool:
    if run is None or run.completed_at is None:
        return True
    if run.completed_at < datetime.now(UTC) - timedelta(seconds=get_settings().forecast_freshness_s):
        return True
    changed = await session.scalar(text(
        'SELECT changed_at FROM forecast_input_changes '
        'WHERE tenant_id=:t AND industry=CAST(:i AS industry_code)'
    ), {'t': tenant_id, 'i': industry})
    meta = run.metrics or {}
    # Compare the revision actually visible to the job, not statement time vs
    # job time: an import can write its marker before the job but commit later.
    if 'input_revision' in meta:
        return (changed.isoformat() if changed else None) != meta['input_revision']
    if meta.get('refresh_id'):
        try:
            refresh_id = uuid.UUID(str(meta['refresh_id']))
        except ValueError:
            return True
        snapshot = (await session.execute(text(
            'SELECT input_revision FROM forecast_refreshes WHERE tenant_id=:t AND id=:r'
        ), {'t': tenant_id, 'r': refresh_id})).first()
        return snapshot is None or changed != snapshot.input_revision
    as_of = meta.get('input_as_of')
    observed = datetime.fromisoformat(as_of) if as_of else run.started_at or run.completed_at
    return bool(changed and changed > observed)


async def read_latest(db, tenant_id, industry, *, view='skus', offset=0, limit=6,
                      search="", run_id: uuid.UUID | None = None) -> dict[str, Any]:
    async with db.session(str(tenant_id)) as session:
        if run_id:
            run = await session.scalar(select(ForecastRun).where(
                ForecastRun.id == run_id, ForecastRun.tenant_id == tenant_id,
                ForecastRun.industry == IndustryCode(industry), ForecastRun.status == 'completed',
                (ForecastRun.metrics['mode'].astext.is_(None)) |
                (ForecastRun.metrics['mode'].astext != 'backtest'),
            ))
            if run is None:
                raise HTTPException(404, 'Forecast run not found')
        else:
            run = await latest_completed_run(session, tenant_id, IndustryCode(industry))
        refresh = await refresh_status(session, tenant_id, industry)
        stale = await run_is_stale(session, tenant_id, industry, run)
        if run is None:
            return {'forecast': None, 'refresh': refresh, 'stale': stale}
        args = {'t': tenant_id, 'r': run.id, 'limit': limit, 'offset': offset,
                'search': f"%{search.strip()}%" if search.strip() else None}
        counts = (await session.execute(text(
            'SELECT count(DISTINCT f.sku_id), count(DISTINCT (f.sku_id,f.forecast_date)) '
            'FROM forecast_results f JOIN skus s ON s.id=f.sku_id '
            'WHERE f.tenant_id=:t AND f.run_id=:r '
            'AND (CAST(:search AS text) IS NULL OR s.sku_code ILIKE CAST(:search AS text) '
            'OR s.description ILIKE CAST(:search AS text))'
        ), args)).one()
        total, points = int(counts[0]), int(counts[1])
        if view == 'summary':
            # Average multiple model rows per SKU first, as decision_builder does.
            query = """
                SELECT 'portfolio' AS sku_id, forecast_date,
                       sum(p10) AS p10, sum(p50) AS p50, sum(p90) AS p90
                FROM (SELECT sku_id, forecast_date, avg(p10) p10, avg(p50) p50, avg(p90) p90
                      FROM forecast_results WHERE tenant_id=:t AND run_id=:r
                      GROUP BY sku_id, forecast_date) f GROUP BY forecast_date ORDER BY forecast_date
            """
            labels = {}
        else:
            # Select the bounded page once. A joined LIMIT/OFFSET subquery can
            # be rescanned for each SKU when import-time planner statistics are
            # stale, turning a small response into minutes of catalogue scans.
            args['sku_ids'] = list((await session.execute(text(
                'SELECT DISTINCT f.sku_id FROM forecast_results f JOIN skus s ON s.id=f.sku_id '
                'WHERE f.tenant_id=:t AND f.run_id=:r '
                'AND (CAST(:search AS text) IS NULL OR s.sku_code ILIKE CAST(:search AS text) '
                'OR s.description ILIKE CAST(:search AS text)) '
                'ORDER BY f.sku_id LIMIT :limit OFFSET :offset'
            ), args)).scalars())
            query = """
                SELECT f.sku_id, f.forecast_date, avg(f.p10) p10, avg(f.p50) p50, avg(f.p90) p90
                FROM forecast_results f
                WHERE f.tenant_id=:t AND f.run_id=:r AND f.sku_id=ANY(CAST(:sku_ids AS uuid[]))
                GROUP BY f.sku_id, f.forecast_date ORDER BY f.sku_id, f.forecast_date
            """
            label_rows = (await session.execute(text("""
                SELECT id, sku_code, description FROM skus
                WHERE tenant_id=:t AND id=ANY(CAST(:sku_ids AS uuid[]))
            """), args)).all()
            labels = {str(r.id): {'code': r.sku_code, 'name': r.description or r.sku_code}
                      for r in label_rows}
        rows = [{'sku_id': str(r.sku_id), 'forecast_date': r.forecast_date.isoformat(),
                 'p10': float(r.p10), 'p50': float(r.p50), 'p90': float(r.p90)}
                for r in (await session.execute(text(query), args)).all()]
        meta = run.metrics or {}
        location_ready = bool(meta.get('location_split_completed_at'))
        if not location_ready:
            location_ready = bool(await session.scalar(text(
                'SELECT EXISTS(SELECT 1 FROM location_forecast_results WHERE tenant_id=:t AND run_id=:r)'
            ), args))
        location_error = meta.get('location_split_error')
        return {'forecast': {
            'run_id': str(run.id), 'rows': rows, 'n_predictions': points,
            'n_series': total, 'total_skus': total, 'horizon_weeks': run.horizon_weeks,
            'completed_at': run.completed_at,
            'age_seconds': max(0, int((datetime.now(UTC) - run.completed_at).total_seconds())),
            'source': meta.get('model') or (run.model_stack[0] if len(run.model_stack) == 1 else 'ensemble'),
            'context_source': meta.get('context_source'), 'calendar': meta.get('calendar'),
            'history_end': meta.get('history_end'), 'first_forecast_week': meta.get('first_forecast_week'),
            'omitted': meta.get('omitted', []), 'omitted_count': meta.get('omitted_count'),
            'offset': offset, 'limit': limit, 'has_more': view == 'skus' and offset + limit < total,
            'sku_labels': labels,
            'location_status': 'ready' if location_ready else 'failed' if location_error else 'pending',
            'location_reason': location_error,
        }, 'refresh': refresh, 'stale': stale}


async def request_refresh(db, queue, tenant_id, industry, *, horizon=26, force=False,
                          force_zero_shot=True) -> dict:
    """The DB reservation is authoritative; arq deduplication is a second guard."""
    async with db.session(str(tenant_id)) as session:
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                              {'key': f'forecast-refresh:{tenant_id}'})
        # A dead worker must not leave an eternal spinner. ML's independent lock
        # still prevents a retry overlapping computation left running upstream.
        await session.execute(text("""
            UPDATE forecast_refreshes SET status='failed', completed_at=clock_timestamp(),
                error='Forecast worker interrupted; retry to recover or regenerate.'
            WHERE tenant_id=:t AND status='running'
              AND updated_at < clock_timestamp() - interval '2 minutes'
        """), {'t': tenant_id})
        active = (await session.execute(text(
            "SELECT * FROM forecast_refreshes WHERE tenant_id=:t AND status IN ('pending','running')"
        ), {'t': tenant_id})).mappings().first()
        if active:
            if (active['status'] == 'pending' and queue is not None and
                    active['updated_at'] < datetime.now(UTC) - timedelta(seconds=30)):
                # Repair a process crash between DB commit and Redis enqueue.
                # A stable arq job ID makes this safe if the job is already queued.
                try:
                    await queue.enqueue_job('run_baseline_forecast', str(active['id']), str(tenant_id),
                                            _job_id=f"forecast-refresh:{active['id']}",
                                            _expires=get_settings().forecast_job_timeout_s * 2)
                except Exception as exc:
                    raise HTTPException(503, 'Forecast refresh queue unavailable; retry later.') from exc
                await session.execute(text(
                    'UPDATE forecast_refreshes SET updated_at=clock_timestamp() WHERE id=:r AND tenant_id=:t'
                ), {'r': active['id'], 't': tenant_id})
            return {'refresh': dict(active), 'stale': True}
        run = await latest_completed_run(session, tenant_id, IndustryCode(industry))
        stale = await run_is_stale(session, tenant_id, industry, run)
        needs_split = run is not None and not (run.metrics or {}).get('location_split_completed_at')
        # A fresh longer run covers a shorter request, but is never relabelled.
        needs_generate = force or stale or (run is not None and run.horizon_weeks < horizon)
        if not needs_generate and not needs_split:
            return {'refresh': await refresh_status(session, tenant_id, industry), 'stale': False}
        if queue is None:
            raise HTTPException(503, 'Forecast refresh queue unavailable; start Redis and the forecast worker.')
        operation = 'generate' if needs_generate else 'split'
        params = {'t': tenant_id, 'i': industry, 'h': horizon, 'z': force_zero_shot,
                  'op': operation, 'r': run.id if run is not None else None}
        row = dict((await session.execute(text("""
            INSERT INTO forecast_refreshes (tenant_id,industry,horizon_weeks,force_zero_shot,operation,base_run_id,input_revision)
            VALUES (:t,CAST(:i AS industry_code),:h,:z,:op,:r,
                (SELECT changed_at FROM forecast_input_changes WHERE tenant_id=:t AND industry=CAST(:i AS industry_code)))
            RETURNING *
        """), params)).mappings().one())
    try:
        await queue.enqueue_job('run_baseline_forecast', str(row['id']), str(tenant_id),
                                _job_id=f"forecast-refresh:{row['id']}",
                                _expires=get_settings().forecast_job_timeout_s * 2)
    except Exception as exc:
        async with db.session(str(tenant_id)) as session:
            await session.execute(text("""
                UPDATE forecast_refreshes SET status='failed',
                    error='Forecast refresh queue rejected the job; retry when Redis is available.',
                    completed_at=clock_timestamp() WHERE id=:id AND tenant_id=:t
            """), {'id': row['id'], 't': tenant_id})
        raise HTTPException(503, 'Forecast refresh queue unavailable; retry later.') from exc
    return {'refresh': row, 'stale': stale}


async def execute_baseline_refresh(ctx: dict, refresh_id: str, tenant_id: str) -> None:
    """Recover a committed ML result before retrying inference; split that exact run."""
    from app.services.forecast_gate import assert_forecastable
    from app.services.location_forecast import ensure_location_split

    db, settings = ctx['db'], get_settings()
    tid, rid = uuid.UUID(tenant_id), uuid.UUID(refresh_id)
    async with db.session(tenant_id) as session:
        row = (await session.execute(text("""
            UPDATE forecast_refreshes SET status='running', updated_at=clock_timestamp(), error=NULL
            WHERE id=:r AND tenant_id=:t AND (status='pending' OR
                (status='running' AND updated_at < clock_timestamp()-interval '2 minutes')) RETURNING *
        """), {'r': rid, 't': tid})).mappings().first()
    if row is None:
        return
    job = dict(row)

    async def heartbeat():
        while True:
            await asyncio.sleep(20)
            async with db.session(tenant_id) as session:
                await session.execute(text(
                    "UPDATE forecast_refreshes SET updated_at=clock_timestamp() "
                    "WHERE id=:r AND tenant_id=:t AND status='running'"
                ), {'r': rid, 't': tid})

    pulse = asyncio.create_task(heartbeat())
    run_id = job['base_run_id'] if job['operation'] == 'split' else None
    try:
        async with db.session(tenant_id) as session:
            await assert_forecastable(session, tenant_id=tid, industry=job['industry'])
            if job['operation'] == 'generate':
                run_id = await session.scalar(text("""
                    SELECT id FROM forecast_runs WHERE tenant_id=:t
                        AND industry=CAST(:i AS industry_code) AND status='completed'
                        AND metrics->>'refresh_id'=:refresh
                    ORDER BY completed_at DESC LIMIT 1
                """), {'t': tid, 'i': job['industry'], 'refresh': refresh_id})
        if run_id is None:
            response = await ctx['http'].post(
                f"{settings.ml_api_url.rstrip('/')}/forecast",
                json={'tenant_id': tenant_id, 'industry': job['industry'],
                      'horizon': job['horizon_weeks'], 'force_zero_shot': job['force_zero_shot'],
                      'refresh_id': refresh_id},
                headers={'Authorization': f'Bearer {settings.ml_service_token_effective}'},
                timeout=settings.forecast_ml_timeout_s,
            )
            response.raise_for_status()
            run_id = uuid.UUID(response.json()['run_id'])
        async with db.session(tenant_id) as session:
            run = await session.scalar(select(ForecastRun).where(
                ForecastRun.id == run_id, ForecastRun.tenant_id == tid,
                ForecastRun.industry == IndustryCode(job['industry']), ForecastRun.status == 'completed',
            ))
            if run is None:
                raise RuntimeError('ML returned no persisted forecast run; no result was published.')
            cutoff = (run.metrics or {}).get('history_end')
            as_of = datetime.fromisoformat(cutoff).replace(tzinfo=UTC) if cutoff else run.completed_at
            await ensure_location_split(session, tenant_id=tid, industry=job['industry'], run=run, now=as_of)
            if job['operation'] == 'generate':
                await session.execute(text("""
                    UPDATE forecast_runs SET metrics=metrics || jsonb_build_object(
                        'input_as_of',CAST(:a AS text),'input_revision',CAST(:revision AS text))
                    WHERE id=:run AND tenant_id=:t
                """), {'run': run_id, 't': tid, 'a': job['created_at'].isoformat(),
                         'revision': job['input_revision'].isoformat() if job['input_revision'] else None})
            await session.execute(text("""
                UPDATE forecast_runs SET metrics=metrics - 'location_split_error' WHERE id=:run AND tenant_id=:t
            """), {'run': run_id, 't': tid})
            await session.execute(text("""
                UPDATE forecast_refreshes SET status='completed',base_run_id=:run,
                    updated_at=clock_timestamp(),completed_at=clock_timestamp() WHERE id=:r AND tenant_id=:t
            """), {'run': run_id, 'r': rid, 't': tid})
    except (Exception, asyncio.CancelledError) as exc:
        error = str(exc)[:500] or 'Forecast worker interrupted; retry to recover the saved result.'
        # Keep service errors useful without leaking an internal HTTP URL/token.
        import httpx
        if isinstance(exc, httpx.HTTPStatusError):
            error = f'Forecast service rejected refresh ({exc.response.status_code}); retry later.'
            try:
                detail = exc.response.json().get('detail')
                if isinstance(detail, str) and exc.response.status_code == 422:
                    error = detail[:500]
            except (ValueError, AttributeError):
                pass
        async with db.session(tenant_id) as session:
            await session.execute(text("""
                UPDATE forecast_refreshes SET status='failed',error=:e,base_run_id=COALESCE(:run,base_run_id),
                    updated_at=clock_timestamp(),completed_at=clock_timestamp() WHERE id=:r AND tenant_id=:t
            """), {'run': run_id, 'e': error, 'r': rid, 't': tid})
            if run_id is not None:
                await session.execute(text("""
                    UPDATE forecast_runs SET metrics=metrics || jsonb_build_object('location_split_error',CAST(:e AS text))
                    WHERE id=:run AND tenant_id=:t
                """), {'run': run_id, 't': tid, 'e': error})
        if isinstance(exc, asyncio.CancelledError):
            raise
    finally:
        pulse.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pulse
