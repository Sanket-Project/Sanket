"""Inventory analytics router — current stock, EOQ calculations and cost analysis."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.rbac import require_admin
from app.models.enums import IndustryCode
from app.models.inventory import InventoryLevel
from app.models.product import Sku
from app.routers.industry_router import ActiveIndustry, TenantId, UserId

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/inventory", tags=["inventory"])


# ── Current stock: ingest + read ────────────────────────────────────────────


class InventoryLevelIn(BaseModel):
    sku_id: str
    on_hand_units: float = Field(ge=0)
    inbound_units: float = Field(default=0, ge=0)
    reserved_units: float = Field(default=0, ge=0)
    location: str = "default"
    as_of: datetime | None = None
    source: str = "manual"


class InventoryUpsertRequest(BaseModel):
    items: list[InventoryLevelIn] = Field(min_length=1, max_length=500)


@router.put("/levels")
async def upsert_levels(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
    body: InventoryUpsertRequest,
    _rbac: Annotated[None, require_admin],
) -> dict[str, Any]:
    """Ingest current warehouse stock. Requires admin or owner role.

    Upserts on (tenant, sku, location) so re-sending a SKU updates its
    position rather than duplicating it. Limited to 500 items per request
    to prevent unbounded bulk writes.
    """
    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    now = datetime.now(UTC)

    rows: list[dict] = []
    for it in body.items:
        try:
            sid = uuid.UUID(it.sku_id)
        except ValueError:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail=f"Invalid sku_id: {it.sku_id!r}")
        rows.append(
            {
                "tenant_id": tenant_id,
                "sku_id": sid,
                "industry": industry,
                "location": it.location,
                "on_hand_units": it.on_hand_units,
                "inbound_units": it.inbound_units,
                "reserved_units": it.reserved_units,
                "as_of": it.as_of or now,
                "source": it.source,
            }
        )

    stmt = pg_insert(InventoryLevel).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_inventory_tenant_sku_loc",
        set_={
            "on_hand_units": stmt.excluded.on_hand_units,
            "inbound_units": stmt.excluded.inbound_units,
            "reserved_units": stmt.excluded.reserved_units,
            "as_of": stmt.excluded.as_of,
            "source": stmt.excluded.source,
            "updated_at": func.now(),
        },
    )
    async with db.session(str(tenant_id)) as session:
        await session.execute(stmt)

    log.info("inventory.levels.upserted", tenant=str(tenant_id), industry=ctx.code, n=len(rows))
    return {"upserted": len(rows), "industry": ctx.code}


@router.get("/levels")
async def list_levels(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    limit: int = 200,
) -> dict[str, Any]:
    """Return current stock positions (with sku_code and available = on_hand − reserved)."""
    db = request.app.state.db
    industry = IndustryCode(ctx.code)

    async with db.session(str(tenant_id)) as session:
        rows = await session.execute(
            select(InventoryLevel, Sku.sku_code)
            .join(Sku, Sku.id == InventoryLevel.sku_id)
            .where(
                InventoryLevel.tenant_id == tenant_id,
                InventoryLevel.industry == industry,
            )
            .order_by(InventoryLevel.as_of.desc())
            .limit(limit)
        )
        records = rows.all()

    levels = [
        {
            "sku_id": str(lvl.sku_id),
            "sku_code": sku_code,
            "location": lvl.location,
            "on_hand_units": float(lvl.on_hand_units or 0),
            "inbound_units": float(lvl.inbound_units or 0),
            "reserved_units": float(lvl.reserved_units or 0),
            "available_units": float(lvl.available_units),
            "as_of": lvl.as_of.isoformat() if lvl.as_of else None,
            "source": lvl.source,
        }
        for lvl, sku_code in records
    ]
    return {"industry": ctx.code, "count": len(levels), "levels": levels}


@router.get("/eoq")
async def eoq_for_sku(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    sku_id: str,
    annual_demand: float | None = None,
    order_cost: float = 50.0,
    holding_cost_pct: float = 0.25,
) -> dict[str, Any]:
    """Compute Economic Order Quantity for a single SKU."""
    import uuid as _uuid

    from sanket_ml.optimization.eoq import EOQCalculator

    db = request.app.state.db
    sid = _uuid.UUID(sku_id)

    async with db.session(str(tenant_id)) as session:
        sku = await session.scalar(select(Sku).where(Sku.id == sid, Sku.tenant_id == tenant_id))
        if sku is None:
            return {"error": "SKU not found"}

        if annual_demand is None:
            from datetime import UTC, datetime, timedelta

            from app.models.historical_sales import HistoricalSale

            cutoff = datetime.now(UTC) - timedelta(weeks=52)
            annual_demand_row = await session.scalar(
                select(func.sum(HistoricalSale.units_sold)).where(
                    HistoricalSale.tenant_id == tenant_id,
                    HistoricalSale.sku_id == sid,
                    HistoricalSale.sale_time >= cutoff,
                )
            )
            annual_demand = float(annual_demand_row or 0)

        unit_cost = float(sku.unit_cost or 0)

    calc = EOQCalculator()
    result = calc.calculate(
        sku_id=str(sku_id),
        annual_demand=annual_demand,
        order_cost=order_cost,
        holding_cost_pct=holding_cost_pct,
        unit_cost=unit_cost,
    )
    sensitivity = calc.sensitivity(
        sku_id=str(sku_id),
        demand_range=[annual_demand * f for f in (0.5, 0.75, 1.0, 1.25, 1.5)],
        order_cost=order_cost,
        holding_cost_pct=holding_cost_pct,
        unit_cost=unit_cost,
    )
    return {
        "sku_id": sku_id,
        "sku_code": sku.sku_code,
        "eoq": {
            "eoq_units": result.eoq_units,
            "reorder_frequency_weeks": result.reorder_frequency_weeks,
            "annual_order_cost": result.annual_order_cost,
            "annual_holding_cost": result.annual_holding_cost,
            "total_annual_cost": result.total_annual_cost,
        },
        "inputs": {
            "annual_demand": annual_demand,
            "order_cost": order_cost,
            "holding_cost_pct": holding_cost_pct,
            "unit_cost": unit_cost,
        },
        "sensitivity": [
            {
                "annual_demand": r.annual_demand,
                "eoq_units": r.eoq_units,
                "total_annual_cost": r.total_annual_cost,
            }
            for r in sensitivity
        ],
    }


@router.get("/cost-analysis")
async def cost_analysis(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    holding_cost_pct: float = 0.25,
    limit: int = 50,
) -> dict[str, Any]:
    """Return per-SKU holding and stockout exposure costs, ranked by total impact."""
    db = request.app.state.db
    industry = IndustryCode(ctx.code)

    from app.services.inventory import current_levels

    async with db.session(str(tenant_id)) as session:
        rows = await session.execute(
            select(Sku)
            .where(
                Sku.tenant_id == tenant_id,
                Sku.industry == industry,
                Sku.is_active.is_(True),
            )
            .limit(limit)
        )
        skus = rows.scalars().all()
        inv_map = await current_levels(
            session,
            tenant_id=tenant_id,
            industry=ctx.code,
            sku_ids=[s.id for s in skus] or None,
        )

    results: list[dict] = []
    for sku in skus:
        uc = float(sku.unit_cost or 0)
        up = float(sku.unit_price or 0)
        ss = sku.safety_stock or 0
        rop = sku.reorder_point or 0

        # Holding cost is charged on the stock actually sitting in the warehouse;
        # fall back to safety_stock only when no real position has been ingested.
        snap = inv_map.get(str(sku.id))
        on_hand = snap.available_units if snap is not None else float(ss)
        on_hand_source = "inventory" if snap is not None else "fallback"

        holding_cost = uc * on_hand * holding_cost_pct
        # Excess inventory: stock held above the safety-stock target.
        excess_units = max(0.0, on_hand - float(ss))
        excess_holding_cost = uc * excess_units * holding_cost_pct
        # Margin-based stockout exposure: lost gross profit per unit at risk
        # between reorder point and safety stock.
        exposed_units = max(0, rop - ss)
        gross_margin = max(0, up - uc)
        stockout_cost = exposed_units * gross_margin

        results.append(
            {
                "sku_id": str(sku.id),
                "sku_code": sku.sku_code,
                "unit_cost": uc,
                "unit_price": up,
                "on_hand_units": round(on_hand, 2),
                "on_hand_source": on_hand_source,
                "safety_stock": ss,
                "reorder_point": rop,
                "holding_cost_annual": round(holding_cost, 2),
                "excess_holding_cost": round(excess_holding_cost, 2),
                "stockout_exposure_cost": round(stockout_cost, 2),
                "total_impact": round(holding_cost + stockout_cost, 2),
            }
        )

    results.sort(key=lambda x: x["total_impact"], reverse=True)
    total_holding = sum(r["holding_cost_annual"] for r in results)
    total_stockout = sum(r["stockout_exposure_cost"] for r in results)

    return {
        "industry": ctx.code,
        "holding_cost_pct": holding_cost_pct,
        "totals": {
            "annual_holding_cost": round(total_holding, 2),
            "stockout_exposure_cost": round(total_stockout, 2),
            "total_impact": round(total_holding + total_stockout, 2),
        },
        "skus": results,
    }
