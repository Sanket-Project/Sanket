"""Benchmark: sales-analytics summary — 8 sequential queries vs 1 query.

Seeds N synthetic rows into ``historical_sales`` for a throwaway tenant, then
times the two implementations of ``/analytics/sales/summary``:

  OLD: for each of {today, week, month, year} run two aggregate queries
       (current + prior window) -> 8 sequential round trips / scans.
  NEW: a single SELECT with per-period ``SUM(...) FILTER (WHERE ...)`` columns.

Both compute identical numbers (asserted), so the only variable is execution
strategy. Prints median / p95 wall-clock latency and the speed-up.

Usage:
    cd backend
    DATABASE_URL=postgresql+asyncpg://sanket_app:...@localhost:5432/sanket \\
        python -m benchmarks.bench_sales_summary --rows 200000 --repeat 25

If no database is reachable it prints the methodology and exits 0 (so CI can run
it as a smoke check without infra).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

# Reuse the production model so the benchmark tracks the real schema/columns.
import app.models  # noqa: F401  (registers models on Base.metadata)
from app.models.sales import HistoricalSale

PERIODS = ["today", "week", "month", "year"]


def _period_bounds(now: datetime, period: str) -> tuple[datetime, datetime]:
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        start, prev = today, today - timedelta(days=1)
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        prev = start - timedelta(weeks=1)
    elif period == "month":
        start = today.replace(day=1)
        prev = (start - timedelta(days=1)).replace(day=1)
    else:  # year
        start = today.replace(month=1, day=1)
        prev = start.replace(year=start.year - 1)
    return start, prev


async def _old_summary(session, tenant_id, industry, now):
    """The pre-optimization path: 8 sequential aggregate queries."""
    out = {}
    for period in PERIODS:
        start, prev_start = _period_bounds(now, period)
        elapsed = now - start
        for label, lo, hi in (
            ("cur", start, now),
            ("prev", prev_start, prev_start + elapsed),
        ):
            row = (
                await session.execute(
                    select(
                        func.coalesce(func.sum(HistoricalSale.units_sold), 0),
                        func.coalesce(func.sum(HistoricalSale.gross_revenue), 0),
                    ).where(
                        HistoricalSale.tenant_id == tenant_id,
                        HistoricalSale.industry == industry,
                        HistoricalSale.sale_time >= lo,
                        HistoricalSale.sale_time < hi,
                    )
                )
            ).one()
            out[f"{period}_{label}"] = (int(row[0] or 0), float(row[1] or 0))
    return out


async def _new_summary(session, tenant_id, industry, now):
    """The optimized path: one SELECT with FILTERed conditional aggregates."""
    bounds, earliest = {}, now
    for period in PERIODS:
        start, prev_start = _period_bounds(now, period)
        prev_end = prev_start + (now - start)
        bounds[period] = (start, prev_start, prev_end)
        earliest = min(earliest, prev_start)

    cols = []
    for period in PERIODS:
        start, prev_start, prev_end = bounds[period]
        cur = and_(HistoricalSale.sale_time >= start, HistoricalSale.sale_time < now)
        prev = and_(HistoricalSale.sale_time >= prev_start, HistoricalSale.sale_time < prev_end)
        cols += [
            func.coalesce(func.sum(HistoricalSale.units_sold).filter(cur), 0),
            func.coalesce(func.sum(HistoricalSale.gross_revenue).filter(cur), 0),
            func.coalesce(func.sum(HistoricalSale.units_sold).filter(prev), 0),
            func.coalesce(func.sum(HistoricalSale.gross_revenue).filter(prev), 0),
        ]
    row = (
        await session.execute(
            select(*cols).where(
                HistoricalSale.tenant_id == tenant_id,
                HistoricalSale.industry == industry,
                HistoricalSale.sale_time >= earliest,
                HistoricalSale.sale_time < now,
            )
        )
    ).one()
    out, i = {}, 0
    for period in PERIODS:
        out[f"{period}_cur"] = (int(row[i] or 0), float(row[i + 1] or 0))
        out[f"{period}_prev"] = (int(row[i + 2] or 0), float(row[i + 3] or 0))
        i += 4
    return out


async def _concurrent_summary(Session, tenant_id, industry, now):
    """Keep the narrow per-window scans (no over-scan) but issue them
    concurrently so the request latency is ~max(window) instead of sum(windows)."""

    async def _one(lo, hi):
        async with Session() as s:
            await s.execute(text("SELECT set_config('app.bypass_rls', 'true', true)"))
            row = (
                await s.execute(
                    select(
                        func.coalesce(func.sum(HistoricalSale.units_sold), 0),
                        func.coalesce(func.sum(HistoricalSale.gross_revenue), 0),
                    ).where(
                        HistoricalSale.tenant_id == tenant_id,
                        HistoricalSale.industry == industry,
                        HistoricalSale.sale_time >= lo,
                        HistoricalSale.sale_time < hi,
                    )
                )
            ).one()
            return int(row[0] or 0), float(row[1] or 0)

    tasks, keys = [], []
    for period in PERIODS:
        start, prev_start = _period_bounds(now, period)
        elapsed = now - start
        tasks.append(_one(start, now))
        keys.append(f"{period}_cur")
        tasks.append(_one(prev_start, prev_start + elapsed))
        keys.append(f"{period}_prev")
    results = await asyncio.gather(*tasks)
    return dict(zip(keys, results))


async def _seed(conn, tenant_id, industry, n_rows, sku_pool=500):
    now = datetime.now(UTC)
    skus = [uuid.uuid4() for _ in range(sku_pool)]
    # Spread rows across ~400 days so all four period windows are populated.
    rows = []
    for k in range(n_rows):
        offset_days = (k * 400) // n_rows
        sale_time = now - timedelta(days=offset_days, minutes=(k % 1440))
        rows.append(
            {
                "tenant_id": str(tenant_id),
                "sku_id": str(skus[k % sku_pool]),
                "industry": industry,
                "sale_time": sale_time,
                "units": (k % 9) + 1,
                "gross": round(10 + (k % 50) * 1.5, 2),
                "net": round(8 + (k % 50) * 1.3, 2),
            }
        )
    await conn.execute(
        text(
            """
            INSERT INTO historical_sales
                (tenant_id, sku_id, industry, sale_time, channel,
                 units_sold, gross_revenue, net_revenue, returns)
            VALUES
                (:tenant_id, :sku_id, CAST(:industry AS industry_code), :sale_time,
                 'bench', :units, :gross, :net, 0)
            """
        ),
        rows,
    )


def _summarize(name, samples_ms):
    med = statistics.median(samples_ms)
    p95 = sorted(samples_ms)[max(0, int(len(samples_ms) * 0.95) - 1)]
    print(f"  {name:<28} median={med:8.2f} ms   p95={p95:8.2f} ms   n={len(samples_ms)}")
    return med


async def run(rows: int, repeat: int) -> None:
    db_url = os.environ.get("DATABASE_URL") or os.environ.get(
        "BENCH_DATABASE_URL"
    )
    if not db_url:
        _print_skip("DATABASE_URL not set")
        return

    engine = create_async_engine(db_url)
    tenant_id = uuid.uuid4()
    industry = "fashion"
    now = datetime.now(UTC)

    try:
        # Validate connectivity early so we can fall back to the methodology note.
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - depends on infra
        _print_skip(f"could not connect: {exc}")
        await engine.dispose()
        return

    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(engine, expire_on_commit=False)

    print(f"\nSeeding {rows:,} rows for throwaway tenant {tenant_id} ...")
    try:
        async with engine.begin() as conn:
            # bypass RLS for the seed/bench (mirrors the app's tenant GUC)
            await conn.execute(text("SELECT set_config('app.bypass_rls', 'true', true)"))
            await conn.execute(
                text("SELECT set_config('app.current_tenant_id', :t, true)"),
                {"t": str(tenant_id)},
            )
            await _seed(conn, tenant_id, industry, rows)

        # Correctness: both strategies must agree.
        async with Session() as s:
            await s.execute(text("SELECT set_config('app.bypass_rls', 'true', true)"))
            old = await _old_summary(s, tenant_id, industry, now)
            new = await _new_summary(s, tenant_id, industry, now)
        assert old == new, f"MISMATCH old != new\n{old}\n{new}"
        print("Correctness check: old and new produce identical totals [OK]\n")

        print(f"Timing each strategy x{repeat} (cold + warm cache mix):")
        old_ms, new_ms, conc_ms = [], [], []
        for _ in range(repeat):
            async with Session() as s:
                await s.execute(text("SELECT set_config('app.bypass_rls', 'true', true)"))
                t0 = time.perf_counter()
                await _old_summary(s, tenant_id, industry, now)
                old_ms.append((time.perf_counter() - t0) * 1000)

                t0 = time.perf_counter()
                await _new_summary(s, tenant_id, industry, now)
                new_ms.append((time.perf_counter() - t0) * 1000)

            t0 = time.perf_counter()
            await _concurrent_summary(Session, tenant_id, industry, now)
            conc_ms.append((time.perf_counter() - t0) * 1000)

        old_med = _summarize("OLD (8 sequential queries)", old_ms)
        new_med = _summarize("NEW (1 FILTER query)", new_ms)
        conc_med = _summarize("CONCURRENT (8 parallel)", conc_ms)
        print()
        for label, med in (("1 FILTER query", new_med), ("8 parallel", conc_med)):
            if med > 0:
                verb = "faster" if med < old_med else "SLOWER"
                print(
                    f"  -> {label:<16} {old_med / med:.2f}x {verb} vs sequential "
                    f"({(1 - med / old_med) * 100:+.1f}% latency)"
                )
        print()
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.bypass_rls', 'true', true)"))
            await conn.execute(
                text("DELETE FROM historical_sales WHERE tenant_id = :t AND channel = 'bench'"),
                {"t": str(tenant_id)},
            )
        await engine.dispose()


def _print_skip(reason: str) -> None:
    print(
        f"\n[SKIP] sales-summary benchmark — {reason}.\n"
        "Methodology: seeds N rows, then times the 8-query loop vs the single\n"
        "FILTERed-aggregate query. Expected effect: the single query removes 7\n"
        "client<->server round trips and 7 redundant index descents, and (with\n"
        "the covering index from migration 0014) runs index-only. On a LAN with\n"
        "~0.3 ms RTT the round-trip saving alone is ~2 ms; the dominant win is\n"
        "scanning the index range once instead of eight times.\n"
        "Run with: DATABASE_URL=... python -m benchmarks.bench_sales_summary\n"
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=200_000)
    ap.add_argument("--repeat", type=int, default=25)
    args = ap.parse_args()
    asyncio.run(run(args.rows, args.repeat))
