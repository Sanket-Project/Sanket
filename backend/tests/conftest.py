"""Shared pytest fixtures.

We spin up a real PostgreSQL via testcontainers and build the schema with the
**real migration chain** (``alembic upgrade head``) — the exact DDL production
runs — rather than hand-listing a subset of SQL files. This guarantees tests
exercise the same schema (and the same FORCE-RLS tenant isolation) that ships.

Fixtures yield a clean async session, an httpx AsyncClient bound to the FastAPI
app, and ``rls_session`` — a session connected as the non-privileged
``sanket_app`` role so row-level-security policies actually apply (a superuser
connection bypasses RLS, so isolation must be asserted as ``sanket_app``).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
SQL_DIR = BACKEND_DIR / "sql"

# The app lifespan starts background loops that call third-party services
# (Google Trends, Reddit, FRED, Shopify, WhatsApp). A test run must never do
# that: a real 429 from Google opened the shared Trends cooldown mid-suite and
# made test_regional_demand_connector_fetch fail only in full runs. Set before
# any test imports the app, so the cached Settings never see the live defaults.
os.environ["SIGNAL_PIPELINE_ENABLED"] = "false"
os.environ["SHOPIFY_POLL_ENABLED"] = "false"
os.environ["WHATSAPP_DIGEST_WORKER_ENABLED"] = "false"
# Never let a test reach a real ML service: a developer's (or an audit's)
# inference API on the default 127.0.0.1:8001 writes into its own database.
# Port 9 (discard) refuses connections, so any un-mocked call fails loudly.
os.environ["ML_API_URL"] = "http://127.0.0.1:9"
# Same for Redis: backend/.env points at a developer Redis on :6379. Tests ran
# against "Redis unreachable" anyway (plus ~11 s of arq retries per lifespan);
# empty means in-process only, and a live developer Redis is never written to.
os.environ["REDIS_URL"] = ""


@pytest.fixture(scope="session", autouse=True)
def mock_env():
    """Ensure Firebase is disabled for all test runs to prevent test pollution."""
    os.environ["FIREBASE_PROJECT_ID"] = ""
    os.environ["FIREBASE_CREDENTIALS_PATH"] = ""
    os.environ["FIREBASE_WEB_API_KEY"] = ""


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def postgres_container():
    """Start a real PostgreSQL with pgvector for the test session."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer(image="pgvector/pgvector:pg16", driver="asyncpg").with_env(
        "POSTGRES_DB", "sanket_test"
    ) as pg:
        os.environ["DATABASE_URL"] = pg.get_connection_url().replace(
            "postgresql+asyncpg://", "postgresql+asyncpg://"
        )
        os.environ["JWT_SECRET"] = "test-secret-min-32-chars-please-rotate-1234"
        yield pg


@pytest_asyncio.fixture(scope="session")
async def setup_schema(postgres_container) -> None:
    """Build the full schema via the real migration chain (``alembic upgrade head``).

    Running Alembic — instead of hand-applying a subset of SQL files — means the
    test database is byte-for-byte the production schema: every table, every RLS
    policy, and the FORCE-ROW-LEVEL-SECURITY hardening from migration 0011. We
    shell out so Alembic's own asyncio.run() doesn't collide with the test event
    loop.
    """
    env = dict(os.environ)
    env["DATABASE_URL"] = os.environ["DATABASE_URL"]
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )


# NOTE on testing RLS as sanket_app:
# RLS policies are enforced for the *current role* only when it is neither a
# superuser nor a BYPASSRLS role. The test container connects as a superuser, so
# the isolation tests use `SET ROLE sanket_app` (see the `as_sanket_app` helper)
# rather than a separate password-authenticated connection — a superuser that
# SET ROLEs to sanket_app becomes subject to every policy, exactly as the
# application is in production, with no dependency on the role's password.


@pytest_asyncio.fixture
async def db_session(setup_schema) -> AsyncIterator[AsyncSession]:
    from app.config import get_settings
    from app.core.database import Database

    get_settings.cache_clear()
    db = Database(get_settings())
    async with db._sessionmaker() as session:
        yield session
    await db.close()


async def grant_active_subscription(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Give a tenant a live subscription so entitlement does not 402 its requests.

    Every tenant-data router is gated on ``require_active_subscription``
    (``app/core/entitlement.py``). Tests that exercise something else — RBAC,
    connectors, webhook delivery — still have to get past the paywall, exactly
    as a real customer does. Call this from any fixture that seeds a tenant and
    then drives a gated endpoint.

    Deliberately a helper rather than something baked into the ``client``
    fixture: entitlement should be granted where a test means to grant it, so
    that a test which forgets is a visible 402 and not a silent bypass.
    """
    existing = await db.execute(
        text(
            "SELECT 1 FROM subscriptions "
            "WHERE tenant_id = :tid AND status IN ('active','trialing') "
            "AND current_period_end > now()"
        ),
        {"tid": str(tenant_id)},
    )
    if existing.fetchone():
        return

    await db.execute(
        text(
            """
            INSERT INTO subscriptions (id, tenant_id, plan_id, status,
                                       current_period_start, current_period_end,
                                       cancel_at_period_end, metadata)
            VALUES (:id, :tid, 'enterprise_monthly', 'active',
                    now() - interval '1 day', now() + interval '365 days',
                    FALSE, '{}'::jsonb)
            """
        ),
        {"id": str(uuid.uuid4()), "tid": str(tenant_id)},
    )
    await db.commit()


@pytest_asyncio.fixture
async def test_tenant_id(db_session: AsyncSession) -> uuid.UUID:
    # Avoid duplicate key value unique violation by checking if tenant already exists
    result = await db_session.execute(text("SELECT id FROM tenants WHERE slug = 'test-tenant'"))
    row = result.fetchone()
    if row:
        await grant_active_subscription(db_session, row[0])
        return row[0]

    tenant_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO industries (code, display_name, default_horizon_weeks, audit_level)
            VALUES ('fashion', 'Fashion', 26, 'standard'),
                   ('electronics', 'Electronics', 12, 'standard'),
                   ('pharma', 'Pharmaceuticals', 52, 'gxp')
            ON CONFLICT DO NOTHING
            """
        )
    )
    await db_session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status, industry)
            VALUES (:id, 'test-tenant', 'Test Tenant', 'enterprise', 'active',
                    'fashion')
            """
        ),
        {"id": str(tenant_id)},
    )
    await db_session.commit()
    await grant_active_subscription(db_session, tenant_id)
    return tenant_id


@pytest_asyncio.fixture
async def pharma_tenant_id(db_session: AsyncSession) -> uuid.UUID:
    """A second workspace, scoped to pharma.

    Industry-boundary assertions need a tenant on the *other* side of the line:
    without one, "fashion cannot reach pharma" can only be tested by pointing a
    fashion tenant at a pharma URL, which says nothing about what a real pharma
    workspace sees.
    """
    result = await db_session.execute(
        text("SELECT id FROM tenants WHERE slug = 'pharma-tenant'")
    )
    row = result.fetchone()
    if row:
        await grant_active_subscription(db_session, row[0])
        return row[0]

    tenant_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status, industry)
            VALUES (:id, 'pharma-tenant', 'Pharma Tenant', 'enterprise',
                    'active', 'pharma')
            """
        ),
        {"id": str(tenant_id)},
    )
    await db_session.commit()
    await grant_active_subscription(db_session, tenant_id)
    return tenant_id


@pytest_asyncio.fixture
async def client(setup_schema, monkeypatch) -> AsyncIterator[AsyncClient]:
    from app.main import create_app
    from app.config import get_settings

    # Legacy provisioning/industry tests explicitly exercise optional public
    # flows. Runtime defaults remain private and are tested independently.
    monkeypatch.setenv("PUBLIC_SIGNUP_ENABLED", "true")
    monkeypatch.setenv("SANDBOX_ENABLED", "true")
    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Trigger lifespan
        async with app.router.lifespan_context(app):
            yield ac
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def app_role_db(setup_schema):
    """A ``Database`` connected as ``sanket_app`` — the production app role.

    ``db_session``/``client`` connect as the container superuser, which
    bypasses RLS. Services that must be shown to respect tenant isolation run
    through this instead, so every query is subject to the real policies.
    """
    from sqlalchemy.engine import make_url

    from app.config import get_settings
    from app.core.database import Database

    get_settings.cache_clear()
    # The disposable test container's app role (created by sql/003_rls_policies.sql).
    url = make_url(os.environ["DATABASE_URL"]).set(
        username="sanket_app", password="changeme"  # noqa: S106
    )
    settings = get_settings().model_copy(
        update={"database_url": url.render_as_string(hide_password=False)}
    )
    db = Database(settings)
    try:
        yield db
    finally:
        await db.close()


@pytest_asyncio.fixture
async def make_tenant(db_session: AsyncSession):
    """Factory for disposable, clearly synthetic workspaces (fixture setup only)."""

    async def _make(industry: str = "fashion") -> uuid.UUID:
        tenant_id = uuid.uuid4()
        slug = f"synthetic-{tenant_id.hex[:10]}"
        await db_session.execute(
            text(
                "INSERT INTO tenants (id, slug, display_name, tier, status, industry) "
                "VALUES (:id, :slug, :name, 'growth', 'active', CAST(:ind AS industry_code))"
            ),
            {"id": str(tenant_id), "slug": slug, "name": f"Synthetic test {slug}", "ind": industry},
        )
        await db_session.commit()
        return tenant_id

    return _make


@pytest_asyncio.fixture
async def signed_in_workspace(client, db_session, make_tenant):
    """Factory: a fresh subscribed workspace plus an admin's auth headers.

    For API tests that need their own data (duplicates, forecasts, stock)
    without leaking into the shared ``test-tenant``.
    """
    from app.config import get_settings
    from app.core.security import hash_password

    async def _make(industry: str = "fashion") -> tuple[uuid.UUID, dict[str, str]]:
        tenant_id = await make_tenant(industry)
        await grant_active_subscription(db_session, tenant_id)
        slug = await db_session.scalar(
            text("SELECT slug FROM tenants WHERE id = :t"), {"t": str(tenant_id)}
        )
        email = f"admin-{tenant_id.hex[:10]}@test.com"
        await db_session.execute(
            text(
                "INSERT INTO users (id, tenant_id, email, password_hash, full_name, role, "
                "active_industry, is_active) VALUES (:id, :t, :e, :h, 'Synthetic admin', 'admin', "
                "CAST(:ind AS industry_code), TRUE)"
            ),
            {
                "id": str(uuid.uuid4()),
                "t": str(tenant_id),
                "e": email,
                "h": hash_password("GoodPass123!", get_settings()),
                "ind": industry,
            },
        )
        await db_session.commit()
        r = await client.post(
            "/api/v1/auth/dev-login",
            json={"email": email, "password": "GoodPass123!", "tenant_slug": slug},
        )
        assert r.status_code == 200, r.text
        return tenant_id, {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _make


@pytest_asyncio.fixture
async def rls_engine(setup_schema):
    """Async engine for tenant-isolation tests.

    Connects as the container superuser but the tests immediately `SET ROLE
    sanket_app` per transaction (see `as_sanket_app`), so every query is subject
    to RLS exactly as the application is in production.
    """
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        yield engine
    finally:
        await engine.dispose()
