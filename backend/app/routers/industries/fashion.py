from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app.models.enums import IndustryCode
from app.models.product import Product, Sku
from app.models.trend import TrendSignal
from app.routers.industry_router import ActiveIndustry, TenantId
from app.services.industry_context import FASHION

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/fashion", tags=["fashion"])


@router.get("/overview")
async def fashion_overview(
    request: Request, ctx: ActiveIndustry, tenant_id: TenantId
) -> dict[str, Any]:
    """Return fashion-vertical KPIs: product counts, active signals, top categories."""
    db = request.app.state.db

    async with db.session(str(tenant_id)) as session:
        total_skus = (
            await session.scalar(
                select(func.count(Sku.id)).where(
                    Sku.tenant_id == tenant_id,
                    Sku.industry == IndustryCode.fashion,
                    Sku.is_active.is_(True),
                )
            )
            or 0
        )

        total_products = (
            await session.scalar(
                select(func.count(Product.id)).where(
                    Product.tenant_id == tenant_id,
                    Product.industry == IndustryCode.fashion,
                )
            )
            or 0
        )

        active_signals = (
            await session.scalar(
                select(func.count(TrendSignal.id)).where(
                    TrendSignal.industry == IndustryCode.fashion,
                )
            )
            or 0
        )

        category_rows = await session.execute(
            select(Product.category, func.count(Product.id).label("count"))
            .where(Product.tenant_id == tenant_id, Product.industry == IndustryCode.fashion)
            .group_by(Product.category)
            .order_by(func.count(Product.id).desc())
            .limit(5)
        )
        top_categories = [{"category": r.category, "count": r.count} for r in category_rows]

    return {
        "industry": "fashion",
        "kpis": {
            "active_skus": total_skus,
            "total_products": total_products,
            "validated_signals": active_signals,
        },
        "top_categories": top_categories,
        "forecast_horizon_weeks": FASHION.default_horizon_weeks,
        "active_models": FASHION.forecast_models,
    }


@router.get("/size-curve/{product_id}")
async def size_curve(
    product_id: str, request: Request, ctx: ActiveIndustry, tenant_id: TenantId
) -> dict[str, Any]:
    """Aggregate historical sales by size attribute to produce a size-run curve."""
    import uuid as _uuid

    from app.models.sales import HistoricalSale

    db = request.app.state.db
    pid = _uuid.UUID(product_id)

    async with db.session(str(tenant_id)) as session:
        sku_rows = await session.execute(
            select(Sku.id, Sku.attributes).where(
                Sku.tenant_id == tenant_id,
                Sku.product_id == pid,
                Sku.industry == IndustryCode.fashion,
                Sku.is_active.is_(True),
            )
        )
        skus = sku_rows.all()

    if not skus:
        return {"product_id": product_id, "size_curve": []}

    async with db.session(str(tenant_id)) as session:
        size_totals: dict[str, int] = {}
        for row in skus:
            size = row.attributes.get("size", "UNKNOWN")
            sales_total = (
                await session.scalar(
                    select(func.sum(HistoricalSale.units_sold)).where(
                        HistoricalSale.tenant_id == tenant_id,
                        HistoricalSale.sku_id == row.id,
                    )
                )
                or 0
            )
            size_totals[size] = size_totals.get(size, 0) + int(sales_total)

    grand_total = sum(size_totals.values()) or 1
    size_curve = [
        {"size": s, "units": u, "share_pct": round(u / grand_total * 100, 2)}
        for s, u in sorted(size_totals.items(), key=lambda x: -x[1])
    ]
    return {"product_id": product_id, "size_curve": size_curve}
