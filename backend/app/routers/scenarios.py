"""Scenario simulator API — the digital twin.

``POST /scenarios/simulate`` runs the tenant's *real* SKUs, *real* stock and
*real* forecast through the weekly inventory recursion twice (baseline and
scenario) and returns the difference. If there is no completed forecast run the
endpoint says so rather than simulating a made-up demand curve.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.exceptions import AuthenticationError
from app.models.enums import IndustryCode
from app.models.product import Sku
from app.models.tenant import Tenant
from app.routers.industry_router import ActiveIndustry, TenantId
from app.services import scenario as sim
from app.services.decision_builder import (
    MAX_SKUS,
    forecast_bands,
    latest_completed_run,
    load_policy,
)
from app.services.decision_engine import DEFAULT_LEAD_TIME_DAYS, SkuEconomics
from app.services.inventory import current_levels

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

        bands = await forecast_bands(session, tenant_id, run.id)
        if body.sku_ids:
            wanted = set(body.sku_ids)
            bands = {k: v for k, v in bands.items() if k in wanted}
        if not bands:
            raise HTTPException(
                status_code=422, detail="The latest forecast run produced no SKU-level results."
            )

        ids = list(bands)[:MAX_SKUS]
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

        stock = await current_levels(
            session, tenant_id=tenant_id, industry=ctx.code, sku_ids=[s.id for s in sku_rows]
        )

    currency = sku_rows[0].currency or "INR"
    economics = []
    band_map: dict[str, sim.DemandBand] = {}
    for s in sku_rows:
        snap = stock.get(str(s.id))
        economics.append(
            SkuEconomics(
                sku_id=str(s.id),
                sku_code=s.sku_code,
                on_hand_units=float(snap.on_hand_units) if snap else 0.0,
                reserved_units=float(snap.reserved_units) if snap else 0.0,
                inbound_units=float(snap.inbound_units) if snap else 0.0,
                lead_time_days=int(s.lead_time_days or DEFAULT_LEAD_TIME_DAYS),
                moq=int(s.moq or 1),
                unit_cost=float(s.unit_cost or 0),
                unit_price=float(s.unit_price or 0),
                currency=s.currency or "INR",
                configured_safety_stock=int(s.safety_stock or 0),
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
        "skus_with_recorded_stock": sum(1 for s in sku_rows if str(s.id) in stock),
        "skus_total": len(sku_rows),
    }

    log.info(
        "scenario.simulated",
        tenant_id=str(tenant_id),
        preset=body.preset,
        skus=len(economics),
        horizon=body.horizon_weeks,
    )
    return payload
