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
from app.services.industry_context import ELECTRONICS

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/electronics", tags=["electronics"])


@router.get("/overview")
async def electronics_overview(
    request: Request, ctx: ActiveIndustry, tenant_id: TenantId
) -> dict[str, Any]:
    """Return electronics-vertical KPIs: SKU counts, component risk signals, top categories."""
    db = request.app.state.db

    async with db.session(str(tenant_id)) as session:
        total_skus = (
            await session.scalar(
                select(func.count(Sku.id)).where(
                    Sku.tenant_id == tenant_id,
                    Sku.industry == IndustryCode.electronics,
                    Sku.is_active.is_(True),
                )
            )
            or 0
        )

        total_products = (
            await session.scalar(
                select(func.count(Product.id)).where(
                    Product.tenant_id == tenant_id,
                    Product.industry == IndustryCode.electronics,
                )
            )
            or 0
        )

        disruption_signals = (
            await session.scalar(
                select(func.count(TrendSignal.id)).where(
                    TrendSignal.industry == IndustryCode.electronics,
                    TrendSignal.kind.in_(("news_sentiment", "economic_indicator")),
                )
            )
            or 0
        )

        competitor_signals = (
            await session.scalar(
                select(func.count(TrendSignal.id)).where(
                    TrendSignal.industry == IndustryCode.electronics,
                    TrendSignal.kind.in_(("search_interest", "social_buzz")),
                )
            )
            or 0
        )

        category_rows = await session.execute(
            select(Product.category, func.count(Product.id).label("count"))
            .where(Product.tenant_id == tenant_id, Product.industry == IndustryCode.electronics)
            .group_by(Product.category)
            .order_by(func.count(Product.id).desc())
            .limit(5)
        )
        top_categories = [{"category": r.category, "count": r.count} for r in category_rows]

    return {
        "industry": "electronics",
        "kpis": {
            "active_skus": total_skus,
            "total_products": total_products,
            "logistics_disruption_signals": disruption_signals,
            "competitor_price_signals": competitor_signals,
        },
        "top_categories": top_categories,
        "forecast_horizon_weeks": ELECTRONICS.default_horizon_weeks,
        "active_models": ELECTRONICS.forecast_models,
    }


@router.get("/component-risk/{sku_id}")
async def component_risk(
    sku_id: str, request: Request, ctx: ActiveIndustry, tenant_id: TenantId
) -> dict[str, Any]:
    """Return component supply-risk assessment for a given electronics SKU."""
    import uuid as _uuid

    db = request.app.state.db
    sid = _uuid.UUID(sku_id)

    async with db.session(str(tenant_id)) as session:
        sku_row = await session.scalar(
            select(Sku).where(
                Sku.id == sid,
                Sku.tenant_id == tenant_id,
                Sku.industry == IndustryCode.electronics,
            )
        )
        if sku_row is None:
            return {"error": "SKU not found", "sku_id": sku_id}

        component_ids: list[str] = sku_row.attributes.get("component_ids", [])

        disruption_count = (
            await session.scalar(
                select(func.count(ExternalSignal.id)).where(
                    ExternalSignal.tenant_id == tenant_id,
                    ExternalSignal.industry == IndustryCode.electronics,
                    ExternalSignal.signal_type == "logistics_disruption",
                    ExternalSignal.status == "validated",
                )
            )
            or 0
        )

    risk_level = "low"
    if disruption_count > 10:
        risk_level = "critical"
    elif disruption_count > 5:
        risk_level = "high"
    elif disruption_count > 2:
        risk_level = "medium"

    return {
        "sku_id": sku_id,
        "sku_code": sku_row.sku_code,
        "component_ids": component_ids,
        "active_disruption_signals": disruption_count,
        "risk_level": risk_level,
        "lead_time_days": sku_row.lead_time_days,
        "safety_stock": sku_row.safety_stock,
        "reorder_point": sku_row.reorder_point,
    }
