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


@dataclass(frozen=True, slots=True)
class RazorpayPaymentResult:
    payment_id: str
    status: str  # created | authorized | captured | refunded | failed
    amount: int  # in paise
    currency: str
    subscription_id: str | None


@dataclass(frozen=True, slots=True)
class RazorpayOrderResult:
    order_id: str
    amount: int  # in paise
    currency: str
    receipt: str | None
    status: str


def _signature_errors() -> tuple[type[BaseException], ...]:
    """The SDK's signature-mismatch exception types, if the SDK is importable.

    Kept narrow on purpose: catching bare `Exception` around signature
    verification masks configuration and transport failures as forgeries.
    """
    try:
        from razorpay.errors import SignatureVerificationError  # type: ignore

        return (SignatureVerificationError,)
    except ImportError:  # pragma: no cover - SDK always present in prod
        return ()


def _request_errors() -> tuple[type[BaseException], ...]:
    """Provider-declared API failures that are safe to translate upstream."""
    try:
        from razorpay.errors import BadRequestError, GatewayError, ServerError  # type: ignore

        return (BadRequestError, GatewayError, ServerError)
    except ImportError:  # pragma: no cover - SDK always present in prod
        return ()


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
    def cycles_for(self, billing_interval: str) -> int:
        """Number of billing cycles to request for a given plan interval.

        `total_count` is a count of *cycles*, not months. Sending the monthly
        default (120) on a yearly plan asked Razorpay for 120 years of billing.
        Yearly plans get the equivalent span in years instead.
        """
        if billing_interval == "year":
            return max(1, self.total_count // 12)
        return self.total_count

    async def create_subscription(
        self,
        *,
        plan_id: str,
        trial_days: int | None = None,
        billing_interval: str = "month",
    ) -> RazorpaySubscriptionResult:
        client = self._module()

        def _impl() -> RazorpaySubscriptionResult:
            data: dict[str, Any] = {
                "plan_id": plan_id,
                "total_count": self.cycles_for(billing_interval),
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

        try:
            return await asyncio.to_thread(_impl)
        except _request_errors() as exc:
            log.warning("billing.razorpay.subscription_create_rejected", error=str(exc))
            raise RuntimeError(
                "Razorpay rejected subscription setup. Please try again shortly."
            ) from exc

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

    # ── Signature Verification ──
    def verify_payment_signature(
        self, subscription_id: str, payment_id: str, signature: str
    ) -> bool:
        """Verify Razorpay payment signature for subscription authorization.

        Only a genuine signature mismatch returns False. Everything else —
        missing config, SDK import failure, transport errors — propagates.
        The previous `except Exception` swallowed the RuntimeError raised by
        `_module()` when Razorpay was unconfigured and silently fell through to
        the manual HMAC, so an operator misconfiguration was indistinguishable
        from a forged signature.
        """
        if not self.key_secret:
            raise RuntimeError("Cannot verify payment signature — RAZORPAY_KEY_SECRET is not set.")

        # `_module()` raising here is a config error and must not be caught.
        client = self._module()
        try:
            client.utility.verify_subscription_payment_signature(
                {
                    "razorpay_subscription_id": subscription_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": signature,
                }
            )
            return True
        except _signature_errors():
            return False

    # ── Orders (Standard Web Checkout) ──
    async def create_order(
        self,
        *,
        amount: int,
        currency: str = "INR",
        receipt: str | None = None,
        notes: dict[str, Any] | None = None,
    ) -> RazorpayOrderResult:
        """Create a standard Razorpay order for web checkout.

        Amount is in minor units (e.g. paise for INR). Minimum amount: 100 paise (₹1.00).
        """
        if amount < 100:
            raise ValueError("Order amount must be at least 100 paise (₹1.00)")
        client = self._module()

        def _impl() -> RazorpayOrderResult:
            data: dict[str, Any] = {
                "amount": amount,
                "currency": currency,
            }
            if receipt:
                data["receipt"] = receipt
            if notes:
                data["notes"] = notes
            order = client.order.create(data=data)
            return RazorpayOrderResult(
                order_id=order["id"],
                amount=int(order["amount"]),
                currency=order.get("currency", currency),
                receipt=order.get("receipt"),
                status=order.get("status", "created"),
            )

        return await asyncio.to_thread(_impl)

    def verify_order_signature(
        self,
        order_id: str,
        payment_id: str,
        signature: str,
    ) -> bool:
        """Verify Razorpay payment signature for standard web checkout order.

        Algorithm: HMAC-SHA256(order_id + "|" + payment_id, KEY_SECRET)
        """
        if not self.key_secret:
            raise RuntimeError("Cannot verify payment signature — RAZORPAY_KEY_SECRET is not set.")
        client = self._module()
        try:
            client.utility.verify_payment_signature(
                {
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": signature,
                }
            )
            return True
        except _signature_errors():
            return False

    def _hmac_order_signature(self, order_id: str, payment_id: str) -> str:
        """Reference HMAC for a standard order payment. Test/offline helper."""
        if not self.key_secret:
            raise RuntimeError("RAZORPAY_KEY_SECRET is not set")
        return hmac.new(
            self.key_secret.encode("utf-8"),
            f"{order_id}|{payment_id}".encode(),
            "sha256",
        ).hexdigest()

    def _hmac_signature(self, subscription_id: str, payment_id: str) -> str:
        """Reference HMAC for a subscription payment. Test/offline helper."""
        if not self.key_secret:
            raise RuntimeError("RAZORPAY_KEY_SECRET is not set")
        return hmac.new(
            self.key_secret.encode("utf-8"),
            f"{payment_id}|{subscription_id}".encode(),
            "sha256",
        ).hexdigest()

    # ── Payment ──
    async def fetch_payment(self, payment_id: str) -> RazorpayPaymentResult:
        """Fetch a payment so its captured state and amount can be checked.

        A valid signature only proves the (payment_id, subscription_id) pair was
        signed with our key. It says nothing about whether money actually moved,
        or how much. Activation must be gated on this call, not the signature.
        """
        client = self._module()

        def _impl() -> RazorpayPaymentResult:
            p = client.payment.fetch(payment_id)
            return RazorpayPaymentResult(
                payment_id=p["id"],
                status=p.get("status", ""),
                amount=int(p.get("amount") or 0),
                currency=p.get("currency") or "",
                subscription_id=p.get("subscription_id"),
            )

        return await asyncio.to_thread(_impl)

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
