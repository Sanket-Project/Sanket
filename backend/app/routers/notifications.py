"""Notification channels API — WhatsApp digest configuration, preview and test.

The preview endpoint is the important one while credentials are pending: it
renders the exact message body from live data so the digest can be reviewed and
tuned before a single message is ever transmitted.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.rbac import require_admin
from app.models.tenant import Tenant
from app.routers.industry_router import ActiveIndustry, TenantId
from app.services.notifications import digest as digest_svc
from app.services.notifications import whatsapp as wa

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/notifications", tags=["notifications"])


class RecipientIn(BaseModel):
    phone: str = Field(max_length=32)
    name: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=60)

    @field_validator("phone")
    @classmethod
    def _e164(cls, v: str) -> str:
        try:
            return wa.normalize_phone(v)
        except wa.InvalidRecipientError as exc:
            raise ValueError(str(exc)) from exc


class WhatsAppConfigIn(BaseModel):
    enabled: bool = False
    recipients: list[RecipientIn] = Field(default_factory=list, max_length=20)
    send_hour: int = Field(default=8, ge=0, le=23)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    min_confidence: int = Field(default=50, ge=0, le=100)
    max_items: int = Field(default=5, ge=1, le=20)
    include_alerts: bool = True


class TestSendBody(BaseModel):
    #: Transmitting is an outward-facing action, so it never happens implicitly.
    confirm: bool = False
    to: str | None = Field(default=None, max_length=32)


def _provider_status(settings: Any) -> dict[str, Any]:
    provider = wa.get_provider(settings)
    configured = provider.name != "console"
    return {
        "provider": provider.name,
        "configured": configured,
        "detail": (
            "Live delivery is active."
            if configured
            else getattr(provider, "reason", "No WhatsApp credentials configured")
            + ". Messages are rendered and logged, not sent."
        ),
    }


@router.get("/whatsapp")
async def get_whatsapp_config(request: Request, tenant_id: TenantId) -> dict[str, Any]:
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise AuthenticationError()
        config = wa.load_tenant_config(tenant.settings)
    return {"config": config.as_dict(), "delivery": _provider_status(get_settings())}


@router.put("/whatsapp")
async def update_whatsapp_config(
    body: WhatsAppConfigIn,
    request: Request,
    tenant_id: TenantId,
    _rbac: None = require_admin,
) -> dict[str, Any]:
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise AuthenticationError()
        settings = dict(tenant.settings or {})
        notifications = dict(settings.get("notifications") or {})
        notifications["whatsapp"] = body.model_dump(mode="json")
        settings["notifications"] = notifications
        tenant.settings = settings
        await session.flush()
        config = wa.load_tenant_config(settings)

    log.info(
        "whatsapp.config.updated",
        tenant_id=str(tenant_id),
        enabled=body.enabled,
        recipients=len(body.recipients),
    )
    return {"config": config.as_dict(), "delivery": _provider_status(get_settings())}


@router.get("/whatsapp/preview")
async def preview_digest(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
) -> dict[str, Any]:
    """Render today's digest from live data without transmitting anything."""
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise AuthenticationError()
        config = wa.load_tenant_config(tenant.settings)
        d = await digest_svc.build_digest(
            session,
            tenant_id=tenant_id,
            tenant_name=tenant.display_name,
            industry=ctx.code,
            config=config,
        )

    body = digest_svc.render_text(d)
    return {
        "digest": d.as_dict(),
        "body": body,
        "characters": len(body),
        "would_send": config.enabled and not d.is_empty and bool(config.recipients),
        "recipients": [r.as_dict() for r in config.recipients],
        "delivery": _provider_status(get_settings()),
    }


@router.post("/whatsapp/test")
async def send_test(
    body: TestSendBody,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    _rbac: None = require_admin,
) -> dict[str, Any]:
    """Send today's digest to the configured recipients (or one override number).

    Requires ``confirm: true``. Without live credentials the console provider
    returns the rendered body and ``success: false`` rather than pretending.
    """
    settings = get_settings()
    db = request.app.state.db

    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise AuthenticationError()
        config = wa.load_tenant_config(tenant.settings)
        d = await digest_svc.build_digest(
            session,
            tenant_id=tenant_id,
            tenant_name=tenant.display_name,
            industry=ctx.code,
            config=config,
        )

    text = digest_svc.render_text(d)

    if body.to:
        try:
            recipients = (wa.Recipient(phone=wa.normalize_phone(body.to)),)
        except wa.InvalidRecipientError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        recipients = config.recipients

    if not recipients:
        raise HTTPException(
            status_code=400,
            detail="No recipients configured. Add a number first, or pass `to`.",
        )

    if not body.confirm:
        return {
            "sent": False,
            "dry_run": True,
            "body": text,
            "recipients": [r.as_dict() for r in recipients],
            "delivery": _provider_status(settings),
            "detail": "Pass confirm: true to actually transmit.",
        }

    provider = wa.get_provider(settings, getattr(request.app.state, "http", None))
    results = await wa.send_all(provider, recipients=recipients, body=text)

    log.info(
        "whatsapp.test.sent",
        tenant_id=str(tenant_id),
        provider=provider.name,
        recipients=len(recipients),
        succeeded=sum(1 for r in results if r.success),
    )
    return {
        "sent": any(r.success for r in results),
        "dry_run": False,
        "body": text,
        "results": [r.as_dict() for r in results],
        "delivery": _provider_status(settings),
    }
