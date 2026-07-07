"""Tests for ML inference admission control (DoS protection).

Pure asyncio — driven with ``asyncio.run`` so they don't depend on
pytest-asyncio mode configuration.
"""

from __future__ import annotations

import asyncio

import pytest

from sanket_ml.inference.throttle import InferenceThrottle, ThrottleRejectionError


def _throttle(**over):
    kwargs = {
        "max_concurrent": 2,
        "max_queued": 2,
        "tenant_rate_per_min": 600,  # effectively unlimited for capacity tests
        "tenant_burst": 100,
        "acquire_timeout_s": 0.2,
    }
    kwargs.update(over)
    return InferenceThrottle(**kwargs)


def test_tenant_rate_limit_rejects_beyond_burst():
    async def run():
        t = _throttle(tenant_rate_per_min=60, tenant_burst=3)
        accepted = 0
        reason = None
        for _ in range(10):
            try:
                async with t.slot("tenant-a"):
                    accepted += 1
            except ThrottleRejectionError as exc:
                reason = exc.reason
                break
        # Only the burst is admitted before the bucket empties.
        assert accepted == 3
        assert reason == "tenant_rate_limited"

    asyncio.run(run())


def test_tenants_are_isolated():
    async def run():
        t = _throttle(tenant_rate_per_min=60, tenant_burst=1)
        async with t.slot("a"):
            pass
        # Tenant a is now rate-limited, but tenant b has its own bucket.
        with pytest.raises(ThrottleRejectionError):
            async with t.slot("a"):
                pass
        async with t.slot("b"):
            pass  # b unaffected

    asyncio.run(run())


def test_overload_sheds_load_with_429():
    async def run():
        # capacity = concurrent(2) + queued(2) = 4 admissible in-flight
        t = _throttle(max_concurrent=2, max_queued=2)
        release = asyncio.Event()
        entered = []

        async def hold():
            async with t.slot("t"):
                entered.append(1)
                await release.wait()

        # Start 4 long-running slots to saturate capacity.
        tasks = [asyncio.create_task(hold()) for _ in range(4)]
        # Give them time to occupy slots / queue.
        for _ in range(50):
            if len(entered) >= 2:  # 2 executing, 2 queued
                break
            await asyncio.sleep(0.01)

        # The 5th request exceeds capacity → immediate rejection.
        with pytest.raises(ThrottleRejectionError) as exc:
            async with t.slot("t"):
                pass
        assert exc.value.reason == "overloaded"

        release.set()
        await asyncio.gather(*tasks)
        # Capacity fully recovered.
        assert t.stats()["inflight"] == 0

    asyncio.run(run())


def test_queue_timeout_when_slots_stay_busy():
    async def run():
        t = _throttle(max_concurrent=1, max_queued=5, acquire_timeout_s=0.1)
        release = asyncio.Event()

        async def hold():
            async with t.slot("t"):
                await release.wait()

        holder = asyncio.create_task(hold())
        await asyncio.sleep(0.02)
        # Slot is busy; this one waits then times out (queue_timeout → 429).
        with pytest.raises(ThrottleRejectionError) as exc:
            async with t.slot("t"):
                pass
        assert exc.value.reason == "queue_timeout"
        release.set()
        await holder

    asyncio.run(run())


def test_slot_released_on_success():
    async def run():
        t = _throttle()
        async with t.slot("t"):
            assert t.stats()["inflight"] == 1
        assert t.stats()["inflight"] == 0

    asyncio.run(run())
