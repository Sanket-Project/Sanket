"""Tests for the direct-SQL connectors (PostgreSQL, MySQL).

Pure validation/safety logic (DSN scheme matching, read-only query guard) is
tested with no network at all. The actual pull-and-import path is exercised
against real local Postgres/MySQL containers (testcontainers, same pattern as
``conftest.py``'s app database) standing in for "the customer's database" —
no paid account needed, matching the rest of this connector's design goal.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import get_settings
from app.connectors import get_spec
from app.core.security import hash_password
from app.models.enums import IndustryCode
from app.services.integrations import sql_source
from app.services.integrations.sql_source import SqlSourceError


# ── Pure logic: no network, no containers ──────────────────────────────────
def test_normalize_dsn_postgres_rewrites_to_async_driver():
    out = sql_source.normalize_dsn("postgres", "postgresql://u:p@host:5432/db")
    assert out.startswith("postgresql+asyncpg://")


def test_normalize_dsn_accepts_postgres_short_scheme():
    out = sql_source.normalize_dsn("postgres", "postgres://u:p@host:5432/db")
    assert out.startswith("postgresql+asyncpg://")


def test_normalize_dsn_mysql_rewrites_to_async_driver():
    out = sql_source.normalize_dsn("mysql", "mysql://u:p@host:3306/db")
    assert out.startswith("mysql+aiomysql://")


def test_normalize_dsn_rejects_mismatched_scheme():
    with pytest.raises(SqlSourceError, match="postgres"):
        sql_source.normalize_dsn("postgres", "mysql://u:p@host:3306/db")


def test_normalize_dsn_rejects_unparseable_dsn():
    with pytest.raises(SqlSourceError):
        sql_source.normalize_dsn("postgres", "not a connection string")


def test_normalize_dsn_unsupported_provider():
    with pytest.raises(SqlSourceError, match="Unsupported"):
        sql_source.normalize_dsn("snowflake", "postgresql://u:p@host/db")


async def test_fetch_rows_rejects_non_select_query():
    with pytest.raises(SqlSourceError, match="SELECT / WITH"):
        await sql_source.fetch_rows("postgres", "postgresql://x/y", "DROP TABLE orders")


async def test_fetch_rows_rejects_stacked_statements():
    with pytest.raises(SqlSourceError, match="single statement"):
        await sql_source.fetch_rows("postgres", "postgresql://x/y", "SELECT 1; DROP TABLE orders")


async def test_fetch_rows_rejects_empty_query():
    with pytest.raises(SqlSourceError, match="empty"):
        await sql_source.fetch_rows("postgres", "postgresql://x/y", "   ")


async def test_fetch_rows_allows_with_cte():
    # A WITH/CTE query should pass the read-only guard (and then fail on the
    # bogus DSN at connection time, proving the guard didn't reject it).
    with pytest.raises(SqlSourceError) as exc_info:
        await sql_source.fetch_rows(
            "postgres", "postgresql+asyncpg://baduser:badpass@127.0.0.1:1/nope",
            "WITH x AS (SELECT 1 AS n) SELECT * FROM x",
        )
    assert "SELECT / WITH" not in str(exc_info.value)


async def test_validate_connection_fails_fast_on_unreachable_dsn():
    with pytest.raises(SqlSourceError, match="connect"):
        await sql_source.validate_connection(
            "postgres", "postgresql+asyncpg://baduser:badpass@127.0.0.1:1/nope"
        )


def test_run_sql_sync_requires_at_least_one_feed_query():
    async def _run():
        await sql_source.run_sql_sync(
            db=None, tenant_id=uuid.uuid4(), provider="postgres",
            industry=IndustryCode.fashion, dsn="postgresql://x/y",
            queries={"sales_query": None, "inventory_query": None, "products_query": None},
        )

    with pytest.raises(SqlSourceError, match="No feed queries configured"):
        asyncio.run(_run())


def test_spec_marks_postgres_and_mysql_live():
    assert get_spec("postgres").availability.value == "live"
    assert get_spec("mysql").availability.value == "live"


# ── Postgres source container (stand-in for "the customer's database") ─────
@pytest.fixture(scope="module")
def pg_source_container():
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg


@pytest_asyncio.fixture(scope="module")
async def pg_source_dsn(pg_source_container) -> str:
    dsn = pg_source_container.get_connection_url()
    engine = create_async_engine(dsn)
    async with engine.begin() as conn:
        await conn.execute(
            text("CREATE TABLE raw_orders (sku text, qty int, sale_date date, price numeric)")
        )
        await conn.execute(
            text(
                "INSERT INTO raw_orders VALUES "
                "('SQL-A', 5, '2026-06-01', 120.0), ('SQL-B', 2, '2026-06-02', 45.5)"
            )
        )
    await engine.dispose()
    return dsn


async def test_fetch_rows_against_real_postgres(pg_source_dsn):
    headers, records = await sql_source.fetch_rows(
        "postgres", pg_source_dsn, "SELECT sku, qty, sale_date, price FROM raw_orders ORDER BY sku"
    )
    assert headers == ["sku", "qty", "sale_date", "price"]
    assert len(records) == 2
    assert records[0]["sku"] == "SQL-A"


async def test_validate_connection_succeeds_against_real_postgres(pg_source_dsn):
    await sql_source.validate_connection("postgres", pg_source_dsn)  # no raise


# ── MySQL source container ──────────────────────────────────────────────────
@pytest.fixture(scope="module")
def mysql_source_container():
    from testcontainers.mysql import MySqlContainer

    with MySqlContainer("mysql:8.0") as mysql:
        yield mysql


@pytest_asyncio.fixture(scope="module")
async def mysql_source_dsn(mysql_source_container) -> str:
    dsn = mysql_source_container.get_connection_url()
    engine = create_async_engine(sql_source.normalize_dsn("mysql", dsn))
    async with engine.begin() as conn:
        await conn.execute(
            text("CREATE TABLE raw_stock (sku VARCHAR(50), available_stock INT, warehouse_id VARCHAR(50))")
        )
        await conn.execute(
            text(
                "INSERT INTO raw_stock VALUES "
                "('SQL-A', 100, 'WH1'), ('SQL-B', 40, 'WH2')"
            )
        )
    await engine.dispose()
    return dsn


async def test_fetch_rows_against_real_mysql(mysql_source_dsn):
    headers, records = await sql_source.fetch_rows(
        "mysql", mysql_source_dsn,
        "SELECT sku, available_stock, warehouse_id FROM raw_stock ORDER BY sku",
    )
    assert set(headers) == {"sku", "available_stock", "warehouse_id"}
    assert len(records) == 2


# ── End-to-end import (DB-backed, mirrors test_integrations_hub_db.py) ──────
@pytest_asyncio.fixture
async def db(setup_schema):
    from app.core.database import Database

    get_settings.cache_clear()
    database = Database(get_settings())
    yield database
    await database.close()


@pytest_asyncio.fixture
async def tenant_id(db) -> uuid.UUID:
    tid = uuid.uuid4()
    async with db.session_no_rls() as session:
        await session.execute(
            text(
                """
                INSERT INTO industries (code, display_name, default_horizon_weeks, audit_level)
                VALUES ('fashion', 'Fashion', 26, 'standard')
                ON CONFLICT DO NOTHING
                """
            )
        )
        await session.execute(
            text(
                """
                INSERT INTO tenants (id, slug, display_name, tier, status,
                                     industries, active_industry)
                VALUES (:id, :slug, 'SQL Source Test', 'enterprise', 'active',
                        ARRAY['fashion']::industry_code[], 'fashion')
                """
            ),
            {"id": str(tid), "slug": f"sqlsrc-{tid.hex[:8]}"},
        )
    return tid


async def test_run_sql_sync_imports_sales_from_postgres(db, tenant_id, pg_source_dsn):
    stats = await sql_source.run_sql_sync(
        db=db, tenant_id=tenant_id, provider="postgres", industry=IndustryCode.fashion,
        dsn=pg_source_dsn,
        queries={
            "sales_query": "SELECT sku, qty, sale_date, price FROM raw_orders",
            "inventory_query": None,
            "products_query": None,
        },
    )
    assert stats["sales"]["rows_imported"] == 2
    assert stats["sales"]["skus_created"] == 2
    assert "synced_at" in stats
    assert "inventory" not in stats

    async with db.session(str(tenant_id)) as session:
        n = await session.scalar(
            text("SELECT COUNT(*) FROM historical_sales WHERE tenant_id = :t"), {"t": tenant_id}
        )
    assert n == 2


async def test_run_sql_sync_imports_inventory_from_mysql(db, tenant_id, mysql_source_dsn):
    stats = await sql_source.run_sql_sync(
        db=db, tenant_id=tenant_id, provider="mysql", industry=IndustryCode.fashion,
        dsn=mysql_source_dsn,
        queries={
            "sales_query": None,
            "inventory_query": "SELECT sku, available_stock, warehouse_id FROM raw_stock",
            "products_query": None,
        },
    )
    assert stats["inventory"]["inventory_rows"] == 2

    async with db.session(str(tenant_id)) as session:
        n = await session.scalar(
            text("SELECT COUNT(*) FROM inventory_levels WHERE tenant_id = :t"), {"t": tenant_id}
        )
    assert n == 2


# ── HTTP-level: connect validates the DSN live, then on-demand sync ─────────
async def _seed_user(db: AsyncSession, tenant_id: uuid.UUID, email: str, password: str) -> None:
    settings = get_settings()
    await db.execute(
        text(
            """
            INSERT INTO users (id, tenant_id, email, password_hash, full_name,
                               role, active_industry, is_active)
            VALUES (:id, :tid, :email, :hash, 'SQL Source Test', 'admin', 'fashion', TRUE)
            """
        ),
        {"id": str(uuid.uuid4()), "tid": str(tenant_id), "email": email,
         "hash": hash_password(password, settings)},
    )
    await db.commit()


async def _login(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    r = await client.post(
        "/api/v1/auth/dev-login",
        json={"email": email, "password": password, "tenant_slug": "test-tenant"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_connect_rejects_missing_feed_query(client, db_session, test_tenant_id, pg_source_dsn):
    await _seed_user(db_session, test_tenant_id, "noquery@test.com", "GoodPass123!")
    headers = await _login(client, "noquery@test.com", "GoodPass123!")
    resp = await client.post(
        "/api/v1/integrations/postgres/connect",
        headers=headers,
        json={"target_industry": "fashion", "credentials": {"dsn": pg_source_dsn}},
    )
    assert resp.status_code == 400
    assert "sales_query" in resp.json()["detail"]


async def test_connect_rejects_unreachable_dsn(client, db_session, test_tenant_id):
    await _seed_user(db_session, test_tenant_id, "baddsn@test.com", "GoodPass123!")
    headers = await _login(client, "baddsn@test.com", "GoodPass123!")
    resp = await client.post(
        "/api/v1/integrations/postgres/connect",
        headers=headers,
        json={
            "target_industry": "fashion",
            "credentials": {
                "dsn": "postgresql://baduser:badpass@127.0.0.1:1/nope",
                "sales_query": "SELECT 1 AS sku, 1 AS quantity, now() AS timestamp",
            },
        },
    )
    assert resp.status_code == 400


async def test_connect_and_sync_postgres_end_to_end(client, db_session, test_tenant_id, pg_source_dsn):
    await _seed_user(db_session, test_tenant_id, "sqlsync@test.com", "GoodPass123!")
    headers = await _login(client, "sqlsync@test.com", "GoodPass123!")

    connect_resp = await client.post(
        "/api/v1/integrations/postgres/connect",
        headers=headers,
        json={
            "target_industry": "fashion",
            "credentials": {
                "dsn": pg_source_dsn,
                "sales_query": "SELECT sku, qty, sale_date, price FROM raw_orders",
            },
        },
    )
    assert connect_resp.status_code == 200, connect_resp.text
    body = connect_resp.json()
    assert body["status"] == "connected"
    assert body["supports_sync"] is True

    sync_resp = await client.post("/api/v1/integrations/postgres/sync", headers=headers)
    assert sync_resp.status_code == 202, sync_resp.text
    assert sync_resp.json()["status"] == "syncing"

    # The sync runs as an in-process background task; poll the catalog for it
    # to settle rather than racing it.
    conn = None
    for _ in range(50):
        cat = await client.get("/api/v1/integrations/catalog", headers=headers)
        conn = next(c for g in cat.json()["groups"] for c in g["connectors"] if c["key"] == "postgres")
        if conn["status"] != "syncing":
            break
        await asyncio.sleep(0.1)
    assert conn is not None
    assert conn["status"] == "connected", conn
    assert conn["last_sync_status"] == "success"

    # A second sync while one is "running" would 409 — but it already
    # finished, so a back-to-back sync should be accepted again.
    again = await client.post("/api/v1/integrations/postgres/sync", headers=headers)
    assert again.status_code == 202
