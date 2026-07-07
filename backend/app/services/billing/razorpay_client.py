"""Thin async wrapper around the Razorpay API.

We isolate Razorpay behind this class so tests can swap it for a fake without
touching the SubscriptionManager logic. The Razorpay SDK is sync, so we wrap
blocking calls in `asyncio.to_thread`.

Notes on the Razorpay model (vs. Stripe):
  * Subscriptions are created against a Razorpay `plan_id` and return a hosted
    `short_url`. The customer must visit that URL to authorize the mandate /
    make the first payment — there is no Stripe-style "billing portal".
  * Razorpay requires a finite `total_count` (number of billing cycles).
  * A `trial` is expressed as `start_at` (delay the first charge), not a
    `trial_period_days` field.
"""

from __future__ import annotations

import asyncio
import hmac
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import structlog

from app.config import Settings, get_settings

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RazorpayCustomerResult:
    customer_id: str
    email: str


@dataclass(frozen=True, slots=True)
class RazorpaySubscriptionResult:
    subscription_id: str
    status: str
    current_period_start: int | None
    current_period_end: int | None
    short_url: str | None


class RazorpayClient:
    def __init__(
        self,
        key_id: str | None,
        key_secret: str | None,
        *,
        total_count: int = 120,
    ) -> None:
        self.key_id = key_id
        self.key_secret = key_secret
        self.total_count = total_count
        self._client = None

    def _module(self):
        if self._client is not None:
            return self._client
        if not self.key_id or not self.key_secret:
            raise RuntimeError(
                "Razorpay is not configured — set RAZORPAY_KEY_ID and "
                "RAZORPAY_KEY_SECRET before calling billing APIs."
            )
        try:
            import razorpay  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pip install razorpay>=1.4.2") from exc
        self._client = razorpay.Client(auth=(self.key_id, self.key_secret))
        return self._client

    # ── Customer ──
    async def upsert_customer(
        self, *, email: str, tenant_id: str, name: str | None = None
    ) -> RazorpayCustomerResult:
        client = self._module()

        def _impl() -> RazorpayCustomerResult:
            # fail_existing=0 makes Razorpay return the existing customer (matched
            # by email/contact) instead of raising "Customer already exists".
            data: dict[str, Any] = {
                "email": email,
                "fail_existing": "0",
                "notes": {"tenant_id": tenant_id},
            }
            if name:
                data["name"] = name
            c = client.customer.create(data=data)
            return RazorpayCustomerResult(customer_id=c["id"], email=c.get("email") or email)

        return await asyncio.to_thread(_impl)

    # ── Subscription ──
    async def create_subscription(
        self, *, customer_id: str, plan_id: str, trial_days: int | None = None
    ) -> RazorpaySubscriptionResult:
        client = self._module()

        def _impl() -> RazorpaySubscriptionResult:
            data: dict[str, Any] = {
                "plan_id": plan_id,
                "customer_id": customer_id,
                "total_count": self.total_count,
                "customer_notify": 1,
            }
            if trial_days:
                data["start_at"] = utc_now_sec() + trial_days * 86400
            s = client.subscription.create(data=data)
            return RazorpaySubscriptionResult(
                subscription_id=s["id"],
                status=s["status"],
                current_period_start=s.get("current_start"),
                current_period_end=s.get("current_end"),
                short_url=s.get("short_url"),
            )

        return await asyncio.to_thread(_impl)

    async def cancel_subscription(
        self, subscription_id: str, *, at_period_end: bool = True
    ) -> None:
        client = self._module()

        def _impl() -> None:
            client.subscription.cancel(
                subscription_id, {"cancel_at_cycle_end": 1 if at_period_end else 0}
            )

        await asyncio.to_thread(_impl)

    async def fetch_subscription(self, subscription_id: str) -> RazorpaySubscriptionResult:
        client = self._module()

        def _impl() -> RazorpaySubscriptionResult:
            s = client.subscription.fetch(subscription_id)
            return RazorpaySubscriptionResult(
                subscription_id=s["id"],
                status=s["status"],
                current_period_start=s.get("current_start"),
                current_period_end=s.get("current_end"),
                short_url=s.get("short_url"),
            )

        return await asyncio.to_thread(_impl)

    # ── Webhook signature verification ──
    def verify_webhook_signature(self, payload: bytes, signature: str, webhook_secret: str) -> None:
        """Raise razorpay.errors.SignatureVerificationError if invalid."""
        client = self._module()
        body = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        client.utility.verify_webhook_signature(body, signature, webhook_secret)


@lru_cache(maxsize=1)
def _get_razorpay_client_cached(
    key_id: str | None, key_secret: str | None, total_count: int
) -> RazorpayClient:
    return RazorpayClient(
        key_id=key_id,
        key_secret=key_secret,
        total_count=total_count,
    )


def get_razorpay_client(settings: Settings | None = None) -> RazorpayClient:
    settings = settings or get_settings()
    return _get_razorpay_client_cached(
        key_id=getattr(settings, "razorpay_key_id", None),
        key_secret=getattr(settings, "razorpay_key_secret", None),
        total_count=getattr(settings, "razorpay_total_count", 120),
    )


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def utc_now_sec() -> int:
    return int(time.time())
