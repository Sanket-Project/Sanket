"""Location identity, registration from imported data, and network readiness.

Imports never create locations themselves: any code seen on sales (last 365
days) or stock is registered here as ``unconfirmed``. Nothing is inferred from a
name — "Central DC" is not assumed to be a warehouse.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import LocationKind
from app.models.location import Location

UNASSIGNED_CODES = frozenset({"", "default"})


def normalize_code(raw: str | None) -> str | None:
    """``lower(trim(raw))``, or None when the value means "no location"."""
    if raw is None:
        return None
    code = raw.strip(" ").lower()
    return None if code in UNASSIGNED_CODES else code


_SYNC_SQL = text(
    """
    INSERT INTO locations (tenant_id, code, name, kind)
    SELECT :t, code, min(raw), 'unconfirmed'
      FROM (
        SELECT lower(btrim(location)) AS code, btrim(location) AS raw
          FROM inventory_levels WHERE tenant_id = :t AND location IS NOT NULL
        UNION ALL
        SELECT lower(btrim(location)), btrim(location)
          FROM historical_sales
         WHERE tenant_id = :t AND location IS NOT NULL
           AND sale_time >= now() - interval '365 days'
      ) seen
     WHERE code NOT IN ('', 'default')
     GROUP BY code
    ON CONFLICT (tenant_id, code) DO NOTHING
    """
)


async def sync_locations(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    result = await session.execute(_SYNC_SQL, {"t": str(tenant_id)})
    return int(result.rowcount or 0)


async def load_locations(session: AsyncSession, tenant_id: uuid.UUID) -> list[Location]:
    rows = await session.execute(
        select(Location).where(Location.tenant_id == tenant_id).order_by(Location.code)
    )
    return list(rows.scalars().all())


@dataclass(frozen=True)
class NetworkReadiness:
    allocation_ready: bool
    transfers_ready: bool
    missing: list[str] = field(default_factory=list)


def network_readiness(locations: list[Location]) -> NetworkReadiness:
    active = [l for l in locations if l.is_active]
    missing: list[str] = []
    for l in active:
        if l.kind == LocationKind.unconfirmed:
            missing.append(f"Location '{l.code}' kind is not confirmed")
    warehouses = {l.id for l in active if l.kind == LocationKind.warehouse}
    stores = [l for l in active if l.kind == LocationKind.store]
    if not warehouses:
        missing.append("No warehouse is defined")
    for s in stores:
        if s.parent_location_id is None or s.parent_location_id not in warehouses:
            missing.append(f"Store '{s.code}' has no supplying warehouse")
        if s.lead_time_days_from_parent is None:
            missing.append(f"Store '{s.code}' has no lead time from its warehouse")
    unconfirmed = any(l.kind == LocationKind.unconfirmed for l in active)
    allocation_ready = not missing and bool(stores)
    transfers_ready = not unconfirmed and len(stores) >= 2
    return NetworkReadiness(allocation_ready, transfers_ready, missing)
