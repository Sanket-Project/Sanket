"""Replay protection for inbound provider webhooks (Shopify, Razorpay).

HMAC signature verification proves a payload was produced by someone holding the
shared secret — it does NOT prove the payload is *fresh*. An attacker (or a
flaky network / over-eager provider retry) can capture a validly-signed body and
replay it: the signature still matches, so a naive handler processes it again.
For billing events that means double-applying a subscription state change.

Two independent defences, both best-effort and fail-open on Redis errors so a
Redis blip never drops legitimate provider traffic:

1. **Freshness window** — if the provider stamps the delivery with a timestamp
   (Shopify does not by default; Razorpay events carry ``created_at``) we reject
   anything older than ``max_age_s``.
2. **Delivery-id dedupe** — each delivery carries a stable unique id
   (``X-Shopify-Webhook-Id`` / Razorpay event ``id``). We record it in Redis with
   ``SET NX EX``; if it already exists the delivery is a duplicate and is dropped.

The dedupe TTL is kept >= the freshness window so a replay cannot beat the
dedupe key by simply waiting for it to expire while still inside the window.
"""

from __future__ import annotations

import time

import structlog

log = structlog.get_logger(__name__)


class WebhookReplayError(Exception):
    """Raised when an inbound webhook is stale or a duplicate."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _ts_is_fresh(event_ts: float | None, *, now: float, max_age_s: int) -> bool:
    if event_ts is None:
        return True  # provider didn't give us a usable timestamp — can't check
    # Allow a small clock-skew tolerance into the future.
    if event_ts > now + 60:
        return True
    return (now - event_ts) <= max_age_s


async def assert_fresh_and_unique(
    redis_client,
    *,
    provider: str,
    delivery_id: str | None,
    event_ts: float | None,
    max_age_s: int,
    dedupe_ttl_s: int,
) -> None:
    """Raise :class:`WebhookReplayError` if the delivery is stale or a replay.

    No-ops (allows the delivery) when replay protection cannot be applied:
    Redis is unavailable, or the provider supplied no delivery id. Freshness is
    still checked even without Redis.
    """
    now = time.time()

    if not _ts_is_fresh(event_ts, now=now, max_age_s=max_age_s):
        log.warning("webhook.replay.stale", provider=provider, age_s=round(now - (event_ts or now)))
        raise WebhookReplayError("stale")

    if redis_client is None or not delivery_id:
        return

    key = f"sanket:webhook:seen:{provider}:{delivery_id}"
    try:
        first_time = await redis_client.set(key, "1", nx=True, ex=dedupe_ttl_s)
    except Exception as exc:
        # Fail open: a Redis outage must not drop legitimate provider webhooks.
        log.warning("webhook.replay.redis_error", provider=provider, error=str(exc))
        return
    if not first_time:
        log.warning("webhook.replay.duplicate", provider=provider, delivery_id=delivery_id)
        raise WebhookReplayError("duplicate")
