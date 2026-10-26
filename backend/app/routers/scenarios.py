"""Scenario simulator API — the digital twin.

``POST /scenarios/simulate`` runs the tenant's *real* SKUs, *real* stock and
*real* forecast through the weekly inventory recursion twice (baseline and
scenario) and returns the difference. If there is no completed forecast run the
endpoint says so rather than simulating a made-up demand curve.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import get_settings
from app.core.exceptions import AuthenticationError
from app.models.enums import IndustryCode
from app.models.inventory import InventoryLevel
from app.models.product import Sku
from app.models.tenant import Tenant
from app.routers.industry_router import ActiveIndustry, TenantId
from app.services import scenario as sim
from app.services.decision_builder import (
    latest_completed_run,
    load_policy,
)
from app.services.decision_engine import DEFAULT_LEAD_TIME_DAYS, SkuEconomics
from app.services.planning_inputs import (
    future_forecast_bands,
    is_run_fresh,
    run_age_days,
    stock_is_stale,
)

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/scenarios", tags=["scenarios"])


class ScenarioBody(BaseModel):
    name: str = Field(default="Custom scenario", max_length=120)
    preset: str | None = Field(default=None, max_length=60)

    demand_shock_pct: float = Field(default=0.0, ge=-95.0, le=500.0)
    price_change_pct: float = Field(default=0.0, ge=-90.0, le=300.0)
    price_elasticity: float = Field(default=sim.DEFAULT_PRICE_ELASTICITY, ge=-5.0, le=0.0)
    lead_time_delta_days: int = Field(default=0, ge=-60, le=365)
    cost_change_pct: float = Field(default=0.0, ge=-90.0, le=300.0)
    supplier_outage_weeks: int = Field(default=0, ge=0, le=52)
    supplier_outage_sku_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    service_level: float | None = Field(default=None, ge=0.5, le=0.999)
    ramp_weeks: int = Field(default=0, ge=0, le=52)

    horizon_weeks: int = Field(default=26, ge=4, le=104)
    review_weeks: int = Field(default=4, ge=1, le=26)
    sku_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)

    def to_scenario(self) -> sim.Scenario:
        return sim.Scenario(
            name=self.name,
            demand_shock_pct=self.demand_shock_pct,
            price_change_pct=self.price_change_pct,
            price_elasticity=self.price_elasticity,
            lead_time_delta_days=self.lead_time_delta_days,
            cost_change_pct=self.cost_change_pct,
            supplier_outage_weeks=self.supplier_outage_weeks,
            supplier_outage_sku_ids=tuple(str(s) for s in self.supplier_outage_sku_ids),
            service_level=self.service_level,
            ramp_weeks=self.ramp_weeks,
        )


@router.get("/presets")
async def list_presets() -> dict[str, Any]:
    """The scenarios people actually ask about, one click each."""
    return {
        "presets": [
            {"key": key, **{k: v for k, v in spec.items() if k != "scenario"}, "scenario": spec["scenario"]}
            for key, spec in sim.PRESETS.items()
        ]
    }


@router.post("/simulate")
async def simulate(
    body: ScenarioBody,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
) -> dict[str, Any]:
    if body.preset:
        spec = sim.PRESETS.get(body.preset)
        if spec is None:
            raise HTTPException(status_code=400, detail=f"Unknown preset '{body.preset}'")
        # Preset values seed the request; anything the caller set explicitly on
        # top of a preset still wins, because the UI sends the merged sliders.
        merged = {**spec["scenario"]}
        scenario = sim.Scenario(
            **{
                **merged,
                "price_elasticity": body.price_elasticity,
                "supplier_outage_sku_ids": tuple(str(s) for s in body.supplier_outage_sku_ids),
            }
        )
    else:
        scenario = body.to_scenario()

    db = request.app.state.db
    industry = IndustryCode(ctx.code)

    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise AuthenticationError()
        policy = load_policy(tenant.settings)

        run = await latest_completed_run(session, tenant_id, industry)
        if run is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "No completed forecast run to simulate against. Generate a forecast first — "
                    "the twin runs on your real demand curve, not a synthetic one."
                ),
            )

        now = datetime.now(UTC)
        bands = await future_forecast_bands(session, tenant_id, run.id, now)
        if body.sku_ids:
            wanted = set(body.sku_ids)
            bands = {k: v for k, v in bands.items() if k in wanted}
        if not bands:
            raise HTTPException(
                status_code=422,
                detail=(
                    "The latest forecast run has no SKU-level results for the current or "
                    "future weeks. Generate a new forecast."
                ),
            )

        ids = list(bands)[: get_settings().forecast_max_skus]
        sku_rows = (
            await session.execute(
                select(Sku).where(
                    Sku.tenant_id == tenant_id,
                    Sku.industry == industry,
                    Sku.id.in_(ids),
                    Sku.is_active.is_(True),
                )
            )
        ).scalars().all()
        if not sku_rows:
            raise HTTPException(status_code=422, detail="No active SKUs matched the forecast run.")

        levels = (
            await session.execute(
                select(InventoryLevel).where(
                    InventoryLevel.tenant_id == tenant_id,
                    InventoryLevel.industry == industry,
                    InventoryLevel.sku_id.in_([s.id for s in sku_rows]),
                )
            )
        ).scalars().all()

    by_sku: dict[uuid.UUID, list[InventoryLevel]] = {}
    for lvl in levels:
        by_sku.setdefault(lvl.sku_id, []).append(lvl)

    currency = sku_rows[0].currency or "INR"
    economics = []
    band_map: dict[str, sim.DemandBand] = {}
    for s in sku_rows:
        rows = by_sku.get(s.id, [])
        # A SKU with no stock record starts from zero on hand: that is the
        # simulation's explicit assumption, disclosed in `readiness` below.
        economics.append(
            SkuEconomics(
                sku_id=str(s.id),
                sku_code=s.sku_code,
                on_hand_units=sum(float(r.on_hand_units or 0) for r in rows),
                reserved_units=sum(float(r.reserved_units or 0) for r in rows),
                inbound_units=sum(float(r.inbound_units or 0) for r in rows),
                lead_time_days=int(s.lead_time_days or DEFAULT_LEAD_TIME_DAYS),
                moq=int(s.moq or 1),
                unit_cost=float(s.unit_cost or 0),
                unit_price=float(s.unit_price or 0),
                currency=s.currency or "INR",
                configured_safety_stock=int(s.safety_stock or 0),
                cost_known=s.unit_cost is not None,
                price_known=s.unit_price is not None,
                lead_time_assumed=s.lead_time_days is None,
            )
        )
        band_map[str(s.id)] = bands[s.id]

    config = sim.SimConfig(
        horizon_weeks=body.horizon_weeks,
        review_weeks=body.review_weeks,
        holding_cost_pct=policy.holding_cost_pct,
        service_level=policy.service_level,
    )

    payload = sim.compare(
        skus=economics, bands=band_map, scenario=scenario, config=config, currency=currency
    )
    payload["run_id"] = str(run.id)
    payload["skus_simulated"] = len(economics)
    payload["stock_coverage"] = {
        "skus_with_recorded_stock": sum(1 for s in sku_rows if by_sku.get(s.id)),
        "skus_total": len(sku_rows),
    }
    payload["readiness"] = _readiness(run, sku_rows, by_sku, now)

    log.info(
        "scenario.simulated",
        tenant_id=str(tenant_id),
        preset=body.preset,
        skus=len(economics),
        horizon=body.horizon_weeks,
    )
    return payload


def _readiness(
    run: Any, sku_rows: list[Sku], by_sku: dict[uuid.UUID, list[InventoryLevel]], now: datetime
) -> dict[str, Any]:
    """Which inputs this simulation stands on, judged by the same contract as
    coverage and decisions. Any gap makes the result advisory."""
    codes = sorted(sku_rows, key=lambda s: s.sku_code)
    missing_stock = [s.sku_code for s in codes if not by_sku.get(s.id)]
    stale_stock = [
        s.sku_code for s in codes
        if by_sku.get(s.id) and any(stock_is_stale(r.as_of, now) for r in by_sku[s.id])
    ]
    lead_assumed = [s.sku_code for s in codes if s.lead_time_days is None]
    missing_cost = [s.sku_code for s in codes if s.unit_cost is None]
    missing_price = [s.sku_code for s in codes if s.unit_price is None]
    stale = not is_run_fresh(run, now)
    return {
        "forecast_run_id": str(run.id),
        "forecast_completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "forecast_age_days": run_age_days(run, now),
        "forecast_stale": stale,
        "skus_missing_stock": missing_stock,
        "skus_stale_stock": stale_stock,
        "skus_lead_time_assumed": lead_assumed,
        "skus_missing_cost": missing_cost,
        "skus_missing_price": missing_price,
        "assumed_lead_time_days": DEFAULT_LEAD_TIME_DAYS,
        "advisory": bool(
            stale or missing_stock or stale_stock or lead_assumed or missing_cost or missing_price
        ),
    }
