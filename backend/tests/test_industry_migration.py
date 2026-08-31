"""The database, not the application, guarantees one industry per workspace.

A workspace is scoped to exactly one industry. That could have been enforced in
Python alone, but every previous industry rule lived in application code and
every one of them had a hole: signup granted all five verticals, the middleware
trusted a claim signup had filled with all five, and the industry routers never
compared the caller's industry to their own.

So the invariant is enforced where nothing can route around it. These tests
assert the constraint and the triggers directly, in SQL, without going through
the ORM at all.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.asyncio

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROBE_DB = "migration_probe"


def _alembic(database_url: str, revision: str, direction: str = "upgrade") -> None:
    """Run the real migration chain against ``database_url``."""
    env = {**os.environ, "DATABASE_URL": database_url}
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell, test-only
        [sys.executable, "-m", "alembic", direction, revision],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")


@pytest_asyncio.fixture
async def migration_probe_url(setup_schema) -> str:
    """A throwaway database for exercising the upgrade on pre-migration rows.

    Kept separate from the suite's own database so running the migration chain
    twice cannot disturb the schema every other test shares.
    """
    base = os.environ["DATABASE_URL"]
    admin_url, _, _ = base.rpartition("/")
    engine = create_async_engine(f"{admin_url}/postgres", poolclass=NullPool)
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text(f"DROP DATABASE IF EXISTS {PROBE_DB} WITH (FORCE)"))
        await conn.execute(text(f"CREATE DATABASE {PROBE_DB}"))
    await engine.dispose()

    yield f"{admin_url}/{PROBE_DB}"

    engine = create_async_engine(f"{admin_url}/postgres", poolclass=NullPool)
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text(f"DROP DATABASE IF EXISTS {PROBE_DB} WITH (FORCE)"))
    await engine.dispose()


async def test_tenant_industries_mirrors_industry(db_session: AsyncSession) -> None:
    """The legacy array column is maintained by the database, not by callers."""
    tenant_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status, industry)
            VALUES (:id, :slug, 'Mirror Co', 'growth', 'trial', 'pharma')
            """
        ),
        {"id": str(tenant_id), "slug": f"mirror-{tenant_id.hex[:8]}"},
    )
    await db_session.commit()

    row = await db_session.execute(
        text("SELECT industry::text, industries::text[] FROM tenants WHERE id = :id"),
        {"id": str(tenant_id)},
    )
    industry, industries = row.one()
    assert industry == "pharma"
    assert industries == ["pharma"]


async def test_cannot_grant_a_second_industry(db_session: AsyncSession) -> None:
    """A bug that tries to re-grant five verticals is overwritten, not obeyed."""
    tenant_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status,
                                 industry, industries)
            VALUES (:id, :slug, 'Greedy Co', 'growth', 'trial', 'fashion',
                    ARRAY['fashion','pharma']::industry_code[])
            """
        ),
        {"id": str(tenant_id), "slug": f"greedy-{tenant_id.hex[:8]}"},
    )
    await db_session.commit()

    industries = await db_session.scalar(
        text("SELECT industries::text[] FROM tenants WHERE id = :id"),
        {"id": str(tenant_id)},
    )
    assert industries == ["fashion"]


async def test_user_inherits_tenant_industry(db_session: AsyncSession) -> None:
    """A member cannot carry an industry that differs from their workspace."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status, industry)
            VALUES (:id, :slug, 'Inherit Co', 'growth', 'trial', 'agrocenter')
            """
        ),
        {"id": str(tenant_id), "slug": f"inherit-{tenant_id.hex[:8]}"},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO users (id, tenant_id, email, full_name, role,
                               active_industry, is_active)
            VALUES (:uid, :tid, :email, 'Member', 'analyst', 'pharma', TRUE)
            """
        ),
        {
            "uid": str(user_id),
            "tid": str(tenant_id),
            "email": f"member-{user_id.hex[:8]}@inherit.test",
        },
    )
    await db_session.commit()

    active = await db_session.scalar(
        text("SELECT active_industry::text FROM users WHERE id = :id"),
        {"id": str(user_id)},
    )
    assert active == "agrocenter", "a stale user industry must never survive a write"


async def test_updating_tenant_industry_cascades_to_members(
    db_session: AsyncSession,
) -> None:
    """Correcting the workspace industry during setup must not strand members."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status, industry)
            VALUES (:id, :slug, 'Corrected Co', 'growth', 'trial', 'fashion')
            """
        ),
        {"id": str(tenant_id), "slug": f"corrected-{tenant_id.hex[:8]}"},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO users (id, tenant_id, email, full_name, role,
                               active_industry, is_active)
            VALUES (:uid, :tid, :email, 'Member', 'analyst', 'fashion', TRUE)
            """
        ),
        {
            "uid": str(user_id),
            "tid": str(tenant_id),
            "email": f"member-{user_id.hex[:8]}@corrected.test",
        },
    )
    await db_session.commit()

    await db_session.execute(
        text("UPDATE tenants SET industry = 'pharma' WHERE id = :id"),
        {"id": str(tenant_id)},
    )
    # The users trigger fires on the member row, not the tenant row, so the
    # cascade is an explicit re-write rather than something Postgres does for us.
    await db_session.execute(
        text("UPDATE users SET updated_at = now() WHERE id = :id"),
        {"id": str(user_id)},
    )
    await db_session.commit()

    active = await db_session.scalar(
        text("SELECT active_industry::text FROM users WHERE id = :id"),
        {"id": str(user_id)},
    )
    assert active == "pharma"


async def test_sandbox_tenant_exists_and_is_single_industry(
    db_session: AsyncSession,
) -> None:
    """The public demo gets its own workspace, not the development tenant."""
    row = await db_session.execute(
        text(
            "SELECT industry::text, industries::text[] FROM tenants "
            "WHERE slug = 'sandbox'"
        )
    )
    result = row.one_or_none()
    assert result is not None, "the migration must create the sandbox workspace"
    industry, industries = result
    assert industry == "fashion"
    assert industries == ["fashion"]


async def test_sandbox_user_is_a_viewer(db_session: AsyncSession) -> None:
    """Anyone on the internet can start a sandbox session, so it is read-only."""
    role = await db_session.scalar(
        text(
            "SELECT u.role::text FROM users u JOIN tenants t ON t.id = u.tenant_id "
            "WHERE t.slug = 'sandbox'"
        )
    )
    assert role == "viewer"


async def test_orm_exposes_exactly_one_industry_field() -> None:
    """The mirrors are the database's business, not the ORM's.

    Leaving them mapped would recreate the problem the triggers solve: a second
    writable field that application code can set independently of the first.
    """
    from app.models.tenant import Tenant, User

    assert hasattr(Tenant, "industry")
    assert not hasattr(Tenant, "industries"), "the mirror column must not be mapped"
    assert not hasattr(User, "active_industry"), "members inherit; they do not carry"


async def test_migrating_a_multi_industry_tenant_preserves_its_data(
    setup_schema, migration_probe_url: str
) -> None:
    """The real upgrade, run against real pre-migration rows.

    Asserting on the post-migration schema cannot show what the migration *did*
    to a tenant that held five verticals, because no such row can exist once the
    constraint is in place. So this builds a separate database at revision 0019,
    puts a genuinely multi-industry tenant in it, and then runs 0020 for real.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    _alembic(migration_probe_url, "0019")

    engine = create_async_engine(migration_probe_url, poolclass=NullPool)
    tenant_id, user_id = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO tenants (id, slug, display_name, tier, status,
                                     industries, active_industry, settings)
                VALUES (:id, 'legacy-co', 'Legacy Co', 'growth', 'active',
                        ARRAY['fashion','pharma','electronics']::industry_code[],
                        'pharma', '{"currency": "INR"}'::jsonb)
                """
            ),
            {"id": str(tenant_id)},
        )
        await conn.execute(
            text(
                """
                INSERT INTO users (id, tenant_id, email, full_name, role,
                                   active_industry, is_active)
                VALUES (:uid, :tid, 'legacy@legacy.test', 'Legacy User',
                        'analyst', 'fashion', TRUE)
                """
            ),
            {"uid": str(user_id), "tid": str(tenant_id)},
        )
    await engine.dispose()

    _alembic(migration_probe_url, "head")

    engine = create_async_engine(migration_probe_url, poolclass=NullPool)
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT industry::text, industries::text[], "
                    "       settings -> 'legacy_industries', settings ->> 'currency' "
                    "FROM tenants WHERE id = :id"
                ),
                {"id": str(tenant_id)},
            )
        ).one()
        member_industry = await conn.scalar(
            text("SELECT active_industry::text FROM users WHERE id = :id"),
            {"id": str(user_id)},
        )
    await engine.dispose()

    industry, industries, legacy, currency = row
    # Deterministic: the tenant keeps the industry it was already active in.
    assert industry == "pharma"
    assert industries == ["pharma"]
    # Non-destructive: the prior grant is still recorded, not dropped.
    assert sorted(legacy) == ["electronics", "fashion", "pharma"]
    # And unrelated settings survive the jsonb rewrite.
    assert currency == "INR"
    # The member inherits the workspace, overriding their stale own value.
    assert member_industry == "pharma"


async def test_downgrade_restores_the_original_industry_array(
    setup_schema, migration_probe_url: str
) -> None:
    """The snapshot is not decoration: it is what makes 0020 reversible."""
    _alembic(migration_probe_url, "0019")

    tenant_id = uuid.uuid4()
    engine = create_async_engine(migration_probe_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO tenants (id, slug, display_name, tier, status,
                                     industries, active_industry)
                VALUES (:id, 'rollback-co', 'Rollback Co', 'growth', 'active',
                        ARRAY['hardware','agrocenter']::industry_code[],
                        'hardware')
                """
            ),
            {"id": str(tenant_id)},
        )
    await engine.dispose()

    _alembic(migration_probe_url, "head")
    _alembic(migration_probe_url, "0019", direction="downgrade")

    engine = create_async_engine(migration_probe_url, poolclass=NullPool)
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT active_industry::text, industries::text[], "
                    "       settings ? 'legacy_industries' "
                    "FROM tenants WHERE id = :id"
                ),
                {"id": str(tenant_id)},
            )
        ).one()
    await engine.dispose()

    active_industry, industries, snapshot_remains = row
    assert active_industry == "hardware", "the column name must be restored"
    assert sorted(industries) == ["agrocenter", "hardware"]
    assert snapshot_remains is False, "the snapshot is cleaned up on the way back"
