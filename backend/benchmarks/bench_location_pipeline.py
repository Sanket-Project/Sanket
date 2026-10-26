"""Measure the real location pipeline on a disposable synthetic tenant.

Run with BENCH_DATABASE_URL pointing at sanket_app on a migrated local DB.
The timed services run with tenant RLS enforced. No connector is contacted.
"""
from __future__ import annotations

import argparse
import asyncio
import gc
import json
import os
import time
import uuid
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.core.calendar import current_week_start, week_start_instant
from app.core.database import Database
from app.models.forecast import ForecastRun
from app.models.inventory import InventoryLevel
from app.models.product import Sku
from app.services.decision_builder import persist_decisions
from app.services.decision_engine import PolicyConfig
from app.services.location_forecast import split_run_by_location
from app.services.network_decisions import build_network_decisions


async def seed(session, tenant, count, now):
    """Seed using bounded batches, outside all timing intervals."""
    rng = np.random.default_rng(26102026)
    monday = current_week_start(now)
    run = uuid.uuid4()
    dc, *stores = [uuid.uuid4() for _ in range(7)]
    products = [uuid.uuid4() for _ in range(50)]
    skus = [uuid.uuid4() for _ in range(count)]
    await session.execute(text("INSERT INTO tenants (id, slug, display_name, industry, tier, status) "
        "VALUES (:t, :slug, 'Synthetic location benchmark', 'fashion', 'enterprise', 'active')"),
        {'t': str(tenant), 'slug': f'bench-location-{tenant.hex[:12]}'})
    await session.execute(text("INSERT INTO locations (id, tenant_id, code, name, kind) "
        "VALUES (:i, :t, 'dc', 'DC', 'warehouse')"), {'i': str(dc), 't': str(tenant)})
    for i, loc in enumerate(stores):
        await session.execute(text("INSERT INTO locations (id, tenant_id, code, name, kind, "
            "parent_location_id, lead_time_days_from_parent) VALUES (:i, :t, :c, :c, 'store', :d, 5)"),
            {'i': str(loc), 't': str(tenant), 'c': f'store-{i}', 'd': str(dc)})
    await session.execute(text("INSERT INTO products (id, tenant_id, industry, name, category, status) "
        "VALUES (:p, :t, 'fashion', :c, :c, 'active')"),
        [{'p': str(p), 't': str(tenant), 'c': f'Category-{i}'} for i, p in enumerate(products)])
    for start in range(0, count, 500):
        batch = skus[start:start + 500]
        await session.execute(text("INSERT INTO skus (id, tenant_id, product_id, industry, sku_code, "
            "moq, unit_cost, unit_price, currency) VALUES (:s, :t, :p, 'fashion', :c, 1, 400, 960, 'INR')"),
            [{'s': str(s), 't': str(tenant), 'p': str(products[(start + j) % 50]), 'c': f'BENCH-{start+j:05d}'}
             for j, s in enumerate(batch)])
    await session.execute(text("INSERT INTO forecast_runs (id, tenant_id, industry, model_stack, "
        "horizon_weeks, granularity, status, completed_at, metrics) VALUES (:r, :t, 'fashion', "
        "ARRAY['synthetic_bench'], 8, 'weekly', 'completed', :n, '{}'::jsonb)"),
        {'r': str(run), 't': str(tenant), 'n': now})
    for start in range(0, count, 250):
        sales, stock, forecasts = [], [], []
        for sku in skus[start:start + 250]:
            means = rng.uniform(.2, 8, 6)
            for i, mean in enumerate(means):
                for w in range(1, 13):
                    sales.append({'t': tenant, 's': sku, 'w': week_start_instant(monday - timedelta(weeks=w)),
                                  'u': int(rng.poisson(mean)), 'l': f'store-{i}'})
            for i in range(7):
                stock.append({'tenant_id': tenant, 'sku_id': sku, 'industry': 'fashion',
                    'location': 'dc' if i == 6 else f'store-{i}',
                    'on_hand_units': int(rng.integers(0, 12)) if i < 6 else int(rng.integers(0, 30)),
                    'reserved_units': 0, 'inbound_units': 0, 'as_of': now, 'source': 'synthetic_bench'})
            total = float(sum(means))
            for w in range(8):
                forecasts.append({'t': tenant, 'r': run, 's': sku, 'w': monday + timedelta(weeks=w),
                                  'lo': total * .7, 'p': total, 'hi': total * 1.3})
        await session.execute(text("INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, "
            "channel, units_sold, location, metadata) VALUES (:t, :s, 'fashion', :w, 'store', :u, :l, "
            "jsonb_build_object('source', 'synthetic_bench'))"), sales)
        await session.execute(insert(InventoryLevel), stock)
        await session.execute(text("INSERT INTO forecast_results (tenant_id, run_id, sku_id, forecast_date, "
            "p10, p50, p90, model_name) VALUES (:t, :r, :s, :w, :lo, :p, :hi, 'synthetic_bench')"), forecasts)
        if start % 2500 == 0:
            print(f'Seeded {min(start + 250, count):,}/{count:,} SKUs', flush=True)
    return run


async def run(count: int):
    url = os.environ.get('BENCH_DATABASE_URL')
    cleanup_url = os.environ.get('MIGRATION_DATABASE_URL')
    if not url or not cleanup_url:
        raise SystemExit('BENCH_DATABASE_URL (sanket_app) and MIGRATION_DATABASE_URL (fixture cleanup only) are required')
    db = Database(get_settings().model_copy(update={'database_url': url}))
    await db.assert_tenant_isolation_enforced(strict=True)
    tenant = uuid.uuid4()
    now = datetime.now(UTC)
    timings = []
    try:
        async with db.session(str(tenant)) as s:
            run_id = await seed(s, tenant, count, now)
        async with db.session(str(tenant)) as s:
            start = time.perf_counter()
            summary = await split_run_by_location(s, tenant_id=tenant, industry='fashion', run_id=run_id, now=now)
            elapsed = time.perf_counter() - start
            timings.append({'step': 'split_run_by_location', 'rows': summary.series * 8, 'seconds': elapsed})
        gc.collect()
        async with db.session(str(tenant)) as s:
            skus = {r.id: r for r in (await s.scalars(select(Sku).where(Sku.tenant_id == tenant))).all()}
            levels = {}
            for row in (await s.scalars(select(InventoryLevel).where(InventoryLevel.tenant_id == tenant))).all():
                levels.setdefault(row.sku_id, []).append(row)
            run_row = await s.get(ForecastRun, run_id)
            start = time.perf_counter()
            built = await build_network_decisions(s, tenant_id=tenant, industry='fashion', run=run_row,
                skus=skus, levels=levels, confidence={}, policy=PolicyConfig(review_period_days=7), now=now)
            elapsed = time.perf_counter() - start
            timings.append({'step': 'build_network_decisions', 'rows': len(built.decisions), 'seconds': elapsed})
            start = time.perf_counter()
            persisted = await persist_decisions(s, tenant_id=tenant, industry='fashion', run_id=run_id,
                                               decisions=built.decisions, now=now)
            elapsed = time.perf_counter() - start
            timings.append({'step': 'persist_decisions', 'rows': len(persisted), 'seconds': elapsed})
        for result in timings:
            result['rows_per_second'] = result['rows'] / result['seconds']
            result['over_120_seconds'] = result['seconds'] > 120
            print(json.dumps(result), flush=True)
    finally:
        # Partitioned sales have no tenant FK; remove them explicitly first.
        # Historical sales are append-only to sanket_app. Fixture teardown uses
        # the migration role; none of the timed application services use it.
        cleanup = create_async_engine(cleanup_url)
        try:
            async with cleanup.begin() as s:
                owned = await s.scalar(text("SELECT id FROM tenants WHERE id = :t AND slug LIKE 'bench-%'"), {'t': str(tenant)})
                if owned:
                    for table in ('location_forecast_results', 'forecast_results', 'historical_sales'):
                        await s.execute(text(f'DELETE FROM {table} WHERE tenant_id = :t'), {'t': str(tenant)})
                    await s.execute(text('DELETE FROM tenants WHERE id = :t'), {'t': str(tenant)})
        finally:
            await cleanup.dispose()
        print(f'Cleaned benchmark tenant {tenant}', flush=True)
        await db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--skus', type=int, default=25000)
    args = parser.parse_args()
    if args.skus < 1:
        parser.error('--skus must be positive')
    asyncio.run(run(args.skus))
