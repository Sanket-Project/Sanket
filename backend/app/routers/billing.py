from __future__ import annotations

import json
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.config import Settings, get_settings
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.rbac import require_admin_db
from app.models.billing import MeterKind, Plan, Subscription
from app.routers.industry_router import TenantId, UserId
from app.services import usage
from app.services.billing import SubscriptionManager, get_razorpay_client

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/billing", tags=["billing"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


class StartSubscriptionBody(BaseModel):
    plan_id: str
    billing_email: EmailStr
    trial_days: int | None = Field(default=14, ge=0, le=60)


class CancelBody(BaseModel):
    at_period_end: bool = True


class PortalSessionBody(BaseModel):
    return_url: str


@router.get("/plans")
async def list_plans(request: Request) -> list[dict[str, Any]]:
    db = request.app.state.db
    async with db.session_no_rls() as session:
        result = await session.execute(
            select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.base_price_cents)
        )
        plans = result.scalars().all()
    return [
        {
            "id": p.id,
            "display_name": p.display_name,
            "tier": p.tier,
            "base_price_cents": p.base_price_cents,
            "billing_interval": p.billing_interval,
            "included_quotas": p.included_quotas,
            "overage_rates_cents": p.overage_rates_cents,
        }
        for p in plans
    ]


@router.get("/subscription")
async def get_subscription(request: Request, tenant_id: TenantId) -> dict[str, Any] | None:
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        res = await session.execute(
            select(Subscription)
            .where(Subscription.tenant_id == tenant_id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        sub = res.scalar_one_or_none()
    if sub is None:
        return None
    return {
        "id": str(sub.id),
        "plan_id": sub.plan_id,
        "status": sub.status.value,
        "current_period_start": sub.current_period_start.isoformat(),
        "current_period_end": sub.current_period_end.isoformat(),
        "cancel_at_period_end": sub.cancel_at_period_end,
    }


@router.post("/subscription")
async def start_subscription(
    body: StartSubscriptionBody,
    request: Request,
    tenant_id: TenantId,
    user_id: UserId,
    settings: SettingsDep,
    _rbac: None = require_admin_db,
) -> dict[str, Any]:
    db = request.app.state.db
    mgr = SubscriptionManager(get_razorpay_client(settings))
    async with db.session(str(tenant_id)) as session:
        try:
            sub = await mgr.start_subscription(
                session,
                tenant_id=tenant_id,
                plan_id=body.plan_id,
                billing_email=body.billing_email,
                trial_days=body.trial_days,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        # short_url is the Razorpay-hosted page where the customer authorizes
        # the mandate / makes the first payment. The frontend redirects here.
        short_url = (sub.subscription_metadata or {}).get("short_url")
    return {
        "id": str(sub.id),
        "plan_id": sub.plan_id,
        "status": sub.status.value,
        "short_url": short_url,
    }


@router.post("/subscription/cancel")
async def cancel_subscription(
    body: CancelBody,
    request: Request,
    tenant_id: TenantId,
    settings: SettingsDep,
    _rbac: None = require_admin_db,
) -> dict[str, Any]:
    db = request.app.state.db
    mgr = SubscriptionManager(get_razorpay_client(settings))
    async with db.session(str(tenant_id)) as session:
        try:
            sub = await mgr.cancel(session, tenant_id=tenant_id, at_period_end=body.at_period_end)
        except ValueError as exc:
            raise NotFoundError("Subscription") from exc
    return {
        "id": str(sub.id),
        "status": sub.status.value,
        "cancel_at_period_end": sub.cancel_at_period_end,
    }


@router.post("/portal")
async def billing_portal(
    body: PortalSessionBody,
    request: Request,
    tenant_id: TenantId,
    settings: SettingsDep,
) -> dict[str, str]:
    # Razorpay has no Stripe-style billing portal. We return the subscription's
    # hosted `short_url`, where the customer can view/authorize/manage it.
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        sub = await session.scalar(
            select(Subscription)
            .where(
                Subscription.tenant_id == tenant_id,
                Subscription.razorpay_subscription_id.is_not(None),
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        short_url = (sub.subscription_metadata or {}).get("short_url") if sub else None
        rzp_sub_id = sub.razorpay_subscription_id if sub else None

    if sub is None or not rzp_sub_id:
        raise NotFoundError("Razorpay subscription")

    # Backfill short_url from Razorpay if it wasn't captured at creation time.
    if not short_url:
        fetched = await get_razorpay_client(settings).fetch_subscription(rzp_sub_id)
        short_url = fetched.short_url
    if not short_url:
        raise NotFoundError("Razorpay subscription page")
    return {"url": short_url}


@router.get("/usage")
async def get_usage(request: Request, tenant_id: TenantId) -> dict[str, Any]:
    db = request.app.state.db
    out: dict[str, Any] = {"period_start": None, "period_end": None, "meters": {}}
    async with db.session(str(tenant_id)) as session:
        sub = await session.scalar(
            select(Subscription)
            .where(Subscription.tenant_id == tenant_id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        if sub:
            out["period_start"] = sub.current_period_start.isoformat()
            out["period_end"] = sub.current_period_end.isoformat()
            plan = await session.get(Plan, sub.plan_id)
            quotas = (plan.included_quotas if plan else {}) or {}
        else:
            quotas = {}
        for meter in MeterKind:
            used = float(
                await usage.current_period_usage(session, tenant_id=tenant_id, meter=meter)
            )
            limit = float(quotas.get(meter.value, float("inf")))
            out["meters"][meter.value] = {
                "used": used,
                "limit": limit if limit != float("inf") else None,
                "pct": (used / limit) if limit and limit != float("inf") else 0.0,
            }
    return out


# ── Razorpay webhook receiver (unauthenticated; signature-verified) ──
@router.post("/razorpay/webhook", include_in_schema=False)
async def razorpay_webhook(request: Request, settings: SettingsDep) -> dict[str, str]:
    secret = getattr(settings, "razorpay_webhook_secret", None)
    if not secret:
        raise HTTPException(status_code=503, detail="Razorpay webhook not configured")
    signature = request.headers.get("X-Razorpay-Signature", "")
    body = await request.body()
    client = get_razorpay_client(settings)
    try:
        client.verify_webhook_signature(body, signature, secret)
    except Exception as exc:
        log.warning("billing.razorpay.webhook.bad_signature", error=str(exc))
        raise HTTPException(status_code=400, detail="invalid signature") from exc

    event = json.loads(body)

    # Replay protection: a captured, validly-signed Razorpay event can be
    # replayed (the HMAC still matches). Drop stale events and de-duplicate by
    # the provider event id so a state change is never applied twice.
    if settings.webhook_replay_protection_enabled:
        from app.core.webhook_replay import WebhookReplayError, assert_fresh_and_unique

        delivery_id = request.headers.get("X-Razorpay-Event-Id") or event.get("id") or None
        try:
            await assert_fresh_and_unique(
                getattr(request.app.state, "redis", None),
                provider="razorpay",
                delivery_id=delivery_id,
                event_ts=float(event["created_at"]) if event.get("created_at") else None,
                max_age_s=settings.webhook_replay_max_age_s,
                dedupe_ttl_s=settings.webhook_replay_dedupe_ttl_s,
            )
        except WebhookReplayError as exc:
            # 200 so the provider stops retrying a duplicate; we simply no-op.
            log.info("billing.razorpay.webhook.replay_dropped", reason=exc.reason)
            return {"received": "duplicate"}

    db = request.app.state.db
    mgr = SubscriptionManager(client)
    async with db.session_no_rls() as session:
        await mgr.handle_razorpay_event(session, event)
    return {"received": "ok"}
