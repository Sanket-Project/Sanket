import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
from test_config import settings

from app.services.llm.errors import AIError, TokenUsage
from app.services.llm.state import AIState, cache_key


def test_cache_key_isolation():
    kwargs = {"tenant": "a", "policy": "headers_only", "payload": {"columns": ["x"]}, "config": settings()}
    original = cache_key(**kwargs)
    assert "columns" not in original
    assert "headers" not in original
    assert original == cache_key(**kwargs)
    for change in [{"tenant": "b"}, {"policy": "redacted_samples"}, {"payload": {"columns": ["y"]}},
                   {"config": settings(llm_model="other")}, {"config": settings(llm_cache_generation="v2")}]:
        assert cache_key(**{**kwargs, **change}) != original


async def test_cache_and_owner_lease(ai_redis):
    state = AIState(ai_redis, settings())
    key = cache_key(tenant="a", policy="headers_only", payload={"x": 1}, config=settings())
    assert await state.cached(key) is None
    assert await state.acquire(key, "owner")
    assert not await state.acquire(key, "other")
    await state.release(key, "other")
    assert not await state.acquire(key, "other")
    await state.put(key, "owner", '{"valid":true}')
    assert await state.cached(key) == '{"valid":true}'
    await state.release(key, "owner")
    assert await state.acquire(key, "other")


async def test_request_limit_atomic_concurrency(ai_redis):
    state = AIState(ai_redis, settings(llm_requests_per_minute=3, llm_requests_per_day=4))
    async def call():
        try:
            await state.admit("workspace")
            return True
        except AIError as exc:
            if exc.code != "request_limit":
                raise
            return False
    assert sum(await asyncio.gather(*[call() for _ in range(20)])) == 3
    await state.admit("another")


async def test_request_day_boundary(ai_redis):
    clock = [1000.0]
    state = AIState(ai_redis, settings(llm_requests_per_minute=2, llm_requests_per_day=2), clock=lambda: clock[0])
    await state.admit("a")
    clock[0] += 60
    await state.admit("a")
    clock[0] += 60
    with pytest.raises(AIError, match="request_limit"):
        await state.admit("a")
    clock[0] += 86400
    await state.admit("a")


async def test_budget_settlement_and_unknown_usage(ai_redis):
    state = AIState(ai_redis, settings(llm_daily_token_limit=100, llm_max_input_bytes=20,
                                     llm_max_output_tokens=10))
    a = await state.reserve("a", "attempt1")
    await state.settle(a, TokenUsage(5, 5))
    await state.settle(a, TokenUsage(5, 5))  # No double release/debit.
    assert await ai_redis.get(a.key) == "10"
    b = await state.reserve("a", "attempt2")
    await state.settle(b, None)
    assert await ai_redis.get(a.key) == "40"
    await state.reserve("a", "attempt3")
    await state.reserve("a", "attempt4")
    with pytest.raises(AIError, match="token_limit"):
        await state.reserve("a", "attempt5")


async def test_budget_reservations_are_atomic(ai_redis):
    state = AIState(ai_redis, settings(llm_daily_token_limit=90, llm_max_input_bytes=20,
                                     llm_max_output_tokens=10))
    async def call():
        try:
            await state.reserve("a", uuid.uuid4().hex)
            return 1
        except AIError:
            return 0
    assert sum(await asyncio.gather(*[call() for _ in range(20)])) == 3


async def test_shared_breaker_one_probe_and_recovery(ai_redis):
    clock = [1000.0]
    state = AIState(ai_redis, settings(), clock=lambda: clock[0])
    for _ in range(5):
        await state.breaker_enter("owner")
        await state.breaker_finish("owner", failed=True)
    with pytest.raises(AIError, match="circuit_open"):
        await state.breaker_enter("blocked")
    clock[0] += 61
    await state.breaker_enter("probe")
    with pytest.raises(AIError, match="circuit_open"):
        await state.breaker_enter("other")
    await state.breaker_finish("other", failed=False)  # A stale/non-owner cannot reset a probe.
    with pytest.raises(AIError):
        await state.breaker_enter("other")
    await state.breaker_finish("probe", failed=False)
    await state.breaker_enter("healthy")


async def test_missing_and_broken_redis_fail_closed():
    for redis in [None, AsyncMock(get=AsyncMock(side_effect=RuntimeError("private")))]:
        with pytest.raises(AIError, match="infrastructure_unavailable"):
            await AIState(redis, settings()).cached("x")
