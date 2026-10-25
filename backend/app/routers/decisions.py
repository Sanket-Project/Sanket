"""Decision engine API — recommendations, not just predictions.

``GET /decisions`` returns the current queue. ``POST /decisions/refresh``
recomputes it from the latest forecast run. Accept/dismiss record what the
planner actually did, which is what the ROI ledger is later computed from.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.exceptions import AuthenticationError
from app.core.rbac import require_admin
from app.models.enums import DecisionStatus, IndustryCode
from app.models.product import Sku
from app.models.recommendation import Recommendation
from app.models.tenant import Tenant
from app.routers.industry_router import ActiveIndustry, TenantId, UserId
from app.services import decision_builder
from app.services.decision_builder import load_policy, serialize
from app.services.forecast_gate import assert_forecastable

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/decisions", tags=["decisions"])


class AcceptBody(BaseModel):
    #: Lets the planner commit to a different quantity than we proposed —
    #: the ROI ledger records what they actually ordered, not what we asked for.
    units: int | None = Field(default=None, ge=0, le=10_000_000)
    note: str | None = Field(default=None, max_length=500)


class DismissBody(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class PolicyBody(BaseModel):
    service_level: float = Field(default=0.97, ge=0.50, le=0.999)
    review_period_days: int = Field(default=28, ge=1, le=180)
    holding_cost_pct: float = Field(default=0.25, ge=0.0, le=2.0)
    min_confidence_to_act: int = Field(default=60, ge=0, le=100)


async def _sku_codes(session, tenant_id: uuid.UUID, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(Sku.id, Sku.sku_code).where(Sku.tenant_id == tenant_id, Sku.id.in_(ids))
        )
    ).fetchall()
    return {r.id: r.sku_code for r in rows}


@router.get("")
async def list_decisions(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    status: str = Query(default="open", pattern="^(open|accepted|dismissed|expired|all)$"),
    kind: str | None = Query(default=None, pattern="^(purchase_order|excess_stock|safety_stock_update)$"),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """The decision queue for the active industry, most urgent first."""
    db = request.app.state.db
    industry = IndustryCode(ctx.code)

    async with db.session(str(tenant_id)) as session:
        stmt = select(Recommendation).where(
            Recommendation.tenant_id == tenant_id,
            Recommendation.industry == industry,
        )
        if status != "all":
            stmt = stmt.where(Recommendation.status == DecisionStatus(status))
        if kind:
            stmt = stmt.where(Recommendation.kind == kind)
        rows = (
            await session.execute(stmt.order_by(Recommendation.created_at.desc()).limit(limit))
        ).scalars().all()
        codes = await _sku_codes(session, tenant_id, [r.sku_id for r in rows])

    urgency_rank = {"critical": 0, "high": 1, "normal": 2, "low": 3}
    items = [serialize(r, sku_code=codes.get(r.sku_id)) for r in rows]
    items.sort(key=lambda i: (urgency_rank.get(i["urgency"], 9), -i["confidence"]))

    return {
        "industry": ctx.code,
        "status": status,
        "count": len(items),
        "decisions": items,
        "totals": _totals(items),
    }


def _totals(items: list[dict]) -> dict[str, Any]:
    orders = [i for i in items if i["kind"] == "purchase_order"]
    return {
        "purchase_orders": len(orders),
        "units_to_order": sum(i["recommended_units"] for i in orders),
        "capital_committed": round(
            sum(float(i["economics"].get("capital_committed") or 0) for i in orders), 2
        ),
        "working_capital_released_vs_baseline": round(
            sum(float(i["economics"].get("working_capital_released") or 0) for i in orders), 2
        ),
        "revenue_protected": round(
            sum(float(i["economics"].get("revenue_protected") or 0) for i in orders), 2
        ),
        "critical": sum(1 for i in items if i["urgency"] == "critical"),
        "currency": orders[0]["currency"] if orders else (items[0]["currency"] if items else "INR"),
    }


@router.post("/refresh")
async def refresh_decisions(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
) -> dict[str, Any]:
    """Recompute the queue from the latest completed forecast run."""
    db = request.app.state.db

    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise AuthenticationError()
        await assert_forecastable(session, tenant_id=tenant_id, industry=ctx.code)
        result, rows = await decision_builder.refresh(
            session,
            tenant_id=tenant_id,
            industry=ctx.code,
            tenant_settings=tenant.settings,
        )
        codes = await _sku_codes(session, tenant_id, [r.sku_id for r in rows])
        items = [serialize(r, sku_code=codes.get(r.sku_id)) for r in rows]

    if not rows and result.reason:
        # Not an error — a tenant with no forecast yet is a normal state, and
        # the reason is the actionable part of the response.
        return {
            "industry": ctx.code,
            "generated": 0,
            "skus_evaluated": result.skus_evaluated,
            "reason": result.reason,
            "decisions": [],
            "totals": _totals([]),
        }

    return {
        "industry": ctx.code,
        "generated": len(items),
        "skus_evaluated": result.skus_evaluated,
        "run_id": str(result.run_id) if result.run_id else None,
        "decisions": items,
        "totals": _totals(items),
    }


@router.post("/{decision_id}/accept")
async def accept_decision(
    decision_id: uuid.UUID,
    body: AcceptBody,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> dict[str, Any]:
    """Record that the planner is acting on this recommendation."""
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        rec = await _load(session, tenant_id, ctx.code, decision_id)
        if rec.status != DecisionStatus.open:
            raise HTTPException(status_code=409, detail=f"Already {rec.status}")
        rec.status = DecisionStatus.accepted
        rec.accepted_units = body.units if body.units is not None else rec.recommended_units
        rec.decided_at = datetime.now(UTC)
        rec.decided_by = user_id
        if body.note:
            rec.dismissal_reason = None
            econ = dict(rec.economics or {})
            econ["note"] = body.note
            rec.economics = econ
        await session.flush()
        payload = serialize(rec)

    log.info("decisions.accepted", tenant_id=str(tenant_id), decision_id=str(decision_id))
    return payload


@router.post("/{decision_id}/dismiss")
async def dismiss_decision(
    decision_id: uuid.UUID,
    body: DismissBody,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> dict[str, Any]:
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        rec = await _load(session, tenant_id, ctx.code, decision_id)
        if rec.status != DecisionStatus.open:
            raise HTTPException(status_code=409, detail=f"Already {rec.status}")
        rec.status = DecisionStatus.dismissed
        rec.decided_at = datetime.now(UTC)
        rec.decided_by = user_id
        rec.dismissal_reason = body.reason
        await session.flush()
        payload = serialize(rec)

    log.info("decisions.dismissed", tenant_id=str(tenant_id), decision_id=str(decision_id))
    return payload


@router.get("/policy")
async def get_policy(request: Request, tenant_id: TenantId) -> dict[str, Any]:
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise AuthenticationError()
        policy = load_policy(tenant.settings)
    return {
        "service_level": policy.service_level,
        "review_period_days": policy.review_period_days,
        "holding_cost_pct": policy.holding_cost_pct,
        "min_confidence_to_act": policy.min_confidence_to_act,
    }


@router.put("/policy")
async def update_policy(
    body: PolicyBody,
    request: Request,
    tenant_id: TenantId,
    _rbac: None = require_admin,
) -> dict[str, Any]:
    """Ordering policy is a commercial commitment (service level, review cycle),
    so it is admin-only like the other tenant-wide settings."""
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise AuthenticationError()
        settings = dict(tenant.settings or {})
        settings["decisions"] = body.model_dump(mode="json")
        tenant.settings = settings
        await session.flush()

    log.info("decisions.policy.updated", tenant_id=str(tenant_id))
    return body.model_dump(mode="json")


async def _load(
    session, tenant_id: uuid.UUID, industry: str, decision_id: uuid.UUID
) -> Recommendation:
    rec = await session.scalar(
        select(Recommendation).where(
            Recommendation.id == decision_id,
            Recommendation.tenant_id == tenant_id,
            Recommendation.industry == IndustryCode(industry),
        )
    )
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return rec
