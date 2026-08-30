"""ROI dashboard API — realized value, traced to accepted decisions."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Query, Request

from app.routers.industry_router import ActiveIndustry, TenantId
from app.services import roi

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/roi", tags=["roi"])


@router.get("/summary")
async def roi_summary(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    window_days: int = Query(default=roi.DEFAULT_WINDOW_DAYS, ge=7, le=730),
) -> dict[str, Any]:
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        return await roi.summary(
            session, tenant_id=tenant_id, industry=ctx.code, window_days=window_days
        )
