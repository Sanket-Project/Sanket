"""Financial impact router — revenue at risk and excess inventory costs."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app.models.enums import IndustryCode
from app.models.product import Sku
from app.routers.industry_router import ActiveIndustry, TenantId

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/financial", tags=["financial"])

HOLDING_COST_PCT = 0.25


@router.get("/impact")
async def financial_impact(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    horizon_weeks: int = 12,
) -> dict[str, Any]:
    """Compute revenue at risk (unmet upside demand) and excess inventory cost per SKU."""
    from app.models.forecast import ForecastResult, ForecastRun

    db = request.app.state.db
    industry = IndustryCode(ctx.code)

    async with db.session(str(tenant_id)) as session:
        # Get most recent completed forecast run
        run = await session.scalar(
            select(ForecastRun)
            .where(
                ForecastRun.tenant_id == tenant_id,
                ForecastRun.industry == industry,
                ForecastRun.status == "completed",
            )
            .order_by(ForecastRun.completed_at.desc())
            .limit(1)
        )
        if run is None:
            return {
                "industry": ctx.code,
                "horizon_weeks": horizon_weeks,
                "total_revenue_at_risk": 0,
                "total_excess_cost": 0,
                "net_impact": 0,
                "by_sku": [],
            }

        # Aggregate forecast per SKU
        fc_rows = await session.execute(
            select(
                ForecastResult.sku_id,
                func.sum(ForecastResult.p50).label("sum_p50"),
                func.sum(ForecastResult.p90).label("sum_p90"),
                func.count().label("n_weeks"),
            )
            .where(
                ForecastResult.run_id == run.id,
                ForecastResult.tenant_id == tenant_id,
            )
            .group_by(ForecastResult.sku_id)
            .limit(200)
        )
        fc_data = fc_rows.fetchall()

        sku_ids = [r.sku_id for r in fc_data]
        skus_rows = await session.execute(
            select(Sku).where(
                Sku.tenant_id == tenant_id,
                Sku.id.in_(sku_ids),
            )
        )
        skus = {s.id: s for s in skus_rows.scalars().all()}

    by_sku: list[dict] = []
    total_rar = 0.0
    total_excess = 0.0

    for fc in fc_data:
        sku = skus.get(fc.sku_id)
        if sku is None:
            continue
        unit_price = float(sku.unit_price or 0)
        unit_cost = float(sku.unit_cost or 0)
        p50 = float(fc.sum_p50 or 0)
        p90 = float(fc.sum_p90 or 0)
        ss = sku.safety_stock or 0

        # Revenue at risk: unmet demand in the optimistic (p90) scenario
        revenue_at_risk = max(0, p90 - p50) * unit_price
        # Excess inventory: safety stock above median demand is excess holding
        excess_units = max(0, ss - p50)
        excess_cost = excess_units * unit_cost * HOLDING_COST_PCT

        total_rar += revenue_at_risk
        total_excess += excess_cost

        by_sku.append(
            {
                "sku_id": str(fc.sku_id),
                "sku_code": sku.sku_code,
                "unit_price": unit_price,
                "unit_cost": unit_cost,
                "p50_demand": round(p50, 1),
                "p90_demand": round(p90, 1),
                "safety_stock": ss,
                "revenue_at_risk": round(revenue_at_risk, 2),
                "excess_inventory_cost": round(excess_cost, 2),
                "total_impact": round(revenue_at_risk + excess_cost, 2),
            }
        )

    by_sku.sort(key=lambda x: x["total_impact"], reverse=True)

    return {
        "industry": ctx.code,
        "horizon_weeks": horizon_weeks,
        "run_id": str(run.id),
        "total_revenue_at_risk": round(total_rar, 2),
        "total_excess_cost": round(total_excess, 2),
        "net_impact": round(total_rar + total_excess, 2),
        "by_sku": by_sku[:100],
    }
