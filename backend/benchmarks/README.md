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
