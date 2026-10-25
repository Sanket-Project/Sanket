"""Data quality API — the dataset health report and its auto-fixes."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.rbac import require_admin
from app.models.enums import IndustryCode
from app.routers.industry_router import ActiveIndustry, TenantId, UserId
from app.services import audit, data_quality_audit

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/data-quality", tags=["data-quality"])


class FixBody(BaseModel):
    action: str = Field(pattern="^(dedupe_sales|drop_future_sales|drop_negative_sales)$")
    #: Deleting rows is irreversible, so the caller has to ask for it explicitly.
    #: A dry run returns the same shape with `applied: false`.
    confirm: bool = False


@router.get("/report")
async def report(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
) -> dict[str, Any]:
    """Full dataset audit: health score, findings, and what to fix first."""
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        return await data_quality_audit.audit(
            session, tenant_id=tenant_id, industry=ctx.code
        )


@router.post("/fix")
async def fix(
    body: FixBody,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
    _rbac: None = require_admin,
) -> dict[str, Any]:
    """Run one auto-fix. Without ``confirm`` this only reports what it would do.

    A confirmed fix deletes rows, so it is written to the audit log in the same
    transaction: either both happen or neither does.
    """
    db = request.app.state.db
    try:
        async with db.session(str(tenant_id)) as session:
            result = await data_quality_audit.apply_fix(
                session,
                tenant_id=tenant_id,
                industry=ctx.code,
                action=body.action,
                dry_run=not body.confirm,
            )
            if body.confirm:
                await audit.record(
                    session,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    industry=IndustryCode(ctx.code),
                    action="data_quality.fix",
                    entity_type="historical_sales",
                    new_value={
                        "action": body.action,
                        "rows_affected": result.get("rows_affected", 0),
                        "groups_conflicting": result.get("groups_conflicting"),
                    },
                    request_id=getattr(request.state, "request_id", None),
                )
            return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
