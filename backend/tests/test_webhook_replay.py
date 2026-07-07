"""Tests for inbound-webhook replay protection (freshness + delivery dedupe)."""

from __future__ import annotations

import time

import pytest

from app.core.webhook_replay import WebhookReplayError, assert_fresh_and_unique


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key, value, nx=False, ex=None, px=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True


async def test_fresh_unique_delivery_passes():
    redis = FakeRedis()
    await assert_fresh_and_unique(
        redis,
        provider="razorpay",
        delivery_id="evt_1",
        event_ts=time.time(),
        max_age_s=300,
        dedupe_ttl_s=900,
    )


async def test_duplicate_delivery_is_rejected():
    redis = FakeRedis()
    kwargs = {
        "provider": "shopify",
        "delivery_id": "wh_42",
        "event_ts": None,
        "max_age_s": 300,
        "dedupe_ttl_s": 900,
    }
    await assert_fresh_and_unique(redis, **kwargs)  # first time: ok
    with pytest.raises(WebhookReplayError) as exc:
        await assert_fresh_and_unique(redis, **kwargs)  # replay: rejected
    assert exc.value.reason == "duplicate"


async def test_stale_event_is_rejected_even_without_redis():
    with pytest.raises(WebhookReplayError) as exc:
        await assert_fresh_and_unique(
            None,
            provider="razorpay",
            delivery_id="evt_old",
            event_ts=time.time() - 10_000,
            max_age_s=300,
            dedupe_ttl_s=900,
        )
    assert exc.value.reason == "stale"


async def test_missing_delivery_id_is_noop_dedupe():
    # No id to dedupe on → cannot detect replay, but must not error.
    redis = FakeRedis()
    await assert_fresh_and_unique(
        redis, provider="shopify", delivery_id=None, event_ts=None, max_age_s=300, dedupe_ttl_s=900
    )
    await assert_fresh_and_unique(
        redis, provider="shopify", delivery_id=None, event_ts=None, max_age_s=300, dedupe_ttl_s=900
    )


async def test_redis_outage_fails_open():
    class BrokenRedis:
        async def set(self, *a, **k):
            raise ConnectionError("redis down")

    # Must allow the delivery through rather than drop legitimate provider traffic.
    await assert_fresh_and_unique(
        BrokenRedis(),
        provider="razorpay",
        delivery_id="evt_x",
        event_ts=time.time(),
        max_age_s=300,
        dedupe_ttl_s=900,
    )


async def test_future_timestamp_tolerated_for_clock_skew():
    redis = FakeRedis()
    await assert_fresh_and_unique(
        redis,
        provider="razorpay",
        delivery_id="evt_future",
        event_ts=time.time() + 30,  # provider clock slightly ahead
        max_age_s=300,
        dedupe_ttl_s=900,
    )
