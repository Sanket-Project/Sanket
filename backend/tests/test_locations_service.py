"""Locations are registered from data as unconfirmed; readiness lists what is missing (spec §3.2–§3.3)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.models.enums import LocationKind
from app.models.location import Location
from app.services.locations import load_locations, network_readiness, normalize_code, sync_locations


def test_normalize_code():
    assert normalize_code("  Alwal ") == "alwal"
    assert normalize_code("DEFAULT") is None
    assert normalize_code("") is None
    assert normalize_code(None) is None


async def _sku(db, tenant):
    pid, sid = uuid.uuid4(), uuid.uuid4()
    await db.execute(text("INSERT INTO products (id, tenant_id, industry, name, category, status) "
                          "VALUES (:p, :t, 'fashion', 'K', 'Kurtis', 'active')"),
                     {"p": str(pid), "t": str(tenant)})
    await db.execute(text("INSERT INTO skus (id, tenant_id, product_id, industry, sku_code) "
                          "VALUES (:s, :t, :p, 'fashion', 'K-M')"),
                     {"s": str(sid), "t": str(tenant), "p": str(pid)})
    return sid


async def test_sync_registers_sales_and_stock_locations_once(db_session, app_role_db, make_tenant):
    t = await make_tenant()
    sku = await _sku(db_session, t)
    for loc in ("Alwal", " alwal", None, "default"):
        await db_session.execute(
            text("INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, channel, "
                 "units_sold, location) VALUES (:t, :s, 'fashion', :w, 'store', 1, :l)"),
            {"t": str(t), "s": str(sku), "l": loc, "w": datetime(2026, 10, 5, tzinfo=UTC)},
        )
    await db_session.execute(
        text("INSERT INTO inventory_levels (tenant_id, sku_id, industry, location, on_hand_units) "
             "VALUES (:t, :s, 'fashion', 'Central DC', 10)"),
        {"t": str(t), "s": str(sku)},
    )
    await db_session.commit()

    async with app_role_db.session(str(t)) as s:
        created = await sync_locations(s, t)
        again = await sync_locations(s, t)
        locs = await load_locations(s, t)

    assert created == 2 and again == 0
    assert sorted(l.code for l in locs) == ["alwal", "central dc"]
    assert all(l.kind == LocationKind.unconfirmed for l in locs)


def _loc(code, kind, parent=None, lead=None):
    return Location(id=uuid.uuid4(), tenant_id=uuid.uuid4(), code=code, name=code,
                    kind=kind, parent_location_id=parent, lead_time_days_from_parent=lead,
                    is_active=True, attributes={})


def test_readiness_requires_dc_parent_and_lead_time():
    dc = _loc("dc", LocationKind.warehouse)
    a = _loc("a", LocationKind.store, parent=dc.id, lead=3)
    b = _loc("b", LocationKind.store)
    r = network_readiness([dc, a, b])
    assert r.allocation_ready is False
    assert r.transfers_ready is True
    assert "Store 'b' has no supplying warehouse" in r.missing
    assert "Store 'b' has no lead time from its warehouse" in r.missing


def test_readiness_unconfirmed_blocks_everything():
    r = network_readiness([_loc("x", LocationKind.unconfirmed)])
    assert (r.allocation_ready, r.transfers_ready) == (False, False)
    assert "Location 'x' kind is not confirmed" in r.missing
    assert "No warehouse is defined" in r.missing
