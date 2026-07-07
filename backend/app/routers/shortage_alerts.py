"""Shortage alert management endpoints.

GET   /alerts                — list active alerts
PATCH /alerts/{id}/acknowledge — acknowledge an alert
PATCH /alerts/{id}/resolve     — mark resolved
GET   /alerts/rules            — list rules per industry
PUT   /alerts/rules/{id}       — update a rule (analyst+)
POST  /alerts/rules            — create a rule
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models.alert import AlertRule, ShortageAlert
from app.models.enums import AlertStatus, IndustryCode
from app.routers.industry_router import ActiveIndustry, TenantId, UserId
from app.schemas.alert import (
    AlertAcknowledge,
    AlertRuleOut,
    AlertRuleUpdate,
    ShortageAlertOut,
)
from app.services import audit

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[ShortageAlertOut])
async def list_alerts(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    hours: int = Query(default=168, ge=1, le=720),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Any]:
    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    async with db.session(str(tenant_id)) as session:
        q = select(ShortageAlert).where(
            ShortageAlert.tenant_id == tenant_id,
            ShortageAlert.industry == industry,
            ShortageAlert.fired_at >= cutoff,
        )
        if status:
            q = q.where(ShortageAlert.status == status)
        if severity:
            q = q.where(ShortageAlert.severity == severity)
        q = q.order_by(ShortageAlert.fired_at.desc()).limit(limit)
        rows = await session.execute(q)
        return list(rows.scalars().all()) if hasattr(rows, "scalars") else list(rows or [])


@router.patch("/{alert_id}/acknowledge", response_model=ShortageAlertOut)
async def acknowledge_alert(
    alert_id: str,
    body: AlertAcknowledge,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> Any:
    db = request.app.state.db
    aid = uuid.UUID(alert_id)
    async with db.session(str(tenant_id)) as session:
        alert = await session.scalar(
            select(ShortageAlert).where(
                ShortageAlert.id == aid,
                ShortageAlert.tenant_id == tenant_id,
            )
        )
        if alert is None:
            raise NotFoundError("ShortageAlert")
        if alert.status not in (AlertStatus.open, AlertStatus.acknowledged):
            return alert  # idempotent for already resolved/suppressed
        old_status = alert.status.value
        alert.status = AlertStatus.acknowledged
        alert.acknowledged_by = user_id
        alert.acknowledged_at = datetime.now(UTC)
        if body.resolution_note:
            alert.resolution_note = body.resolution_note
        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="shortage_alert.acknowledge",
            entity_type="shortage_alert",
            entity_id=alert_id,
            industry=alert.industry,
            old_value={"status": old_status},
            new_value={"status": alert.status.value, "note": body.resolution_note},
            request_id=getattr(request.state, "request_id", None),
        )
    return alert


@router.patch("/{alert_id}/resolve", response_model=ShortageAlertOut)
async def resolve_alert(
    alert_id: str,
    body: AlertAcknowledge,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> Any:
    db = request.app.state.db
    aid = uuid.UUID(alert_id)
    async with db.session(str(tenant_id)) as session:
        alert = await session.scalar(
            select(ShortageAlert).where(
                ShortageAlert.id == aid,
                ShortageAlert.tenant_id == tenant_id,
            )
        )
        if alert is None:
            raise NotFoundError("ShortageAlert")
        alert.status = AlertStatus.resolved
        alert.resolved_at = datetime.now(UTC)
        if body.resolution_note:
            alert.resolution_note = body.resolution_note
    return alert


# ── Rules CRUD ──────────────────────────────────────────────────────────────


@router.get("/rules", response_model=list[AlertRuleOut])
async def list_rules(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
) -> list[Any]:
    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    async with db.session(str(tenant_id)) as session:
        q = (
            select(AlertRule)
            .where(
                AlertRule.tenant_id == tenant_id,
                AlertRule.industry == industry,
            )
            .order_by(AlertRule.rule_name)
        )
        rows = await session.execute(q)
        results = list(rows.scalars().all()) if hasattr(rows, "scalars") else list(rows or [])

    # If tenant has no rules yet, return industry defaults so the UI has
    # something to show (read-only until they save customizations).
    if not results:
        from sanket_ml.alerts.alert_rules import DEFAULT_RULES

        default = DEFAULT_RULES.get(ctx.code)
        if default:
            results = [
                AlertRule(
                    id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                    tenant_id=tenant_id,
                    industry=industry,
                    rule_name=f"{ctx.code}-default (unsaved)",
                    enabled=default.enabled,
                    warn_coverage_days=Decimal(str(default.warn_coverage_days)),
                    critical_coverage_days=Decimal(str(default.critical_coverage_days)),
                    trend_weight=Decimal(str(default.trend_weight)),
                    p90_weight=Decimal(str(default.p90_weight)),
                    inventory_weight=Decimal(str(default.inventory_weight)),
                    cooldown_minutes=default.cooldown_minutes,
                    notify_webhook=True,
                    notify_websocket=True,
                )
            ]
    return results


@router.post("/rules", response_model=AlertRuleOut, status_code=201)
async def create_rule(
    body: dict,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> Any:
    role = getattr(request.state, "role", "viewer")
    if role not in ("owner", "admin", "analyst"):
        raise PermissionDeniedError("Creating alert rules requires analyst role+")

    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    async with db.session(str(tenant_id)) as session:
        rule = AlertRule(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            industry=industry,
            rule_name=body.get("rule_name", "custom"),
            enabled=body.get("enabled", True),
            warn_coverage_days=Decimal(str(body["warn_coverage_days"])),
            critical_coverage_days=Decimal(str(body["critical_coverage_days"])),
            trend_weight=Decimal(str(body.get("trend_weight", 0.30))),
            p90_weight=Decimal(str(body.get("p90_weight", 0.40))),
            inventory_weight=Decimal(str(body.get("inventory_weight", 0.30))),
            cooldown_minutes=int(body.get("cooldown_minutes", 60)),
            notify_webhook=bool(body.get("notify_webhook", True)),
            notify_websocket=bool(body.get("notify_websocket", True)),
        )
        session.add(rule)
    return rule


@router.put("/rules/{rule_id}", response_model=AlertRuleOut)
async def update_rule(
    rule_id: str,
    body: AlertRuleUpdate,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> Any:
    role = getattr(request.state, "role", "viewer")
    if role not in ("owner", "admin", "analyst"):
        raise PermissionDeniedError("Updating alert rules requires analyst role+")

    db = request.app.state.db
    rid = uuid.UUID(rule_id)
    async with db.session(str(tenant_id)) as session:
        rule = await session.scalar(
            select(AlertRule).where(
                AlertRule.id == rid,
                AlertRule.tenant_id == tenant_id,
            )
        )
        if rule is None:
            raise NotFoundError("AlertRule")
        for k, v in body.model_dump(exclude_unset=True).items():
            setattr(rule, k, v)
    return rule
