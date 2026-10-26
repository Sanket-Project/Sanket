# Backend performance benchmarks

Runnable measurement scripts behind the optimizations documented in
[`docs/PERFORMANCE.md`](../../docs/PERFORMANCE.md). They are **not** pytest tests
— run them by hand against a reachable Postgres / Redis to capture before/after
numbers. Each script prints a `[SKIP]` methodology note and exits 0 when its
infra isn't available, so they're safe to invoke in CI as smoke checks.

## Running

```bash
cd backend

# Spin up throwaway infra (or point at staging)
docker run -d --name bench-pg    -e POSTGRES_PASSWORD=bench -e POSTGRES_DB=sanket \
  -p 55432:5432 pgvector/pgvector:pg16
docker run -d --name bench-redis -p 56379:6379 redis:7-alpine

export DATABASE_URL="postgresql+asyncpg://postgres:bench@localhost:55432/sanket"
export REDIS_URL="redis://localhost:56379/0"
export JWT_SECRET="bench-secret-min-32-chars-please-rotate-xyz"
python -m alembic upgrade head            # build the real schema

# Windows consoles: add -X utf8 so the summary glyphs don't crash on cp1252.
python -m benchmarks.bench_sales_summary    --rows 200000 --repeat 30
python -m benchmarks.bench_cache_and_index  --rows 200000 --repeat 30
python -m benchmarks.bench_rate_limit       --iters 5000
```

Each script seeds a throwaway tenant and **deletes its rows on exit** (rows are
tagged `channel = 'bench'`).

## What each script measures

| Script | Compares | Honest result (200k rows, local Docker) |
|--------|----------|------------------------------------------|
| `bench_sales_summary` | sequential 8-query vs single `FILTER` query vs 8 concurrent | sequential **wins**; the rewrites regress (over-scan / contention) |
| `bench_cache_and_index` | covering index vs old index; cache hit vs recompute | covering index **1.2x** (post-VACUUM, index-only); cache hit **~60–100x** |
| `bench_rate_limit` | `INCR`+`EXPIRE`+`TTL` vs one Lua `EVALSHA` | steady-state **neutral**; win is atomicity + the over-limit (429) path |

## Why a local benchmark ≠ the production win

These run on a single-core container over loopback (~0.05 ms RTT). Two effects
are *understated* here and larger in production:

* **Round-trip cost.** A managed/cross-AZ Postgres has 1–5 ms RTT, so the
  per-query round trip the cache eliminates is 10–100x what loopback shows. The
  cache win grows; the multi-query trade-offs shift.
* **Concurrency.** The covering index's smaller, heap-free reads reduce shared
  buffer pressure under many concurrent tenants — invisible in a single-stream
  timing loop.

Numbers here are deliberately the *conservative* end. See `docs/PERFORMANCE.md`
for the full analysis and which changes shipped vs were rejected by measurement.

## Location pipeline: 25,000 SKUs × 6 stores

`bench_location_pipeline.py` seeds 50 categories, one DC, six stores, 12 complete
weeks of Poisson sales (per-store means 0.2–8), eight forecast weeks and fresh
inventory. Its tenant slug starts `bench-`; inventory/sales are labelled
`synthetic_bench`. All three measured application services run as `sanket_app`
with tenant RLS enforced. The migration role is used only for fixture cleanup
because historical sales are append-only to the application role. Every
benchmark tenant is deleted in `finally`.

After migrating a disposable local database:

```powershell
cd backend
$env:BENCH_DATABASE_URL='postgresql+asyncpg://sanket_app:changeme@127.0.0.1:55434/sanket'
$env:MIGRATION_DATABASE_URL='postgresql+asyncpg://postgres:location_bench_local@127.0.0.1:55434/sanket'
uv run python -m benchmarks.bench_location_pipeline --skus 25000
```

Measured 26 October 2026, Windows/Python 3.14.3, local Docker PostgreSQL 16:

| Step | Rows | Final wall time | Final rows/s | First wall time |
|---|---:|---:|---:|---:|
| `split_run_by_location` | 1,200,000 | **119.0793 s** | 10,077.3 | **123.5337 s** |
| `build_network_decisions` | 84,858 | 26.4297 s | 3,210.7 | 29.1170 s |
| `persist_decisions` | 84,858 | 18.2784 s | 4,642.5 | 19.5078 s |

**Finding:** the first split exceeded the 120-second budget by 3.5337 seconds;
the final run was only 0.9207 seconds under it. This is a narrow margin, not
evidence of a comfortable production budget. No performance tuning was done.
The rerun followed correctness fixes to category priors and missing-input
reporting; the synthetic benchmark has no stockout or missing-history cases,
so it produced the same 1.2 million forecasts and 84,858 decisions. Variability
and local memory pressure matter at this scale.

Seeding, commits, fixture teardown and input-object loading before the builder
are outside the three timer intervals. Throughputs count each stage's output
rows; they do not count SKUs. No ML inference is included in this benchmark.
Both benchmark tenants were deleted, confirmed with a zero-count query.
Raw output is in `docs/audit/2026-10-26-location-forecasting/benchmark*.log`.
