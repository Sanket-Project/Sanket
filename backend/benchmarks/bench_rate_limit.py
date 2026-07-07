"""Benchmark: rate-limit check — 3 Redis round trips vs 1 (atomic Lua).

The pre-optimization limiter issued INCR, then EXPIRE (first hit), then TTL
(when over limit) — up to three sequential round trips on the hot path of every
API request. The optimized version folds all three into one server-side Lua
script (one round trip, and atomic).

This times both strategies against a real Redis and reports the per-check
latency and the saving.

Usage:
    cd backend
    REDIS_URL=redis://localhost:6379/0 python -m benchmarks.bench_rate_limit --iters 5000

Exits 0 with a methodology note if Redis is unreachable.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import time

from app.middleware.rate_limit import _RATE_LIMIT_LUA


async def _old_check(redis, key, limit, window_s=60):
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_s)
    if count > limit:
        ttl = await redis.ttl(key)
        return True, max(ttl, 1)
    return False, 0


async def _summarize(name, samples_us):
    med = statistics.median(samples_us)
    p95 = sorted(samples_us)[max(0, int(len(samples_us) * 0.95) - 1)]
    print(f"  {name:<28} median={med:8.1f} us   p95={p95:8.1f} us   n={len(samples_us)}")
    return med


async def run(iters: int) -> None:
    redis_url = os.environ.get("REDIS_URL") or os.environ.get("BENCH_REDIS_URL")
    if not redis_url:
        _print_skip("REDIS_URL not set")
        return
    try:
        import redis.asyncio as aioredis
    except ImportError:
        _print_skip("redis package not installed")
        return

    redis = aioredis.from_url(redis_url, decode_responses=True)
    try:
        await redis.ping()
    except Exception as exc:  # pragma: no cover - depends on infra
        _print_skip(f"could not connect: {exc}")
        await redis.aclose()
        return

    # A high limit so neither path takes the (rare) over-limit TTL branch — we
    # measure the common allowed-request cost.
    limit = iters * 10
    script = redis.register_script(_RATE_LIMIT_LUA)

    print(f"\nTiming {iters:,} rate-limit checks each strategy:")
    old_us, new_us = [], []
    await redis.delete("bench:rl:old", "bench:rl:new")
    for _ in range(iters):
        t0 = time.perf_counter()
        await _old_check(redis, "bench:rl:old", limit)
        old_us.append((time.perf_counter() - t0) * 1e6)

        t0 = time.perf_counter()
        await script(keys=["bench:rl:new"], args=[60, limit])
        new_us.append((time.perf_counter() - t0) * 1e6)

    old_med = await _summarize("OLD (INCR+EXPIRE+TTL)", old_us)
    new_med = await _summarize("NEW (1 EVALSHA)", new_us)
    if new_med > 0:
        print(
            f"\n  -> {old_med / new_med:.2f}x faster per check "
            f"({(1 - new_med / old_med) * 100:.1f}% latency reduction)\n"
        )
    await redis.delete("bench:rl:old", "bench:rl:new")
    await redis.aclose()


def _print_skip(reason: str) -> None:
    print(
        f"\n[SKIP] rate-limit benchmark — {reason}.\n"
        "Methodology: times the allowed-request path of the old 2-3 command\n"
        "sequence (INCR, EXPIRE on first hit) vs the single registered Lua\n"
        "script. Expected effect: ~1 fewer round trip per request in steady\n"
        "state (EXPIRE only fires on the first hit of a window, so the old path\n"
        "is usually 1 RTT too — the guaranteed win is atomicity + removing the\n"
        "INCR/EXPIRE race; the over-limit path drops from 3 RTT to 1).\n"
        "Run with: REDIS_URL=... python -m benchmarks.bench_rate_limit\n"
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=5000)
    args = ap.parse_args()
    asyncio.run(run(args.iters))
