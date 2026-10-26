"""Financial impact router — revenue at risk and excess inventory costs."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app.core.money import totals_by_currency
from app.models.enums import IndustryCode
from app.models.product import Sku
from app.routers.industry_router import ActiveIndustry, TenantId
from app.services.decision_builder import latest_completed_run

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
    from app.models.forecast import ForecastResult

    db = request.app.state.db
    industry = IndustryCode(ctx.code)

    async with db.session(str(tenant_id)) as session:
        # The forecast a planner acts on — never an after-the-fact backtest.
        run = await latest_completed_run(session, tenant_id, industry)
        if run is None:
            return {
                "industry": ctx.code,
                "horizon_weeks": horizon_weeks,
                "currency": None,
                "total_revenue_at_risk": 0,
                "total_excess_cost": 0,
                "net_impact": 0,
                "totals_by_currency": {},
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

        by_sku.append(
            {
                "sku_id": str(fc.sku_id),
                "sku_code": sku.sku_code,
                "currency": sku.currency,
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
    # Exposure is in each SKU's currency; amounts in different currencies are
    # reported side by side, never summed (and impact ranking is per currency).
    currency, totals, by_currency = totals_by_currency(
        by_sku, ("revenue_at_risk", "excess_inventory_cost", "total_impact")
    )

    return {
        "industry": ctx.code,
        "horizon_weeks": horizon_weeks,
        "run_id": str(run.id),
        "currency": currency,
        "total_revenue_at_risk": totals["revenue_at_risk"],
        "total_excess_cost": totals["excess_inventory_cost"],
        "net_impact": totals["total_impact"],
        "totals_by_currency": by_currency,
        "by_sku": by_sku[:100],
    }
