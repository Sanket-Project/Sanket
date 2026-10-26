"""Store / warehouse network: list (registering any newly seen codes) and edit."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.rbac import require_admin
from app.models.enums import LocationKind
from app.models.location import Location
from app.routers.industry_router import TenantId
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
async def list_locations(request: Request, tenant_id: TenantId) -> dict[str, Any]:
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        await sync_locations(session, tenant_id)
        locs = await load_locations(session, tenant_id)
    return {"locations": [_out(l) for l in locs], "network": _network(locs)}


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
