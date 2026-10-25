"""Forecast accuracy router — date-matched production accuracy plus explicit backtests."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Query, Request

from app.routers.industry_router import ActiveIndustry, TenantId
from app.services.forecast_accuracy import compute_accuracy

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/forecast", tags=["forecast-accuracy"])


@router.get("/accuracy")
async def forecast_accuracy(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """Per-SKU WAPE / bias / interval coverage of forecasts against what sold.

    Each forecast week (Monday 00:00 UTC) is matched with the same week's
    sales. Production accuracy only counts forecasts made before their week
    began from history that ended before it; backtests are reported apart.
    Anything not scored is counted under ``excluded`` with its reason.
    """
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        return await compute_accuracy(
            session, tenant_id=tenant_id, industry=ctx.code, limit=limit
        )
