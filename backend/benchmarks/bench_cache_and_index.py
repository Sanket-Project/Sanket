"""Benchmark the two measured backend wins: covering index + response cache.

1. Covering index (migration 0014): times the sales-summary aggregate with the
   covering ``idx_hsales_agg_covering`` (index-only scan) vs the pre-migration
   ``idx_hsales_industry`` (index scan + heap fetch for the summed columns).

2. Response cache (app/core/cache.py): times a Redis cache *hit* (GET + JSON
   decode of the rendered response) against the cost of recomputing the summary.
   This is the dominant real-world win because dashboards poll on an interval.

Usage:
    cd backend
    DATABASE_URL=postgresql+asyncpg://...:5432/sanket \\
    REDIS_URL=redis://localhost:6379/0 \\
        python -m benchmarks.bench_cache_and_index --rows 200000 --repeat 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from benchmarks.bench_sales_summary import _old_summary as _summary_seq
from benchmarks.bench_sales_summary import _seed


def _med(xs):
    return statistics.median(xs)


async def _time_summary(Session, tenant_id, industry, now, repeat):
    samples = []
    for _ in range(repeat):
        async with Session() as s:
            await s.execute(text("SELECT set_config('app.bypass_rls', 'true', true)"))
            t0 = time.perf_counter()
            await _summary_seq(s, tenant_id, industry, now)
            samples.append((time.perf_counter() - t0) * 1000)
    return _med(samples)


async def run(rows: int, repeat: int) -> None:
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("BENCH_DATABASE_URL")
    redis_url = os.environ.get("REDIS_URL") or os.environ.get("BENCH_REDIS_URL")
    if not db_url:
        print("[SKIP] DATABASE_URL not set")
        return

    engine = create_async_engine(db_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id, industry, now = uuid.uuid4(), "fashion", datetime.now(UTC)

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.bypass_rls', 'true', true)"))
            await conn.execute(
                text("SELECT set_config('app.current_tenant_id', :t, true)"),
                {"t": str(tenant_id)},
            )
            print(f"Seeding {rows:,} rows ...")
            await _seed(conn, tenant_id, industry, rows)

        # VACUUM so the visibility map is set — index-only scans require it, and
        # production autovacuum keeps it current. Without this, freshly bulk-
        # loaded rows force heap visibility checks that negate the covering index.
        async with engine.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn.execute(text("VACUUM ANALYZE historical_sales"))

        # ── 1. Covering index vs pre-migration index ─────────────────────────
        print("\n[1] Covering index (index-only) vs idx_hsales_industry (heap fetch)")
        cover_med = await _time_summary(Session, tenant_id, industry, now, repeat)
        print(f"  WITH idx_hsales_agg_covering   median={cover_med:7.2f} ms")

        async with engine.begin() as conn:
            await conn.execute(text("DROP INDEX IF EXISTS idx_hsales_agg_covering"))
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_hsales_industry "
                    "ON historical_sales (tenant_id, industry, sale_time DESC)"
                )
            )
            await conn.execute(text("ANALYZE historical_sales"))
        plain_med = await _time_summary(Session, tenant_id, industry, now, repeat)
        print(f"  WITH idx_hsales_industry       median={plain_med:7.2f} ms")
        if cover_med > 0:
            print(
                f"  -> covering index: {plain_med / cover_med:.2f}x "
                f"({(1 - cover_med / plain_med) * 100:+.1f}% latency)"
            )

        # restore production index state
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_hsales_agg_covering "
                    "ON historical_sales (tenant_id, industry, sale_time) "
                    "INCLUDE (units_sold, gross_revenue, net_revenue, returns)"
                )
            )
            await conn.execute(text("DROP INDEX IF EXISTS idx_hsales_industry"))

        # ── 2. Cache hit vs recompute ────────────────────────────────────────
        if redis_url:
            try:
                import redis.asyncio as aioredis

                redis = aioredis.from_url(redis_url, decode_responses=True)
                await redis.ping()
            except Exception as exc:  # pragma: no cover
                print(f"\n[2] cache benchmark skipped — redis: {exc}")
                redis = None
            if redis is not None:
                print("\n[2] Response cache: Redis hit vs recompute")
                async with Session() as s:
                    await s.execute(text("SELECT set_config('app.bypass_rls', 'true', true)"))
                    payload = await _summary_seq(s, tenant_id, industry, now)
                blob = json.dumps(payload, default=str)
                await redis.set("rc:bench:summary", blob, ex=30)
                hit = []
                for _ in range(max(repeat, 200)):
                    t0 = time.perf_counter()
                    raw = await redis.get("rc:bench:summary")
                    json.loads(raw)
                    hit.append((time.perf_counter() - t0) * 1000)
                hit_med = _med(hit)
                print(f"  recompute (DB miss)            median={cover_med:7.2f} ms")
                print(f"  cache hit (Redis GET+decode)   median={hit_med:7.3f} ms")
                if hit_med > 0:
                    print(
                        f"  -> cache hit: {cover_med / hit_med:.0f}x faster "
                        f"({(1 - hit_med / cover_med) * 100:.1f}% latency reduction)"
                    )
                await redis.delete("rc:bench:summary")
                await redis.aclose()
        else:
            print("\n[2] cache benchmark skipped — REDIS_URL not set")
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.bypass_rls', 'true', true)"))
            await conn.execute(
                text("DELETE FROM historical_sales WHERE tenant_id = :t AND channel = 'bench'"),
                {"t": str(tenant_id)},
            )
        await engine.dispose()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=200_000)
    ap.add_argument("--repeat", type=int, default=30)
    args = ap.parse_args()
    asyncio.run(run(args.rows, args.repeat))
