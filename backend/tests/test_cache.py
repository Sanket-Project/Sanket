"""Tests for the Redis-backed response cache (app/core/cache.py).

Pure unit tests against an in-memory fake Redis — no Postgres or real Redis
needed. They pin the three behaviours the analytics endpoints rely on:
  * a hit returns the cached value without re-running the producer,
  * a tenant version bump (write path) invalidates every cached entry at once,
  * a missing/None Redis degrades to "always compute" (fail-open).
"""

from __future__ import annotations

import pytest

from app.core.cache import ResponseCache


class FakeRedis:
    """Minimal async Redis supporting get / set(ex=) / incr."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.get_calls = 0
        self.set_calls = 0

    async def get(self, key):
        self.get_calls += 1
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.set_calls += 1
        self.store[key] = value
        return True

    async def incr(self, key):
        cur = int(self.store.get(key, "0")) + 1
        self.store[key] = str(cur)
        return cur


def _counting_producer(value, counter):
    async def producer():
        counter["n"] += 1
        return value
    return producer


@pytest.mark.asyncio
async def test_miss_then_hit_runs_producer_once():
    cache = ResponseCache(FakeRedis())
    calls = {"n": 0}
    producer = _counting_producer({"answer": 42}, calls)

    kw = dict(tenant_id="t1", name="sales:summary", params={"industry": "fashion"}, ttl_s=30)
    first = await cache.get_or_set(producer=producer, **kw)
    second = await cache.get_or_set(producer=producer, **kw)

    assert first == second == {"answer": 42}
    assert calls["n"] == 1  # second call served from cache


@pytest.mark.asyncio
async def test_distinct_params_do_not_collide():
    cache = ResponseCache(FakeRedis())
    calls = {"n": 0}

    a = await cache.get_or_set(
        tenant_id="t1", name="s", params={"industry": "fashion"}, ttl_s=30,
        producer=_counting_producer({"v": "fashion"}, calls),
    )
    b = await cache.get_or_set(
        tenant_id="t1", name="s", params={"industry": "pharma"}, ttl_s=30,
        producer=_counting_producer({"v": "pharma"}, calls),
    )
    assert a == {"v": "fashion"}
    assert b == {"v": "pharma"}
    assert calls["n"] == 2  # different params → two distinct keys


@pytest.mark.asyncio
async def test_tenant_isolation():
    cache = ResponseCache(FakeRedis())
    calls = {"n": 0}
    kw = dict(name="s", params={"industry": "fashion"}, ttl_s=30)

    await cache.get_or_set(tenant_id="t1", producer=_counting_producer({"t": 1}, calls), **kw)
    await cache.get_or_set(tenant_id="t2", producer=_counting_producer({"t": 2}, calls), **kw)
    assert calls["n"] == 2  # tenant is part of the key


@pytest.mark.asyncio
async def test_invalidate_tenant_bumps_version_and_misses():
    cache = ResponseCache(FakeRedis())
    calls = {"n": 0}
    kw = dict(tenant_id="t1", name="s", params={"industry": "fashion"}, ttl_s=30)

    await cache.get_or_set(producer=_counting_producer({"v": 1}, calls), **kw)
    await cache.get_or_set(producer=_counting_producer({"v": 1}, calls), **kw)
    assert calls["n"] == 1  # cached

    await cache.invalidate_tenant("t1")  # write path

    fresh = await cache.get_or_set(producer=_counting_producer({"v": 2}, calls), **kw)
    assert fresh == {"v": 2}
    assert calls["n"] == 2  # version bump forced a recompute


@pytest.mark.asyncio
async def test_no_redis_is_passthrough():
    cache = ResponseCache(None)  # no Redis configured
    assert not cache.enabled
    calls = {"n": 0}
    kw = dict(tenant_id="t1", name="s", params={"industry": "fashion"}, ttl_s=30)

    await cache.get_or_set(producer=_counting_producer({"v": 1}, calls), **kw)
    await cache.get_or_set(producer=_counting_producer({"v": 1}, calls), **kw)
    assert calls["n"] == 2  # never caches → always computes
    await cache.invalidate_tenant("t1")  # no-op, must not raise


@pytest.mark.asyncio
async def test_disabled_flag_disables_caching():
    cache = ResponseCache(FakeRedis(), enabled=False)
    assert not cache.enabled
    calls = {"n": 0}
    kw = dict(tenant_id="t1", name="s", params={"industry": "fashion"}, ttl_s=30)
    await cache.get_or_set(producer=_counting_producer({"v": 1}, calls), **kw)
    await cache.get_or_set(producer=_counting_producer({"v": 1}, calls), **kw)
    assert calls["n"] == 2
