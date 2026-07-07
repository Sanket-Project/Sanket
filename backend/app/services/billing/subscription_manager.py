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

    async def start_subscription(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        plan_id: str,
        billing_email: str,
        trial_days: int | None = 14,
    ) -> Subscription:
        plan = await session.get(Plan, plan_id)
        if plan is None:
            raise ValueError(f"Plan '{plan_id}' not found")

        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant '{tenant_id}' not found")

        if plan.razorpay_plan_id:
            customer = await self._rzp.upsert_customer(
                email=billing_email, tenant_id=str(tenant_id), name=tenant.display_name
            )
            rzp_sub = await self._rzp.create_subscription(
                customer_id=customer.customer_id,
                plan_id=plan.razorpay_plan_id,
                trial_days=trial_days,
            )
            now = datetime.now(tz=UTC)
            sub = Subscription(
                tenant_id=tenant_id,
                plan_id=plan_id,
                status=_map_status(rzp_sub.status, SubscriptionStatus.incomplete),
                razorpay_customer_id=customer.customer_id,
                razorpay_subscription_id=rzp_sub.subscription_id,
                current_period_start=_ts(rzp_sub.current_period_start) or now,
                current_period_end=_ts(rzp_sub.current_period_end) or now,
                cancel_at_period_end=False,
                subscription_metadata=(
                    {"short_url": rzp_sub.short_url} if rzp_sub.short_url else {}
                ),
            )
        else:
            # Enterprise (custom-billed) or free-trial without Razorpay integration
            from datetime import timedelta

            now = datetime.now(tz=UTC)
            if trial_days is not None and trial_days > 0:
                status = SubscriptionStatus.trialing
                period_end = now + timedelta(days=trial_days)
            else:
                status = SubscriptionStatus.active
                if plan.billing_interval == "year":
                    period_end = now + timedelta(days=365)
                else:
                    period_end = now + timedelta(days=30)

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
        await self._notify(tenant_id, sub)
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
        await self._notify(tenant_id, sub)
        return sub

    async def handle_razorpay_event(self, session: AsyncSession, event: dict[str, Any]) -> None:
        """Apply a verified Razorpay webhook event to our local Subscription row."""
        etype = event.get("event", "")
        entity = event.get("payload", {}).get("subscription", {}).get("entity", {}) or {}
        sub_id = entity.get("id")
        if not sub_id or not str(sub_id).startswith("sub_"):
            return

        row = await session.scalar(
            select(Subscription).where(Subscription.razorpay_subscription_id == sub_id)
        )
        if row is None:
            log.warning("billing.razorpay.unknown_subscription", id=sub_id, event=etype)
            return

        rzp_status = entity.get("status")
        if rzp_status:
            row.status = _map_status(rzp_status, row.status)

        cps = _ts(entity.get("current_start"))
        cpe = _ts(entity.get("current_end"))
        if cps:
            row.current_period_start = cps
        if cpe:
            row.current_period_end = cpe

        if etype in ("subscription.cancelled", "subscription.completed", "subscription.expired"):
            row.status = SubscriptionStatus.cancelled
            row.cancelled_at = datetime.now(tz=UTC)

        await self._notify(row.tenant_id, row)
        log.info(
            "billing.razorpay.event_applied",
            event=etype,
            sub=sub_id,
            status=row.status.value,
        )

    async def _active(self, session: AsyncSession, tenant_id: uuid.UUID) -> Subscription | None:
        res = await session.execute(
            select(Subscription)
            .where(
                Subscription.tenant_id == tenant_id,
                Subscription.status.in_(("trialing", "active", "past_due", "paused")),
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    @staticmethod
    async def _notify(tenant_id: uuid.UUID, sub: Subscription) -> None:
        await get_connection_manager().publish(
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
