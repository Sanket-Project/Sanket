import asyncio
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest
from test_client import envelope
from test_config import settings

from app.models.enums import IndustryCode
from app.services.llm.client import ProviderClient
from app.services.llm.contracts import Column, TaskInput
from app.services.llm.errors import AIError
from app.services.llm.policy import AIContext, Policy
from app.services.llm.service import AIService
from app.services.llm.state import AIState

TASK = TaskInput(columns=[Column(id="c1", label="Qty Sold (Pcs)")], allowed_fields=["quantity"])


def context():
    return AIContext(uuid.uuid4(), uuid.uuid4(), IndustryCode.fashion)


def service(redis, handler, *, policy=None, config=None):
    config = config or settings()
    policies = AsyncMock(load=AsyncMock(return_value=policy or Policy(True, True, "headers_only")))
    telemetry = AsyncMock()
    client = ProviderClient(config, transport=httpx.MockTransport(handler))
    result = AIService(config, policies, AIState(redis, config), client, telemetry,
                       jitter=lambda: 0)
    return result, policies, telemetry


@pytest.mark.parametrize(("policy", "reason"), [
    (Policy(False, False, "headers_only"), "feature_disabled"),
    (Policy(True, False, "headers_only"), "task_disabled"),
    (Policy(True, True, "disabled"), "sharing_disabled"),
])
async def test_gating_without_redis_or_provider(policy, reason):
    calls = []
    ai, _, _ = service(None, lambda r: calls.append(r), policy=policy)
    try:
        result = await ai.run(context(), TASK)
        assert result.reason == reason
        assert result.value is None
        assert not calls
    finally:
        await ai.aclose()


async def test_success_cache_and_tenant_isolation(ai_redis):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=envelope())
    ai, _, telemetry = service(ai_redis, handler)
    try:
        ctx = context()
        first = await ai.run(ctx, TASK)
        again = await ai.run(ctx, TASK)
        other = await ai.run(context(), TASK)
        assert first.state == "success"
        assert not first.cached
        assert again.state == "success"
        assert again.cached
        assert other.state == "success"
        assert len(calls) == 2
        events = [call.args[2] for call in telemetry.record.await_args_list]
        assert events.count("started") == 2
        assert events.count("finished") == 2
        assert events.count("cache_hit") == 1
    finally:
        await ai.aclose()


async def test_retry_at_most_once_and_account_each_attempt(ai_redis):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json=envelope())
    ai, _, telemetry = service(ai_redis, handler)
    try:
        result = await ai.run(context(), TASK)
        assert result.state == "success"
        assert len(calls) == 2
        assert [c.args[2] for c in telemetry.record.await_args_list].count("finished") == 2
        assert telemetry.record.await_args_list[1].kwargs["usage"] is None
    finally:
        await ai.aclose()


@pytest.mark.parametrize(("status", "reason", "count"), [(401, "provider_auth", 1),
                                                (503, "provider_error", 2)])
async def test_failure_dispatch_counts(ai_redis, status, reason, count):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="private")
    ai, _, _ = service(ai_redis, handler)
    try:
        result = await ai.run(context(), TASK)
        assert result.reason == reason
        assert result.value is None
        assert len(calls) == count
    finally:
        await ai.aclose()


async def test_invalid_output_is_billed_but_not_retried(ai_redis):
    ai, _, telemetry = service(ai_redis, lambda r: httpx.Response(200, json=envelope(choices=[])))
    try:
        result = await ai.run(context(), TASK)
        assert result.reason == "invalid_output"
        calls = telemetry.record.await_args_list
        assert len(calls) == 2
        assert calls[-1].kwargs["usage"].input_tokens == 12
    finally:
        await ai.aclose()


async def test_policy_change_blocks_dispatch(ai_redis):
    calls = []
    ai, policies, _ = service(ai_redis, lambda r: calls.append(r))
    policies.load.side_effect = [Policy(True, True, "headers_only"), Policy(False, False, "disabled")]
    try:
        assert (await ai.run(context(), TASK)).reason == "policy_changed"
        assert not calls
    finally:
        await ai.aclose()


async def test_accounting_before_dispatch_blocks(ai_redis):
    calls = []
    ai, _, telemetry = service(ai_redis, lambda r: calls.append(r))
    telemetry.record.side_effect = AIError("accounting_unavailable")
    try:
        result = await ai.run(context(), TASK)
        assert result.reason == "accounting_unavailable"
        assert not calls
    finally:
        await ai.aclose()


@pytest.mark.parametrize("admission_delay", [0, 0.04])
async def test_deadline_and_cancellation_no_retry(ai_redis, admission_delay):
    calls = []
    dispatched = asyncio.Event()
    async def handler(request):
        calls.append(request)
        dispatched.set()
        await asyncio.sleep(10)
        return httpx.Response(200, json=envelope())
    ai, policies, _ = service(ai_redis, handler, config=settings(llm_deadline_s=0.5))
    try:
        start = asyncio.get_running_loop().time()
        result = await ai.run(context(), TASK)
        assert result.reason == "timeout"
        assert len(calls) == 1
        assert asyncio.get_running_loop().time() - start < 1.0
        async def load_policy(ctx):
            await asyncio.sleep(admission_delay)
            return Policy(True, True, "headers_only")
        policies.load.side_effect = load_policy
        # Cancellation during dispatch is a different contract from cancellation
        # during admission. Wait for dispatch instead of assuming Redis and policy
        # checks finish within 20 ms on every machine.
        dispatched.clear()
        ai.settings = ai.settings.model_copy(update={"llm_deadline_s": 2})
        ctx = context()
        task = asyncio.create_task(ai.run(ctx, TASK))
        try:
            await asyncio.wait_for(dispatched.wait(), timeout=1)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert len(calls) == 2
    finally:
        await ai.aclose()


async def test_two_orchestrators_share_one_dispatch(ai_redis):
    calls = []
    async def handler(request):
        calls.append(request)
        await asyncio.sleep(0.03)
        return httpx.Response(200, json=envelope())
    a, _, _ = service(ai_redis, handler)
    b, _, _ = service(ai_redis, handler)
    try:
        ctx = context()
        results = await asyncio.gather(a.run(ctx, TASK), b.run(ctx, TASK))
        assert all(r.state == "success" for r in results)
        assert len(calls) == 1
    finally:
        await a.aclose()
        await b.aclose()


async def test_missing_redis_no_dispatch():
    calls = []
    ai, _, _ = service(None, lambda r: calls.append(r))
    try:
        assert (await ai.run(context(), TASK)).reason == "infrastructure_unavailable"
        assert not calls
    finally:
        await ai.aclose()


async def test_finished_accounting_failure_retains_reservation(ai_redis):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=envelope())
    ai, _, telemetry = service(ai_redis, handler)
    telemetry.record.side_effect = [None, AIError("accounting_unavailable")]
    ctx = context()
    try:
        result = await ai.run(ctx, TASK)
        assert result.reason == "accounting_unavailable"
        assert len(calls) == 1
        keys = [key async for key in ai_redis.scan_iter(f"sanket:ai:{{{ctx.tenant_id}}}:tokens:*")]
        assert any([await ai_redis.get(key) == "reserved" for key in keys])
        assert not [key async for key in ai_redis.scan_iter(f"sanket:ai:{{{ctx.tenant_id}}}:cache:*")]
    finally:
        await ai.aclose()


async def test_unknown_usage_is_not_reported_as_zero(ai_redis):
    ai, _, telemetry = service(ai_redis, lambda r: httpx.Response(200, json=envelope(usage=None)))
    try:
        assert (await ai.run(context(), TASK)).state == "success"
        assert telemetry.record.await_args_list[-1].kwargs["usage"] is None
    finally:
        await ai.aclose()


async def test_limits_and_breaker_states_are_honest(ai_redis):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=envelope())
    ai, _, _ = service(ai_redis, handler, config=settings(llm_requests_per_minute=1))
    ctx = context()
    try:
        assert (await ai.run(ctx, TASK)).state == "success"
        assert (await ai.run(ctx, TASK)).reason == "request_limit"
        assert len(calls) == 1
    finally:
        await ai.aclose()


async def test_accounting_failure_releases_half_open_probe(ai_redis):
    ai, _, telemetry = service(ai_redis, lambda r: httpx.Response(200, json=envelope()))
    clock = [1000.0]
    ai.state.clock = lambda: clock[0]
    for _ in range(5):
        await ai.state.breaker_enter("setup")
        await ai.state.breaker_finish("setup", failed=True)
    clock[0] += 61
    telemetry.record.side_effect = [None, AIError("accounting_unavailable")]
    try:
        assert (await ai.run(context(), TASK)).reason == "accounting_unavailable"
        # Recording failure does not establish provider recovery, but it must
        # relinquish the probe so another healthy recorder can try.
        await ai.state.breaker_enter("next-probe")
    finally:
        await ai.aclose()
