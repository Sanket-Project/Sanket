"""Tests for the rate-limit middleware after the single-round-trip refactor.

A fake Redis reproduces the atomic Lua contract (allowed → 0, limited → ttl) and
counts script invocations, so we can assert both correct enforcement and that
exactly ONE Redis round trip happens per request (the point of the refactor).
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.middleware.rate_limit import RateLimitMiddleware


class FakeScript:
    """Stand-in for redis.asyncio's AsyncScript — mimics the rate-limit Lua."""

    def __init__(self, redis: FakeRedisRL) -> None:
        self._redis = redis

    async def __call__(self, keys, args):
        self._redis.calls += 1
        key = keys[0]
        window, limit = int(args[0]), int(args[1])
        count = self._redis.counters.get(key, 0) + 1
        self._redis.counters[key] = count
        if count > limit:
            return max(1, window)  # remaining TTL → Retry-After
        return 0  # allowed


class FakeRedisRL:
    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.calls = 0
        self.scripts_registered = 0

    def register_script(self, lua):
        self.scripts_registered += 1
        return FakeScript(self)


class RaisingRedis:
    """Redis whose script always errors — exercises the fail-open path."""

    def register_script(self, lua):
        async def _boom(keys, args):
            raise ConnectionError("redis down")
        return _boom


def _make_app(redis, per_minute=3) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, per_minute=per_minute, trusted_proxy_count=0)
    app.state.redis = redis

    @app.get("/api/v1/ping")
    async def ping():
        return {"pong": True}

    return app


async def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_redis_limits_after_threshold_one_roundtrip_each():
    redis = FakeRedisRL()
    app = _make_app(redis, per_minute=3)
    async with await _client(app) as ac:
        statuses = [(await ac.get("/api/v1/ping")).status_code for _ in range(4)]

    assert statuses == [200, 200, 200, 429]
    # Exactly one script call per request — the refactor's whole point.
    assert redis.calls == 4
    assert redis.scripts_registered == 1  # script registered once, reused


async def test_retry_after_header_present_when_limited():
    app = _make_app(FakeRedisRL(), per_minute=1)
    async with await _client(app) as ac:
        await ac.get("/api/v1/ping")
        blocked = await ac.get("/api/v1/ping")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1


async def test_fail_open_when_redis_errors():
    app = _make_app(RaisingRedis(), per_minute=1)
    async with await _client(app) as ac:
        # Even past the limit, a Redis error must allow the request through.
        r1 = await ac.get("/api/v1/ping")
        r2 = await ac.get("/api/v1/ping")
    assert r1.status_code == 200
    assert r2.status_code == 200


async def test_in_process_fallback_limits_without_redis():
    app = _make_app(None, per_minute=2)
    async with await _client(app) as ac:
        statuses = [(await ac.get("/api/v1/ping")).status_code for _ in range(3)]
    assert statuses[:2] == [200, 200]
    assert statuses[2] == 429


async def test_non_api_paths_are_not_limited():
    app = _make_app(FakeRedisRL(), per_minute=1)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    async with await _client(app) as ac:
        for _ in range(5):
            assert (await ac.get("/health")).status_code == 200
