from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app.models.enums import IndustryCode
from app.models.product import Product, Sku
from app.models.signal import ExternalSignal
from app.models.trend import TrendSignal
from app.routers.industry_router import ActiveIndustry, TenantId
from app.services.industry_context import HARDWARE

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/hardware", tags=["hardware"])


@router.get("/overview")
async def hardware_overview(
    request: Request, ctx: ActiveIndustry, tenant_id: TenantId
) -> dict[str, Any]:
    """Return hardware-vertical KPIs: catalog depth, pricing & supply-chain signals."""
    db = request.app.state.db

    async with db.session(str(tenant_id)) as session:
        total_skus = (
            await session.scalar(
                select(func.count(Sku.id)).where(
                    Sku.tenant_id == tenant_id,
                    Sku.industry == IndustryCode.hardware,
                    Sku.is_active.is_(True),
                )
            )
            or 0
        )

        total_products = (
            await session.scalar(
                select(func.count(Product.id)).where(
                    Product.tenant_id == tenant_id,
                    Product.industry == IndustryCode.hardware,
                )
            )
            or 0
        )

        price_signals = (
            await session.scalar(
                select(func.count(TrendSignal.id)).where(
                    TrendSignal.industry == IndustryCode.hardware,
                    TrendSignal.kind.in_(("economic_indicator", "commodity_price")),
                )
            )
            or 0
        )

        supply_signals = (
            await session.scalar(
                select(func.count(ExternalSignal.id)).where(
                    ExternalSignal.tenant_id == tenant_id,
                    ExternalSignal.industry == IndustryCode.hardware,
                    ExternalSignal.signal_type.in_(("logistics_disruption", "supplier_lead")),
                    ExternalSignal.status == "validated",
                )
            )
            or 0
        )

        category_rows = await session.execute(
            select(Product.category, func.count(Product.id).label("count"))
            .where(
                Product.tenant_id == tenant_id,
                Product.industry == IndustryCode.hardware,
            )
            .group_by(Product.category)
            .order_by(func.count(Product.id).desc())
            .limit(6)
        )
        top_categories = [{"category": r.category, "count": r.count} for r in category_rows]

    return {
        "industry": "hardware",
        "kpis": {
            "active_skus": total_skus,
            "total_products": total_products,
            "active_price_signals": price_signals,
            "validated_supply_signals": supply_signals,
        },
        "top_categories": top_categories,
        "forecast_horizon_weeks": HARDWARE.default_horizon_weeks,
        "active_models": HARDWARE.forecast_models,
    }


@router.get("/supply-risk/{category}")
async def supply_risk(
    category: str, request: Request, ctx: ActiveIndustry, tenant_id: TenantId
) -> dict[str, Any]:
    """Return a lead-time / supply-risk assessment for the SKUs in a category."""
    db = request.app.state.db

    async with db.session(str(tenant_id)) as session:
        rows = await session.execute(
            select(Sku, Product.category)
            .join(Product, Sku.product_id == Product.id)
            .where(
                Sku.tenant_id == tenant_id,
                Sku.industry == IndustryCode.hardware,
                Sku.is_active.is_(True),
                func.lower(Product.category) == category.lower(),
            )
        )
        records = rows.all()

    skus = [r[0] for r in records]
    lead_times = [int(s.lead_time_days or 0) for s in skus]
    avg_lead = round(sum(lead_times) / len(lead_times), 1) if lead_times else 0.0
    long_lead = sum(1 for lt in lead_times if lt >= 30)

    risk = "low"
    if avg_lead >= 30:
        risk = "high"
    elif avg_lead >= 18:
        risk = "medium"

    return {
        "category": category,
        "total_skus": len(skus),
        "avg_lead_time_days": avg_lead,
        "long_lead_skus": long_lead,
        "supply_risk": risk,
    }
