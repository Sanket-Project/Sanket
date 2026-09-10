from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Plan, Subscription, SubscriptionStatus
from app.models.tenant import Tenant
from app.realtime import RealtimeEvent, get_connection_manager
from app.services.billing.razorpay_client import RazorpayClient

log = structlog.get_logger(__name__)


class BillingNotConfiguredError(RuntimeError):
    """A priced plan has no payment provider behind it.

    Operator error, not caller error — surfaces as 503, never 4xx, so it shows
    up in error budgets rather than being written off as a bad request.
    """


class PlanChangeNotSupportedError(ValueError):
    """Tenant already holds a live subscription on a different plan."""


class TrialAlreadyUsedError(ValueError):
    """Tenant has consumed its one trial."""


# Subscription statuses that occupy a tenant's single live-subscription slot.
# Mirrors the partial unique index in migration 0017 — keep the two in sync.
LIVE_STATUSES: tuple[SubscriptionStatus, ...] = (
    SubscriptionStatus.trialing,
    SubscriptionStatus.active,
    SubscriptionStatus.past_due,
)

# Razorpay subscription lifecycle → our internal SubscriptionStatus.
# (Razorpay: created, authenticated, active, pending, halted, paused,
#  cancelled, completed, expired.)
_RAZORPAY_STATUS_MAP: dict[str, SubscriptionStatus] = {
    "created": SubscriptionStatus.incomplete,
    "authenticated": SubscriptionStatus.trialing,
    "active": SubscriptionStatus.active,
    "pending": SubscriptionStatus.past_due,
    "halted": SubscriptionStatus.past_due,
    "paused": SubscriptionStatus.paused,
    "cancelled": SubscriptionStatus.cancelled,
    "completed": SubscriptionStatus.cancelled,
    "expired": SubscriptionStatus.cancelled,
}


def _map_status(rzp_status: str, default: SubscriptionStatus) -> SubscriptionStatus:
    return _RAZORPAY_STATUS_MAP.get(rzp_status, default)


def _ts(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromtimestamp(int(value), tz=UTC)


class SubscriptionManager:
    def __init__(self, razorpay_client: RazorpayClient) -> None:
        self._rzp = razorpay_client
        # Realtime events buffered until the caller confirms the commit.
        self._pending_events: list[RealtimeEvent] = []

    async def start_subscription(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        plan_id: str,
        billing_email: str,
    ) -> Subscription:
        plan = await session.get(Plan, plan_id)
        if plan is None:
            raise ValueError(f"Plan '{plan_id}' not found")

        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant '{tenant_id}' not found")

        # ── Idempotency ──────────────────────────────────────────────────────
        # A tenant may hold exactly one live subscription. Without this, a
        # double-submit created two Razorpay subscriptions and billed twice,
        # while `get_subscription` (newest-first) only ever surfaced one of
        # them — so the duplicate kept charging invisibly. The partial unique
        # index added in 0017 enforces this under concurrency; this check is
        # what turns the race into a friendly response instead of a 500.
        existing = await self._live(session, tenant_id)
        if existing is not None:
            log.info(
                "billing.subscription.already_live",
                tenant=str(tenant_id),
                existing_plan=existing.plan_id,
                requested_plan=plan_id,
                status=existing.status.value,
            )
            if existing.plan_id != plan_id:
                # Switching plans is a different operation (proration, cancel
                # the old mandate) and is not implemented yet. Fail loudly
                # rather than silently stacking a second subscription — the UI
                # currently offers "Switch to this plan", which lands here.
                raise PlanChangeNotSupportedError(
                    f"Tenant already subscribed to '{existing.plan_id}'. "
                    "Changing plans is not supported yet — cancel the current "
                    "subscription first."
                )
            return existing

        # ── Trial eligibility ────────────────────────────────────────────────
        # Trial length comes from the plan, never from the caller. Previously
        # `trial_days` was a request-body field (le=60), and trial reuse was
        # blocked only in React — so a crafted request could mint unlimited
        # 60-day trials.
        trial_days = plan.trial_days if await self._trial_available(session, tenant_id) else 0

        # ── Misconfiguration guard ───────────────────────────────────────────
        # The `else` branch below exists for enterprise / custom-billed plans
        # that are invoiced outside Razorpay. Because every seeded plan has a
        # NULL `razorpay_plan_id`, a *priced* plan silently fell into it and was
        # marked `active` with no payment taken. Refuse instead: a plan that
        # costs money must have a payment provider behind it.
        if plan.base_price_cents > 0 and not plan.razorpay_plan_id:
            log.error(
                "billing.plan.misconfigured",
                plan=plan_id,
                price_cents=plan.base_price_cents,
                hint="run scripts/sync_razorpay_plans.py",
            )
            raise BillingNotConfiguredError(
                f"Plan '{plan_id}' is priced at {plan.base_price_cents} but has no "
                "razorpay_plan_id. Configure RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET "
                "and run scripts/sync_razorpay_plans.py before accepting subscriptions."
            )

        if plan.razorpay_plan_id:
            # Razorpay Subscriptions creates and links the Customer only after
            # the Checkout authorisation transaction. Supplying a customer id
            # here makes the provider reject the create-subscription request.
            # The browser prefills ``billing_email`` in Checkout instead.
            rzp_sub = await self._rzp.create_subscription(
                plan_id=plan.razorpay_plan_id,
                trial_days=trial_days,
                billing_interval=plan.billing_interval,
            )
            now = datetime.now(tz=UTC)
            sub = Subscription(
                tenant_id=tenant_id,
                plan_id=plan_id,
                status=_map_status(rzp_sub.status, SubscriptionStatus.incomplete),
                razorpay_subscription_id=rzp_sub.subscription_id,
                current_period_start=_ts(rzp_sub.current_period_start) or now,
                current_period_end=_ts(rzp_sub.current_period_end) or now,
                cancel_at_period_end=False,
                subscription_metadata=(
                    {"short_url": rzp_sub.short_url} if rzp_sub.short_url else {}
                ),
            )
        else:
            # Reached only by zero-cost plans: enterprise/custom-billed (invoiced
            # out of band) or a free trial. The priced-plan guard above means we
            # can no longer arrive here for something a customer owes money on.
            from datetime import timedelta

            now = datetime.now(tz=UTC)
            if trial_days > 0:
                status = SubscriptionStatus.trialing
                period_end = now + timedelta(days=trial_days)
            else:
                # Custom-billed: entitlement is granted by whoever closes the
                # contract, not by hitting this endpoint. `incomplete` gates
                # access (SubscriptionGate only opens for active/trialing) until
                # someone activates it deliberately.
                status = SubscriptionStatus.incomplete
                period_end = now + timedelta(days=365 if plan.billing_interval == "year" else 30)

            sub = Subscription(
                tenant_id=tenant_id,
                plan_id=plan_id,
                status=status,
                current_period_start=now,
                current_period_end=period_end,
            )

        session.add(sub)
        await session.flush()
        log.info("billing.subscription.created", tenant=str(tenant_id), plan=plan_id)
        self._queue_notify(tenant_id, sub)
        return sub

    async def cancel(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        at_period_end: bool = True,
    ) -> Subscription:
        sub = await self._active(session, tenant_id)
        if sub is None:
            raise ValueError("No active subscription")

        if sub.razorpay_subscription_id:
            await self._rzp.cancel_subscription(
                sub.razorpay_subscription_id, at_period_end=at_period_end
            )

        sub.cancel_at_period_end = at_period_end
        if not at_period_end:
            sub.status = SubscriptionStatus.cancelled
            sub.cancelled_at = datetime.now(tz=UTC)
        self._queue_notify(tenant_id, sub)
        return sub

    async def verify_and_activate(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        subscription_id: str,
        payment_id: str,
        signature: str,
    ) -> Subscription:
        """Verify the payment with Razorpay, then activate.

        The signature is necessary but nowhere near sufficient. It proves the
        ``(payment_id, subscription_id)`` pair was signed with our key — not
        that the payment was captured, not that it belongs to this
        subscription, and not that the amount matches what we charge for the
        plan. This previously activated on the signature alone, so a signed
        result for a failed or under-paid payment unlocked the workspace.
        """
        from datetime import timedelta

        valid = self._rzp.verify_payment_signature(
            subscription_id=subscription_id,
            payment_id=payment_id,
            signature=signature,
        )
        if not valid:
            raise ValueError("Invalid Razorpay payment signature")

        sub = await session.scalar(
            select(Subscription).where(
                Subscription.tenant_id == tenant_id,
                Subscription.razorpay_subscription_id == subscription_id,
            )
        )
        if sub is None:
            raise ValueError(f"Subscription '{subscription_id}' not found")

        plan = await session.get(Plan, sub.plan_id)
        if plan is None:
            raise ValueError(f"Plan '{sub.plan_id}' not found")

        # ── Confirm the money actually moved ─────────────────────────────────
        payment = await self._rzp.fetch_payment(payment_id)

        if payment.status != "captured":
            log.warning(
                "billing.verify.payment_not_captured",
                tenant=str(tenant_id),
                payment=payment_id,
                status=payment.status,
            )
            raise ValueError(
                f"Payment has not been captured (status: {payment.status or 'unknown'})."
            )

        # A signature is scoped to a (payment, subscription) pair, but the
        # payment object is the authority on which subscription it settled.
        if payment.subscription_id and payment.subscription_id != subscription_id:
            log.warning(
                "billing.verify.payment_subscription_mismatch",
                tenant=str(tenant_id),
                payment=payment_id,
                expected=subscription_id,
                actual=payment.subscription_id,
            )
            raise ValueError("Payment does not belong to this subscription.")

        # Underpayment guard. `base_price_cents` and Razorpay's `amount` are
        # both minor units (paise). A trialing subscription authorises with a
        # token charge, so only enforce this once real money is due.
        if payment.amount and plan.base_price_cents and payment.amount < plan.base_price_cents:
            if sub.status is not SubscriptionStatus.trialing:
                log.warning(
                    "billing.verify.amount_mismatch",
                    tenant=str(tenant_id),
                    payment=payment_id,
                    paid=payment.amount,
                    expected=plan.base_price_cents,
                )
                raise ValueError("Payment amount does not match the plan price.")

        sub.status = SubscriptionStatus.active
        now = datetime.now(tz=UTC)
        # Extend by the plan's actual interval. This hardcoded 30 days meant an
        # annual subscriber's period_end was set one month out, so the gate
        # re-locked their workspace eleven months early.
        if (sub.current_period_end - now).total_seconds() < 86400:
            sub.current_period_end = now + timedelta(
                days=365 if plan.billing_interval == "year" else 30
            )

        self._queue_notify(tenant_id, sub)
        log.info(
            "billing.subscription.verified_and_activated",
            tenant=str(tenant_id),
            sub=subscription_id,
            payment=payment_id,
            amount=payment.amount,
        )
        return sub

    async def handle_razorpay_event(self, session: AsyncSession, event: dict[str, Any]) -> None:
        """Apply a verified Razorpay webhook event to our local Subscription row."""
        etype = event.get("event", "")
        payload = event.get("payload", {})
        sub_entity = payload.get("subscription", {}).get("entity", {}) or {}
        payment_entity = payload.get("payment", {}).get("entity", {}) or {}

        sub_id = sub_entity.get("id") or payment_entity.get("subscription_id")
        if not sub_id or not str(sub_id).startswith("sub_"):
            return

        row = await session.scalar(
            select(Subscription).where(Subscription.razorpay_subscription_id == sub_id)
        )
        if row is None:
            log.warning("billing.razorpay.unknown_subscription", id=sub_id, event_type=etype)
            return

        # ── Ordering guard ───────────────────────────────────────────────────
        # Razorpay retries and does not guarantee order. Without this, a
        # delayed `subscription.activated` arriving after a `cancelled` event
        # resurrects a subscription the customer already ended — they keep
        # access, or get billed, depending on which way it lands.
        event_ts = event.get("created_at")
        meta = dict(row.subscription_metadata or {})
        last_applied = meta.get("last_event_ts")
        if event_ts and last_applied and float(event_ts) < float(last_applied):
            log.info(
                "billing.razorpay.event_stale_dropped",
                event_type=etype,
                sub=sub_id,
                event_ts=event_ts,
                last_applied_ts=last_applied,
            )
            return

        cps = _ts(sub_entity.get("current_start"))
        cpe = _ts(sub_entity.get("current_end"))
        if cps:
            row.current_period_start = cps
        if cpe:
            row.current_period_end = cpe

        # ── Status resolution ────────────────────────────────────────────────
        # The subscription entity is the source of truth; the event type only
        # disambiguates when the entity carries no status (e.g. payment.*
        # events, whose payload has no subscription entity).
        #
        # Previously the entity status was applied and then unconditionally
        # overwritten by the event-type branch, so a `halted` subscription
        # emitting `subscription.charged` was recorded as `active` — a
        # delinquent account with a full-access workspace.
        rzp_status = sub_entity.get("status")
        if rzp_status:
            row.status = _map_status(rzp_status, row.status)
        elif etype in ("subscription.authenticated", "subscription.activated"):
            row.status = SubscriptionStatus.active
        elif etype in ("subscription.charged", "payment.captured"):
            # Only a captured payment of at least the plan price activates.
            if await self._payment_covers_plan(session, row, payment_entity):
                row.status = SubscriptionStatus.active
            else:
                log.warning(
                    "billing.razorpay.charge_did_not_cover_plan",
                    sub=sub_id,
                    event_type=etype,
                    amount=payment_entity.get("amount"),
                )
        elif etype == "payment.failed":
            row.status = SubscriptionStatus.past_due

        # Termination is the one case where the event type outranks the entity.
        # Razorpay can deliver `subscription.cancelled` while the embedded
        # entity still reads `active` (the cancellation takes effect at cycle
        # end), and letting the entity win there would leave a cancelled
        # subscription looking live.
        if etype in ("subscription.cancelled", "subscription.completed", "subscription.expired"):
            row.status = SubscriptionStatus.cancelled
            if row.cancelled_at is None:
                row.cancelled_at = datetime.now(tz=UTC)

        if event_ts:
            meta["last_event_ts"] = float(event_ts)
            row.subscription_metadata = meta

        self._queue_notify(row.tenant_id, row)
        log.info(
            "billing.razorpay.event_applied",
            event_type=etype,
            sub=sub_id,
            status=row.status.value,
        )

    @staticmethod
    async def _payment_covers_plan(
        session: AsyncSession, row: Subscription, payment_entity: dict[str, Any]
    ) -> bool:
        """True if the webhook's payment entity settles at least the plan price.

        Missing amount/status data is treated as covering, so a
        `subscription.charged` event whose payload omits the payment entity
        still activates — Razorpay does not always include it.
        """
        status = payment_entity.get("status")
        if status and status != "captured":
            return False
        amount = payment_entity.get("amount")
        if amount is None:
            return True
        plan = await session.get(Plan, row.plan_id)
        if plan is None or not plan.base_price_cents:
            return True
        return int(amount) >= plan.base_price_cents

    async def _active(self, session: AsyncSession, tenant_id: uuid.UUID) -> Subscription | None:
        """Newest subscription that can still be cancelled.

        Broader than :meth:`_live` — includes ``paused``, which does not occupy
        the tenant's live slot but is still cancellable.
        """
        res = await session.execute(
            select(Subscription)
            .where(
                Subscription.tenant_id == tenant_id,
                Subscription.status.in_((*LIVE_STATUSES, SubscriptionStatus.paused)),
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    async def _live(self, session: AsyncSession, tenant_id: uuid.UUID) -> Subscription | None:
        """The subscription currently occupying the tenant's one live slot."""
        res = await session.execute(
            select(Subscription)
            .where(
                Subscription.tenant_id == tenant_id,
                Subscription.status.in_(LIVE_STATUSES),
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    @staticmethod
    async def _trial_available(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
        """True if this tenant has never had a subscription.

        One trial per tenant, forever. Any prior subscription row — including
        one that was cancelled or expired — burns it. The React layer already
        greys out the trial card on `!!sub`; this is the half that a crafted
        request cannot skip.
        """
        prior = await session.scalar(
            select(Subscription.id).where(Subscription.tenant_id == tenant_id).limit(1)
        )
        return prior is None

    def _queue_notify(self, tenant_id: uuid.UUID, sub: Subscription) -> None:
        """Buffer a `subscription.updated` event until the transaction commits.

        These events used to be published inline, mid-transaction. If the
        commit then failed, every connected client had already been told the
        subscription was active — the UI unlocked against state that was rolled
        back. The payload is snapshotted here because the ORM object is not
        safe to read after the session closes.

        Callers must invoke :meth:`flush_notifications` after the session's
        ``async with`` block exits. Dropping a realtime event is survivable;
        emitting one for a change that never committed is not.
        """
        self._pending_events.append(
            RealtimeEvent(
                type="subscription.updated",
                tenant_id=tenant_id,
                data={
                    "subscription_id": str(sub.id),
                    "plan_id": sub.plan_id,
                    "status": sub.status.value,
                    "cancel_at_period_end": sub.cancel_at_period_end,
                    "period_end": sub.current_period_end.isoformat(),
                },
            )
        )

    async def flush_notifications(self) -> None:
        """Publish buffered events. Call only after a successful commit."""
        queued, self._pending_events = self._pending_events, []
        for item in queued:
            try:
                await get_connection_manager().publish(item)
            except Exception as exc:  # noqa: BLE001
                # A realtime delivery failure must never fail a request whose
                # billing state change has already been committed.
                log.warning("billing.notify.publish_failed", error=str(exc))

    def discard_notifications(self) -> None:
        """Drop buffered events. Call when the transaction did not commit."""
        self._pending_events = []
