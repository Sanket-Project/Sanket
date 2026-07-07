"""Adversarial multi-tenant isolation tests.

These are the most important security tests in the suite: they assert that the
row-level-security model actually isolates tenants when queried through the
non-privileged ``sanket_app`` role the application uses in production.

They would FAIL if:
  * the app connected as a superuser / BYPASSRLS role,
  * a tenant table were missing ``FORCE ROW LEVEL SECURITY`` (owner bypass), or
  * a tenant table shipped with no isolation policy at all.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


async def _enter_tenant(conn, tenant_id) -> None:
    """Within the current transaction, drop to the sanket_app role and scope to
    a tenant — i.e. reproduce exactly what the application does per request."""
    await conn.execute(text("SET LOCAL ROLE sanket_app"))
    await conn.execute(
        text("SELECT set_config('app.current_tenant_id', :t, true)"),
        {"t": str(tenant_id)},
    )


async def _seed_tenant(conn, slug: str) -> uuid.UUID:
    tid = uuid.uuid4()
    # Insert each tenant's own rows under that tenant's RLS context (SET LOCAL
    # ROLE sanket_app + tenant GUC), so the WITH CHECK clauses are exercised.
    await _enter_tenant(conn, tid)
    await conn.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status,
                                 industries, active_industry)
            VALUES (:id, :slug, :name, 'enterprise', 'active',
                    ARRAY['fashion']::industry_code[], 'fashion')
            """
        ),
        {"id": str(tid), "slug": slug, "name": slug},
    )
    await conn.execute(
        text(
            """
            INSERT INTO products (id, tenant_id, industry, external_id, name,
                                  category, status, attributes)
            VALUES (:id, :tid, 'fashion', :ext, :name, 'Test', 'active', '{}'::jsonb)
            """
        ),
        {"id": str(uuid.uuid4()), "tid": str(tid), "ext": f"{slug}-P1", "name": f"{slug} product"},
    )
    return tid


@pytest.mark.asyncio
async def test_products_are_tenant_isolated(rls_engine):
    """A tenant context can never see another tenant's products."""
    suffix = uuid.uuid4().hex[:8]
    async with rls_engine.begin() as conn:
        tenant_a = await _seed_tenant(conn, f"rls-a-{suffix}")
        tenant_b = await _seed_tenant(conn, f"rls-b-{suffix}")

    # Tenant A sees only its own product.
    async with rls_engine.begin() as conn:
        await _enter_tenant(conn, tenant_a)
        rows = (await conn.execute(text("SELECT tenant_id FROM products"))).fetchall()
    assert rows, "tenant A should see its own product"
    assert all(str(r[0]) == str(tenant_a) for r in rows), "tenant A leaked another tenant's rows"

    # Tenant B sees only its own product — never tenant A's.
    async with rls_engine.begin() as conn:
        await _enter_tenant(conn, tenant_b)
        rows = (await conn.execute(text("SELECT tenant_id FROM products"))).fetchall()
    assert all(str(r[0]) == str(tenant_b) for r in rows), "tenant B leaked another tenant's rows"


@pytest.mark.asyncio
async def test_cannot_write_into_another_tenant(rls_engine):
    """WITH CHECK / USING must reject inserting a row for a different tenant."""
    suffix = uuid.uuid4().hex[:8]
    async with rls_engine.begin() as conn:
        tenant_a = await _seed_tenant(conn, f"rls-w-{suffix}")

    other_tenant = uuid.uuid4()

    async def _attempt_cross_tenant_write() -> None:
        async with rls_engine.begin() as conn:
            await _enter_tenant(conn, tenant_a)
            # Insert a product owned by a DIFFERENT tenant while the session is
            # scoped to tenant_a — the WITH CHECK clause must reject it.
            await conn.execute(
                text(
                    """
                    INSERT INTO products (id, tenant_id, industry, external_id, name,
                                          category, status, attributes)
                    VALUES (:id, :other, 'fashion', 'evil-P1', 'evil', 'Test', 'active',
                            '{}'::jsonb)
                    """
                ),
                {"id": str(uuid.uuid4()), "other": str(other_tenant)},
            )

    with pytest.raises(DBAPIError):
        await _attempt_cross_tenant_write()


@pytest.mark.asyncio
async def test_startup_guard_rejects_privileged_role(setup_schema):
    """The production startup guard must refuse a role that can bypass RLS.

    The test container connects as a superuser — exactly the dangerous
    production misconfiguration (e.g. DATABASE_URL pointed at a managed
    provider's `postgres` admin role). strict=True must raise; strict=False
    must only warn.
    """
    import os

    from app.config import Settings
    from app.core.database import Database

    db = Database(Settings(database_url=os.environ["DATABASE_URL"]))
    try:
        with pytest.raises(RuntimeError, match="tenant isolation is NOT enforced"):
            await db.assert_tenant_isolation_enforced(strict=True)
        # Non-strict path must not raise (dev warning only).
        await db.assert_tenant_isolation_enforced(strict=False)
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_force_rls_enabled_on_all_tenant_tables(rls_engine):
    """Every RLS-enabled table must also have FORCE ROW LEVEL SECURITY.

    Without FORCE, a connection role that owns the table bypasses every policy —
    which is exactly how tenant isolation was silently defeated before.
    """
    async with rls_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    """
                    SELECT c.relname
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public'
                      AND c.relkind = 'r'
                      AND c.relrowsecurity = true
                      AND c.relforcerowsecurity = false
                    """
                )
            )
        ).fetchall()
    missing = [r[0] for r in rows]
    assert not missing, f"tables have RLS but not FORCE RLS (owner can bypass): {missing}"
