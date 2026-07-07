"""Inventory service — reads real warehouse stock and resolves the on-hand
figure the insight layer should use.

`resolve_on_hand` centralizes the precedence rule (kept pure so it is unit
testable without a database):

    request override  >  real inventory_levels  >  fallback (safety_stock × 2)

The fallback exists only so the system degrades gracefully for tenants that
have not yet ingested any stock data; it is reported as such so callers/UX can
flag that an insight is running on an estimate rather than real stock.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import IndustryCode
from app.models.inventory import InventoryLevel

OnHandSource = Literal["override", "inventory", "fallback"]


@dataclass(frozen=True, slots=True)
class InventorySnapshot:
    sku_id: str
    on_hand_units: float
    inbound_units: float
    reserved_units: float

    @property
    def available_units(self) -> float:
        avail = self.on_hand_units - self.reserved_units
        return avail if avail > 0 else 0.0


def resolve_on_hand(
    *,
    override_units: float | None,
    snapshot: InventorySnapshot | None,
    safety_stock_units: float,
) -> tuple[float, OnHandSource]:
    """Resolve the on-hand quantity to feed the insight layer.

    Returns ``(units, source)``. ``override_units`` wins when supplied (an
    explicit caller-provided position), then real recorded inventory (the
    *available* quantity = on_hand − reserved), then a clearly-labeled estimate.
    """
    if override_units is not None:
        return float(override_units), "override"
    if snapshot is not None:
        return float(snapshot.available_units), "inventory"
    return float(max(0.0, safety_stock_units) * 2.0), "fallback"


async def current_levels(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    industry: str,
    sku_ids: Iterable[uuid.UUID] | None = None,
    location: str | None = None,
) -> dict[str, InventorySnapshot]:
    """Return current stock snapshots keyed by ``str(sku_id)`` for a tenant.

    When a SKU has rows across multiple locations the quantities are summed into
    a single portfolio-wide position (no location filter), or restricted to one
    location when ``location`` is given.
    """
    stmt = select(InventoryLevel).where(
        InventoryLevel.tenant_id == tenant_id,
        InventoryLevel.industry == IndustryCode(industry),
    )
    if sku_ids is not None:
        ids = list(sku_ids)
        if not ids:
            return {}
        stmt = stmt.where(InventoryLevel.sku_id.in_(ids))
    if location is not None:
        stmt = stmt.where(InventoryLevel.location == location)

    rows = (await session.execute(stmt)).scalars().all()

    agg: dict[str, list[float]] = {}
    for r in rows:
        key = str(r.sku_id)
        on_hand = float(r.on_hand_units or 0)
        inbound = float(r.inbound_units or 0)
        reserved = float(r.reserved_units or 0)
        if key in agg:
            agg[key][0] += on_hand
            agg[key][1] += inbound
            agg[key][2] += reserved
        else:
            agg[key] = [on_hand, inbound, reserved]

    return {
        k: InventorySnapshot(sku_id=k, on_hand_units=v[0], inbound_units=v[1], reserved_units=v[2])
        for k, v in agg.items()
    }
