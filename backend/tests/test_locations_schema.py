"""locations: tenant-isolated, unique per (tenant, code), kind constrained (spec §3.1)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


async def _insert(db, tenant, code, kind="unconfirmed"):
    await db.execute(
        text("INSERT INTO locations (tenant_id, code, name, kind) VALUES (:t, :c, :c, :k)"),
        {"t": str(tenant), "c": code, "k": kind},
    )


async def test_code_unique_per_tenant(db_session, make_tenant):
    t = await make_tenant()
    await _insert(db_session, t, "alwal")
    with pytest.raises(IntegrityError):
        await _insert(db_session, t, "alwal")


async def test_kind_is_constrained(db_session, make_tenant):
    t = await make_tenant()
    with pytest.raises(IntegrityError):
        await _insert(db_session, t, "x", kind="depot")


async def test_locations_are_tenant_isolated(db_session, app_role_db, make_tenant):
    a, b = await make_tenant(), await make_tenant()
    await _insert(db_session, a, "alwal")
    await _insert(db_session, b, "boduppal")
    await db_session.commit()
    async with app_role_db.session(str(a)) as s:
        codes = (await s.execute(text("SELECT code FROM locations"))).scalars().all()
    assert codes == ["alwal"]
