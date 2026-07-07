"""Tests for the request-idempotency middleware.

Builds a minimal FastAPI app (no Postgres) with the middleware and an in-memory
fake Redis on app.state, then asserts that retries with the same Idempotency-Key
execute the handler exactly once and replay the cached response.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.middleware.idempotency import IdempotencyMiddleware


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key, value, nx=False, ex=None, px=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)
        return 1


def _make_app(redis) -> FastAPI:
    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware, ttl_s=3600, enabled=True)
    app.state.redis = redis
    app.state.counter = {"n": 0}

    @app.post("/charge")
    async def charge():
        app.state.counter["n"] += 1
        return {"charge_id": app.state.counter["n"]}

    return app


async def _client(app):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_retry_with_same_key_executes_once_and_replays():
    app = _make_app(FakeRedis())
    async with await _client(app) as ac:
        r1 = await ac.post("/charge", headers={"Idempotency-Key": "abc"})
        r2 = await ac.post("/charge", headers={"Idempotency-Key": "abc"})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json() == {"charge_id": 1}
    assert app.state.counter["n"] == 1  # handler ran exactly once
    assert r2.headers.get("Idempotency-Replayed") == "true"


async def test_different_keys_execute_independently():
    app = _make_app(FakeRedis())
    async with await _client(app) as ac:
        r1 = await ac.post("/charge", headers={"Idempotency-Key": "k1"})
        r2 = await ac.post("/charge", headers={"Idempotency-Key": "k2"})
    assert r1.json() == {"charge_id": 1}
    assert r2.json() == {"charge_id": 2}
    assert app.state.counter["n"] == 2


async def test_no_key_means_no_idempotency():
    app = _make_app(FakeRedis())
    async with await _client(app) as ac:
        await ac.post("/charge")
        await ac.post("/charge")
    assert app.state.counter["n"] == 2


async def test_get_requests_are_untouched():
    app = _make_app(FakeRedis())

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    async with await _client(app) as ac:
        r = await ac.get("/ping", headers={"Idempotency-Key": "x"})
    assert r.status_code == 200


async def test_passthrough_when_no_redis():
    app = _make_app(None)  # no shared store → cannot guarantee idempotency
    async with await _client(app) as ac:
        await ac.post("/charge", headers={"Idempotency-Key": "abc"})
        await ac.post("/charge", headers={"Idempotency-Key": "abc"})
    assert app.state.counter["n"] == 2
