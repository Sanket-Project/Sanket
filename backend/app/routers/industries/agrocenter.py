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
from app.services.industry_context import AGROCENTER

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/agrocenter", tags=["agrocenter"])


@router.get("/overview")
async def agrocenter_overview(
    request: Request, ctx: ActiveIndustry, tenant_id: TenantId
) -> dict[str, Any]:
    """Return agrocenter-vertical KPIs: input type breakdown, weather & regulatory signals."""
    db = request.app.state.db

    async with db.session(str(tenant_id)) as session:
        total_skus = (
            await session.scalar(
                select(func.count(Sku.id)).where(
                    Sku.tenant_id == tenant_id,
                    Sku.industry == IndustryCode.agrocenter,
                    Sku.is_active.is_(True),
                )
            )
            or 0
        )

        total_products = (
            await session.scalar(
                select(func.count(Product.id)).where(
                    Product.tenant_id == tenant_id,
                    Product.industry == IndustryCode.agrocenter,
                )
            )
            or 0
        )

        weather_signals = (
            await session.scalar(
                select(func.count(TrendSignal.id)).where(
                    TrendSignal.industry == IndustryCode.agrocenter,
                    TrendSignal.kind.in_(("economic_indicator", "news_sentiment")),
                )
            )
            or 0
        )

        regulatory_signals = (
            await session.scalar(
                select(func.count(ExternalSignal.id)).where(
                    ExternalSignal.tenant_id == tenant_id,
                    ExternalSignal.industry == IndustryCode.agrocenter,
                    ExternalSignal.signal_type == "regulatory",
                    ExternalSignal.status == "validated",
                )
            )
            or 0
        )

        category_rows = await session.execute(
            select(Product.category, func.count(Product.id).label("count"))
            .where(
                Product.tenant_id == tenant_id,
                Product.industry == IndustryCode.agrocenter,
            )
            .group_by(Product.category)
            .order_by(func.count(Product.id).desc())
            .limit(6)
        )
        top_categories = [{"category": r.category, "count": r.count} for r in category_rows]

    return {
        "industry": "agrocenter",
        "kpis": {
            "active_skus": total_skus,
            "total_products": total_products,
            "active_weather_signals": weather_signals,
            "validated_regulatory_signals": regulatory_signals,
        },
        "top_categories": top_categories,
        "forecast_horizon_weeks": AGROCENTER.default_horizon_weeks,
        "active_models": AGROCENTER.forecast_models,
    }


@router.get("/input-coverage/{crop_type}")
async def input_coverage(
    crop_type: str, request: Request, ctx: ActiveIndustry, tenant_id: TenantId
) -> dict[str, Any]:
    """Return coverage assessment of farm inputs available for the given crop type."""
    db = request.app.state.db

    async with db.session(str(tenant_id)) as session:
        rows = await session.execute(
            select(Sku).where(
                Sku.tenant_id == tenant_id,
                Sku.industry == IndustryCode.agrocenter,
                Sku.is_active.is_(True),
            )
        )
        skus = rows.scalars().all()

    crop_skus = [
        s
        for s in skus
        if isinstance(s.attributes, dict)
        and s.attributes.get("crop_type", "").lower() == crop_type.lower()
    ]

    by_type: dict[str, int] = {}
    for s in crop_skus:
        pt = (
            s.attributes.get("product_type", "unknown")
            if isinstance(s.attributes, dict)
            else "unknown"
        )
        by_type[pt] = by_type.get(pt, 0) + 1

    covered_types = set(by_type.keys()) & {"pesticide", "feed", "fertilizer"}
    coverage_pct = round(len(covered_types) / 3 * 100, 1)

    return {
        "crop_type": crop_type,
        "total_skus": len(crop_skus),
        "by_input_type": by_type,
        "essential_types_covered": sorted(covered_types),
        "coverage_pct": coverage_pct,
    }
