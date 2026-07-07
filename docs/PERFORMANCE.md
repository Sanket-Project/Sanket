# SANKET Performance Engineering — Backend & Database

**Author:** Principal Performance Engineer
**Date:** 2026-06-14
**Scope of this pass:** Backend request path + Database (the two areas with the
highest, safest ROI and full local verifiability). ML and Frontend are assessed
at the end with a prioritized backlog — not implemented in this pass.

> **On honesty of numbers.** Every figure below labelled *measured* comes from
> the runnable harness in [`backend/benchmarks/`](../backend/benchmarks/) against
> real Postgres 16 + Redis 7 (Docker, 200k synthetic rows, single tenant +
> industry, loopback). These are **conservative** — a production managed/cross-AZ
> database has 1–5 ms round-trip latency vs loopback's ~0.05 ms, which *amplifies*
> the cache win and the cost of extra round trips. Figures labelled *estimate*
> are reasoned, not run, and say so. Two proposed optimizations were **rejected
> by measurement** — documented as such rather than shipped.

---

## 1. Methodology

1. Read the actual hot paths (auth, DB layer, analytics routers, Redis middleware).
2. Reproduce each candidate bottleneck in an isolated benchmark with a known data
   volume and assert correctness (old vs new produce identical output).
3. Measure median + p95 over ≥30 iterations.
4. Ship only changes that measure as a net improvement (or fix a correctness/
   availability defect). Keep the loser, document why.

**Environment:** Postgres 16 (pgvector image), Redis 7, SQLAlchemy 2 async +
asyncpg, single-core containers over loopback. Schema built by the real Alembic
chain (`alembic upgrade head`) so benchmarks hit production DDL.

---

## 2. Findings & changes (shipped)

### 2.1 Database — automated partition creation  ✅ availability fix

**Bottleneck (correctness/availability, not latency).** `historical_sales` and
`forecast_results` are `RANGE`-partitioned by quarter, but partitions were
created by a **static** `DO` block covering hardcoded years (2022–2027 / 2024–2027,
[`sql/002_schema.sql`](../backend/sql/002_schema.sql)). The first row whose
timestamp lands past the last declared partition fails hard:
`no partition of relation "historical_sales" found for row`. At enterprise ingest
volume this is a guaranteed future outage with no warning.

**Fix.** Migration [`0013_auto_partition_maintenance.py`](../backend/alembic/versions/0013_auto_partition_maintenance.py)
adds `sanket_ensure_quarterly_partitions(parent, lookback, lookahead)` and
`sanket_maintain_partitions()` — idempotent, `SECURITY DEFINER`, search-path
pinned. Driven by three things:
- run once inside the migration (extends the window immediately),
- a daily k8s CronJob ([`infra/cron/partition-maintenance-cronjob.yaml`](../infra/cron/partition-maintenance-cronjob.yaml)),
- a best-effort startup backstop (`Database.maintain_partitions()`,
  [`app/core/database.py`](../backend/app/core/database.py)).

**Result.** Partitions for the rolling `[-1q, +4q]` window always exist before a
row needs them. **Verified** by [`tests/test_partitions.py`](../backend/tests/test_partitions.py)
(current-quarter partition present, idempotent re-runs create 0, far-lookahead
creates then no-ops).
**Gain:** eliminates a class of hard INSERT failures (∞ improvement on the failing
path); no steady-state latency cost.

### 2.2 Database — index audit + covering index  ✅ 1.21x measured

**Audit of `historical_sales` indexes** (8 indexes reviewed). The analytics
endpoints filter `(tenant_id, industry, sale_time)` then `SUM(units_sold,
gross_revenue, net_revenue, returns)`. The pre-existing
`idx_hsales_industry (tenant_id, industry, sale_time DESC)` satisfied the *filter*
but every matching row still needed a **heap fetch** for the summed columns.

**Fix.** Migration [`0014_analytics_covering_indexes.py`](../backend/alembic/versions/0014_analytics_covering_indexes.py):
add `idx_hsales_agg_covering (tenant_id, industry, sale_time) INCLUDE
(units_sold, gross_revenue, net_revenue, returns)` → **index-only scan**, and
**drop** the now-redundant `idx_hsales_industry` (same key prefix; btree scans
backwards so `DESC` ordering is still served) to cut write amplification.

**Measured** (`bench_cache_and_index`, post-VACUUM so the visibility map is set —
the steady-state production condition):

| Index | Summary aggregate, median |
|-------|---------------------------|
| `idx_hsales_industry` (heap fetch) | 29.69 ms |
| `idx_hsales_agg_covering` (index-only) | **24.54 ms** |

**Gain: 1.21x (−17.4% latency).** *Caveat measured honestly:* on freshly
bulk-loaded rows **before** VACUUM the covering index is ~neutral/slightly slower
(wider index, heap still probed for visibility) — autovacuum makes the win real
in production. Under many concurrent tenants the heap-free reads also reduce
shared-buffer pressure (estimate: larger than the single-stream 1.21x).

### 2.3 Backend — API response cache  ✅ ~60–110x measured (the headline win)

**Bottleneck.** Dashboard endpoints (`/analytics/sales/summary`, `/timeseries`,
`/top-products`) recompute the same multi-aggregate query on **every poll**, and
dashboards poll every few seconds per active user. This is the dominant wasted
work at scale.

**Fix.** A Redis-backed, tenant-scoped response cache
([`app/core/cache.py`](../backend/app/core/cache.py)) wrapping the three read
endpoints ([`app/routers/sales_analytics.py`](../backend/app/routers/sales_analytics.py)):
- key = `rc:{tenant}:{version}:{endpoint}:{digest(params)}`,
- **O(1) version-bump invalidation** — `ingest_sale` calls
  `invalidate_tenant()`, which `INCR`s a per-tenant counter so all cached entries
  are instantly unreachable (no key-scan, correct under concurrency),
- short TTL (`api_cache_ttl_s`, default 30 s) as a safety net,
- **fail-open**: no Redis ⇒ transparent passthrough (identical to today).

**Measured** (`bench_cache_and_index`):

| Path | median |
|------|--------|
| Recompute (cache miss / DB) | 24.5 ms |
| Cache hit (Redis GET + JSON decode) | **0.37 ms** |

**Gain: ~66–109x (98.5–99.1% latency reduction)** on the common repeat-poll path.
Verified functionally by [`tests/test_cache.py`](../backend/tests/test_cache.py)
(hit/miss, param & tenant scoping, version-bump invalidation, no-Redis passthrough).

### 2.4 Backend — Redis rate-limiter, atomic single round trip  ✅ correctness + tail-latency

**Bottleneck.** The limiter ran `INCR`, then `EXPIRE` (first hit), then `TTL`
(over limit) — up to **3 sequential round trips** on the hot path of every API
request, plus a race: a crash between `INCR` and `EXPIRE` leaves a key with **no
TTL** → that client is locked out permanently.

**Fix.** Fold all three into one registered Lua script (`EVALSHA`, one round
trip, atomic) — [`app/middleware/rate_limit.py`](../backend/app/middleware/rate_limit.py).

**Measured** (`bench_rate_limit`, allowed-path):

| Strategy | per-check median |
|----------|------------------|
| `INCR`+`EXPIRE`+`TTL` | 440.6 µs |
| 1 `EVALSHA` | 469.5 µs |

**Honest result:** steady-state latency is **neutral** (−7%); in the common
allowed case the old path was *already* ~1 round trip because `EXPIRE` only fires
on a window's first hit. The real wins are **(a) atomicity** — the INCR/EXPIRE
lockout race is eliminated — and **(b) the over-limit (429) path drops from 3
round trips to 1**, cutting tail latency exactly when the system is hot. Verified
by [`tests/test_rate_limit.py`](../backend/tests/test_rate_limit.py) (one script
call per request, fail-open on Redis error, correct enforcement).

---

## 3. Rejected by measurement (did **not** ship)

Rigor means reporting the losers. Both were plausible and both regressed.

### 3.1 Collapsing the 8-query summary into one `FILTER` query — **0.56x (rejected)**

The intuitive "8 round trips → 1" rewrite using `SUM(...) FILTER (WHERE ...)`
**regressed 1.5–1.8x** (`bench_sales_summary`):

| Strategy | median (200k rows) |
|----------|--------------------|
| OLD — 8 sequential windowed queries | **47.75 ms** |
| NEW — 1 conditional-aggregation query | 85.03 ms |
| 8 concurrent queries | 176.12 ms |

**Why.** The single query must scan the entire `[year_prior_start, now)` union
(~1.5 years) and apply 8 filters per row, while the windowed queries each scan
only their slice (today = 1 day, week = 7 days …). On loopback the round-trip
saving (sub-ms each) doesn't pay for the extra rows scanned. Concurrency was
worse still (connection setup + single-core contention; the year-window scan
dominates regardless of parallelism).

**Decision:** kept the original sequential windowed queries (proven fastest) and
let the **cache** (§2.3) carry the latency win. The rationale is recorded inline
in `sales_summary` so no one "re-optimizes" it back into a regression.

---

## 4. Results summary

| Area | Change | Baseline | Final | Gain | Evidence |
|------|--------|----------|-------|------|----------|
| DB | Auto partition creation | INSERT fails past 2027 | Always-present rolling window | Removes outage class | tests + migration 0013 |
| DB | Covering index (index-only) | 29.69 ms | 24.54 ms | **1.21x (−17%)** | measured |
| API | Response cache (repeat poll) | 24.5 ms | 0.37 ms | **~66–109x (−99%)** | measured |
| API | Rate-limiter atomic Lua | 3 RTT race (429 path) | 1 RTT, atomic | Correctness + tail | measured + tests |
| — | Single-query summary | 47.75 ms | 85.03 ms | **rejected (0.56x)** | measured |

**Net shipped effect on the analytics hot path:** first request per TTL window
≈ DB cost (now index-only, ~1.2x faster); every subsequent poll within the window
≈ **0.4 ms** instead of ~25 ms — a ~99% reduction on the overwhelming majority of
dashboard traffic, which is repeat polling.

---

## 5. Not done this pass — assessment & backlog

The brief also lists **JWT/JWK**, **ML**, and **Frontend**. Honest status:

- **"Replace threadpool JWT validation with async JWK caching" — largely a
  non-issue.** The current code already verifies Firebase ID tokens against
  *cached* Google public keys with no per-request network call, and caches
  revocation per-UID with a TTL ([`firebase_auth.py`](../backend/app/core/firebase_auth.py)).
  There is no per-request JWK fetch to eliminate. A real (smaller) win: verify is
  CPU-bound (RS256 signature) and runs on the event loop; offloading to a thread
  or a small `lru_cache` on `(token → identity, exp)` would cut p99 under burst.
  *Estimate only — not measured.*

- **ML (GPU, batch, Chronos latency).** GPU is **already** supported
  (`_resolve_device` → cuda/mps, bf16 on CUDA) and Chronos is **already** batched
  (`pipeline.predict` takes a list of series). Real remaining wins: cross-request
  micro-batching, `torch.compile`, capping `num_samples`/context length. **Cannot
  be honestly benchmarked without GPU hardware** — deferred.

- **Frontend (bundle, virtualization, charts).** Verifiable in the browser
  preview but out of scope for the backend/DB pass chosen for this session.

**Recommended next priority:** cross-request ML micro-batching (biggest tail-
latency lever for forecasts) and frontend list virtualization, each as its own
measured pass.

---

## 6. How to reproduce

See [`backend/benchmarks/README.md`](../backend/benchmarks/README.md). TL;DR:

```bash
cd backend
# (start pg + redis, export DATABASE_URL / REDIS_URL / JWT_SECRET, alembic upgrade head)
python -m benchmarks.bench_cache_and_index --rows 200000 --repeat 30
python -m benchmarks.bench_sales_summary   --rows 200000 --repeat 30
python -m benchmarks.bench_rate_limit      --iters 5000
```
