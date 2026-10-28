"""Store / warehouse network: list (registering any newly seen codes) and edit."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.core.rbac import require_admin
from app.models.enums import IndustryCode, LocationKind
from app.models.inventory import InventoryLevel
from app.models.location import Location
from app.models.sales import HistoricalSale
from app.routers.industry_router import ActiveIndustry, TenantId
from app.services.locations import load_locations, network_readiness, sync_locations

router = APIRouter(prefix="/locations", tags=["locations"])


class LocationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    kind: LocationKind | None = None
    parent_location_id: uuid.UUID | None = None
    lead_time_days_from_parent: int | None = Field(default=None, ge=0, le=365)
    is_active: bool | None = None


def _out(l: Location) -> dict[str, Any]:
    return {
        "id": str(l.id), "code": l.code, "name": l.name, "kind": str(l.kind),
        "parent_location_id": str(l.parent_location_id) if l.parent_location_id else None,
        "lead_time_days_from_parent": l.lead_time_days_from_parent,
        "is_active": l.is_active,
    }


def _network(locs: list[Location]) -> dict[str, Any]:
    r = network_readiness(locs)
    return {"allocation_ready": r.allocation_ready, "transfers_ready": r.transfers_ready,
            "missing": r.missing}


@router.get("")
async def list_locations(request: Request, tenant_id: TenantId, ctx: ActiveIndustry) -> dict[str, Any]:
    from datetime import UTC, datetime

    from app.services.decision_builder import latest_completed_run
    from app.services.planning_inputs import is_run_fresh

    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        await sync_locations(session, tenant_id)
        locs = await load_locations(session, tenant_id)
        sale_code = func.lower(func.btrim(HistoricalSale.location))
        stock_code = func.lower(func.btrim(InventoryLevel.location))
        last_sales = dict((await session.execute(select(sale_code, func.max(HistoricalSale.sale_time))
            .where(HistoricalSale.tenant_id == tenant_id).group_by(sale_code))).all())
        last_stock = dict((await session.execute(select(stock_code, func.max(InventoryLevel.as_of))
            .where(InventoryLevel.tenant_id == tenant_id).group_by(stock_code))).all())
        run = await latest_completed_run(session, tenant_id, IndustryCode(ctx.code))
        metrics = run.metrics or {} if is_run_fresh(run, datetime.now(UTC)) else {}
    network = _network(locs)
    network.update(unassigned_share=metrics.get("unassigned_share"), degraded=bool(metrics.get("location_degraded")))
    return {"locations": [{**_out(l),
        "last_sale_at": last_sales[l.code].isoformat() if last_sales.get(l.code) else None,
        "last_stock_at": last_stock[l.code].isoformat() if last_stock.get(l.code) else None,
    } for l in locs], "network": network}


@router.get("/forecast")
async def location_forecast(request: Request, tenant_id: TenantId, ctx: ActiveIndustry,
                            sku_id: uuid.UUID, run_id: uuid.UUID | None = None) -> dict[str, Any]:
    from datetime import UTC, datetime

    from app.models.forecast import ForecastRun
    from app.services.decision_builder import latest_completed_run
    from app.services.location_forecast import location_bands
    from app.services.planning_inputs import FORECAST_MAX_AGE_DAYS, is_run_fresh

    now = datetime.now(UTC)
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        if run_id is not None:
            mode = ForecastRun.metrics["mode"].astext
            run = await session.scalar(select(ForecastRun).where(
                ForecastRun.id == run_id,
                ForecastRun.tenant_id == tenant_id,
                ForecastRun.industry == IndustryCode(ctx.code),
                ForecastRun.status == "completed",
                or_(mode.is_(None), mode != "backtest"),
            ))
            if run is None:
                raise HTTPException(status_code=404, detail="Forecast run not found")
        else:
            run = await latest_completed_run(session, tenant_id, IndustryCode(ctx.code))
        if run is None or (run_id is None and not is_run_fresh(run, now)):
            return {"run_id": None, "degraded": False, "unassigned_share": None, "locations": [],
                    "reason": f"No forecast from the last {FORECAST_MAX_AGE_DAYS} days"}
        bands = await location_bands(session, tenant_id, run.id, now,
                                     sku_id=sku_id, include_past=run_id is not None)
        locs = {l.id: l for l in await load_locations(session, tenant_id)}
    metrics = run.metrics or {}
    rows = [
        {"location_id": str(loc_id), "code": locs[loc_id].code, "name": locs[loc_id].name,
         "p10": b.p10, "p50": b.p50, "p90": b.p90,
         "forecast_dates": [d.isoformat() for d in b.forecast_dates]}
        for (sid, loc_id), b in bands.items() if sid == sku_id and loc_id in locs
    ]
    return {"run_id": str(run.id), "degraded": bool(metrics.get("location_degraded")),
            "unassigned_share": metrics.get("unassigned_share"),
            "locations": sorted(rows, key=lambda r: r["code"]),
            "reason": None if rows else "No location forecast for this SKU"}


@router.patch("/{location_id}")
async def update_location(
    request: Request,
    tenant_id: TenantId,
    location_id: uuid.UUID,
    body: LocationPatch,
    _rbac: Annotated[None, require_admin],
) -> dict[str, Any]:
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        locs = {l.id: l for l in await load_locations(session, tenant_id)}
        loc = locs.get(location_id)
        if loc is None:
            raise HTTPException(status_code=404, detail="Location not found")
        changes = body.model_dump(exclude_unset=True)
        if "parent_location_id" in changes and changes["parent_location_id"] is not None:
            parent = locs.get(changes["parent_location_id"])
            if parent is None or parent.kind != LocationKind.warehouse or parent.id == loc.id:
                raise HTTPException(status_code=422,
                                    detail="Parent must be a warehouse of this workspace")
        for key, value in changes.items():
            setattr(loc, key, value)
        if loc.kind == LocationKind.warehouse:
            loc.parent_location_id = None
            loc.lead_time_days_from_parent = None
        await session.flush()
        out = _out(loc)
        network = _network(list(locs.values()))
    return {"location": out, "network": network}
