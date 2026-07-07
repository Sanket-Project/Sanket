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

    with PostgresContainer(
        image="pgvector/pgvector:pg16", driver="asyncpg"
    ).with_env("POSTGRES_DB", "sanket_test") as pg:
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


@pytest_asyncio.fixture
async def test_tenant_id(db_session: AsyncSession) -> uuid.UUID:
    # Avoid duplicate key value unique violation by checking if tenant already exists
    result = await db_session.execute(
        text("SELECT id FROM tenants WHERE slug = 'test-tenant'")
    )
    row = result.fetchone()
    if row:
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
            INSERT INTO tenants (id, slug, display_name, tier, status,
                                 industries, active_industry)
            VALUES (:id, 'test-tenant', 'Test Tenant', 'enterprise', 'active',
                    ARRAY['fashion','electronics','pharma']::industry_code[],
                    'fashion')
            """
        ),
        {"id": str(tenant_id)},
    )
    await db_session.commit()
    return tenant_id


@pytest_asyncio.fixture
async def client(setup_schema) -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Trigger lifespan
        async with app.router.lifespan_context(app):
            yield ac


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
