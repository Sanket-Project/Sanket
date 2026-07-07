from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.models.webhook import WebhookDelivery, WebhookEndpoint, WebhookEventType
from app.routers.industry_router import TenantId, UserId
from app.services import audit, webhooks

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_VALID_EVENTS = {e.value for e in WebhookEventType}


class EndpointCreateBody(BaseModel):
    url: str = Field(pattern=r"^https://")
    enabled_events: list[str] = Field(min_length=1)
    description: str | None = None

    @field_validator("enabled_events")
    @classmethod
    def _events_valid(cls, v: list[str]) -> list[str]:
        unknown = [e for e in v if e not in _VALID_EVENTS]
        if unknown:
            raise ValueError(f"Unknown event types: {unknown}. Valid: {sorted(_VALID_EVENTS)}")
        return v


class EndpointUpdateBody(BaseModel):
    enabled_events: list[str] | None = None
    is_active: bool | None = None
    description: str | None = None


def _require_admin(request: Request) -> None:
    role = getattr(request.state, "role", "viewer")
    if role not in ("owner", "admin"):
        raise PermissionDeniedError("Only owner/admin can manage webhooks")


@router.get("/endpoints")
async def list_endpoints(request: Request, tenant_id: TenantId) -> list[dict[str, Any]]:
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        res = await session.execute(
            select(WebhookEndpoint)
            .where(WebhookEndpoint.tenant_id == tenant_id)
            .order_by(WebhookEndpoint.created_at.desc())
        )
        endpoints = res.scalars().all()
    return [
        {
            "id": str(e.id),
            "url": e.url,
            "enabled_events": e.enabled_events,
            "is_active": e.is_active,
            "description": e.description,
            "last_delivery_at": e.last_delivery_at.isoformat() if e.last_delivery_at else None,
            "failure_count": e.failure_count,
            "created_at": e.created_at.isoformat(),
        }
        for e in endpoints
    ]


@router.post("/endpoints", status_code=201)
async def create_endpoint(
    body: EndpointCreateBody,
    request: Request,
    tenant_id: TenantId,
    user_id: UserId,
) -> dict[str, Any]:
    _require_admin(request)
    db = request.app.state.db
    secret = webhooks.generate_secret()
    async with db.session(str(tenant_id)) as session:
        endpoint = WebhookEndpoint(
            tenant_id=tenant_id,
            url=body.url,
            secret=secret,
            enabled_events=body.enabled_events,
            description=body.description,
        )
        session.add(endpoint)
        await session.flush()
        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="webhook.endpoint.create",
            entity_type="webhook_endpoint",
            entity_id=str(endpoint.id),
            new_value={"url": body.url, "events": body.enabled_events},
            request_id=getattr(request.state, "request_id", None),
        )
        endpoint_id = endpoint.id
    log.info("webhook.endpoint.created", id=str(endpoint_id))
    # Secret is returned ONCE on create — never readable afterward.
    return {
        "id": str(endpoint_id),
        "url": body.url,
        "secret": secret,
        "enabled_events": body.enabled_events,
        "warning": "Store this secret now — it will not be shown again.",
    }


@router.patch("/endpoints/{endpoint_id}")
async def update_endpoint(
    endpoint_id: str,
    body: EndpointUpdateBody,
    request: Request,
    tenant_id: TenantId,
    user_id: UserId,
) -> dict[str, Any]:
    _require_admin(request)
    db = request.app.state.db
    eid = uuid.UUID(endpoint_id)

    if body.enabled_events is not None:
        unknown = [e for e in body.enabled_events if e not in _VALID_EVENTS]
        if unknown:
            raise ValidationError(f"Unknown event types: {unknown}")

    async with db.session(str(tenant_id)) as session:
        ep = await session.scalar(
            select(WebhookEndpoint).where(
                WebhookEndpoint.id == eid, WebhookEndpoint.tenant_id == tenant_id
            )
        )
        if ep is None:
            raise NotFoundError("WebhookEndpoint")
        updates = body.model_dump(exclude_none=True)
        for k, v in updates.items():
            setattr(ep, k, v)
        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="webhook.endpoint.update",
            entity_type="webhook_endpoint",
            entity_id=str(eid),
            new_value=updates,
            request_id=getattr(request.state, "request_id", None),
        )
    return {"id": endpoint_id, "updated": list(updates.keys())}


@router.delete("/endpoints/{endpoint_id}", status_code=204)
async def delete_endpoint(
    endpoint_id: str,
    request: Request,
    tenant_id: TenantId,
    user_id: UserId,
) -> None:
    _require_admin(request)
    db = request.app.state.db
    eid = uuid.UUID(endpoint_id)
    async with db.session(str(tenant_id)) as session:
        ep = await session.scalar(
            select(WebhookEndpoint).where(
                WebhookEndpoint.id == eid, WebhookEndpoint.tenant_id == tenant_id
            )
        )
        if ep is None:
            raise NotFoundError("WebhookEndpoint")
        await session.delete(ep)
        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="webhook.endpoint.delete",
            entity_type="webhook_endpoint",
            entity_id=str(eid),
            request_id=getattr(request.state, "request_id", None),
        )


@router.get("/deliveries")
async def list_deliveries(
    request: Request,
    tenant_id: TenantId,
    endpoint_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        q = select(WebhookDelivery).where(WebhookDelivery.tenant_id == tenant_id)
        if endpoint_id:
            q = q.where(WebhookDelivery.endpoint_id == uuid.UUID(endpoint_id))
        if status:
            q = q.where(WebhookDelivery.status == status)
        q = q.order_by(WebhookDelivery.created_at.desc()).limit(min(limit, 200))
        res = await session.execute(q)
        deliveries = res.scalars().all()
    return [
        {
            "id": d.id,
            "endpoint_id": str(d.endpoint_id),
            "event_type": d.event_type.value,
            "event_id": str(d.event_id),
            "status": d.status,
            "attempt_count": d.attempt_count,
            "response_status": d.response_status,
            "response_body": d.response_body,
            "payload": d.payload,
            "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
            "next_retry_at": d.next_retry_at.isoformat() if d.next_retry_at else None,
            "created_at": d.created_at.isoformat(),
        }
        for d in deliveries
    ]


@router.post("/deliveries/{delivery_id}/retry")
async def retry_delivery(
    delivery_id: int,
    request: Request,
    tenant_id: TenantId,
    user_id: UserId,
) -> dict[str, Any]:
    _require_admin(request)
    db = request.app.state.db
    import httpx

    # Phase 1: Reset the delivery status in its own committed transaction.
    async with db.session(str(tenant_id)) as session:
        d = await session.scalar(
            select(WebhookDelivery).where(
                WebhookDelivery.id == delivery_id,
                WebhookDelivery.tenant_id == tenant_id,
            )
        )
        if d is None:
            raise NotFoundError("WebhookDelivery")
        # Reset retry schedule so the worker re-attempts immediately
        d.status = "pending"
        d.next_retry_at = None
        # Transaction commits here when the context manager exits cleanly.

    # Phase 2: Attempt delivery in a fresh session (previous one is closed).
    async with db.session(str(tenant_id)) as session:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await webhooks._try_deliver(session, delivery_id, client)
        d = await session.scalar(select(WebhookDelivery).where(WebhookDelivery.id == delivery_id))
    return {
        "id": d.id if d else delivery_id,
        "status": d.status if d else "unknown",
        "attempt_count": d.attempt_count if d else 0,
        "response_status": d.response_status if d else None,
    }
