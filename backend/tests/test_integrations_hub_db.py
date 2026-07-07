"""DB-backed integration tests for the Integrations Hub.

Exercises the real orchestration paths against a Postgres built from the actual
migration chain (see conftest): file import into the canonical schema, generic
connect persistence, and token-authenticated push ingest. Pure mapping logic is
covered separately in ``test_file_import.py``.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.connectors import get_spec
from app.core.security import hash_password
from app.models.enums import IndustryCode
from app.routers.integrations_hub import _hash_token
from app.services.integrations.file_import import import_rows


async def _seed_user(db: AsyncSession, tenant_id: uuid.UUID, email: str, password: str) -> None:
    settings = get_settings()
    await db.execute(
        text(
            """
            INSERT INTO users (id, tenant_id, email, password_hash, full_name,
                               role, active_industry, is_active)
            VALUES (:id, :tid, :email, :hash, 'Hub Test', 'admin', 'fashion', TRUE)
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


@pytest_asyncio.fixture
async def db(setup_schema):
    from app.core.database import Database

    get_settings.cache_clear()
    database = Database(get_settings())
    yield database
    await database.close()


@pytest_asyncio.fixture
async def tenant_id(db) -> uuid.UUID:
    """A fashion-enabled tenant created via a privileged (RLS-bypassing) session."""
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
                VALUES (:id, :slug, 'Hub Test', 'enterprise', 'active',
                        ARRAY['fashion']::industry_code[], 'fashion')
                """
            ),
            {"id": str(tid), "slug": f"hub-{tid.hex[:8]}"},
        )
    return tid


# ── File import ───────────────────────────────────────────────────────────────
async def test_import_sales_creates_skus_and_rows(db, tenant_id):
    headers = ["sku", "quantity", "selling_price", "timestamp"]
    records = [
        {"sku": "SKU-A", "quantity": "5", "selling_price": "1200", "timestamp": "2026-06-15"},
        {"sku": "SKU-B", "quantity": "2", "selling_price": "500", "timestamp": "2026-06-10"},
        {"sku": "", "quantity": "3", "selling_price": "100", "timestamp": "2026-06-01"},  # skipped
    ]
    stats = await import_rows(
        db=db, tenant_id=tenant_id, industry=IndustryCode.fashion,
        kind="sales", headers=headers, records=records,
    )
    assert stats["rows_imported"] == 2
    assert stats["rows_skipped"] == 1
    assert stats["skus_created"] == 2
    assert stats["sales_rows"] == 2

    async with db.session(str(tenant_id)) as session:
        n = await session.scalar(
            text("SELECT COUNT(*) FROM historical_sales WHERE tenant_id = :t AND metadata->>'source' = 'upload'"),
            {"t": tenant_id},
        )
    assert n == 2


async def test_import_inventory_upserts_idempotently(db, tenant_id):
    headers = ["sku", "available_stock", "reserved_stock", "warehouse_id"]
    records = [{"sku": "INV-1", "available_stock": "250", "reserved_stock": "40", "warehouse_id": "WH01"}]

    first = await import_rows(db=db, tenant_id=tenant_id, industry=IndustryCode.fashion,
                              kind="inventory", headers=headers, records=records)
    assert first["inventory_rows"] == 1

    # Re-import with new numbers → same row updated, not duplicated.
    records[0]["available_stock"] = "300"
    await import_rows(db=db, tenant_id=tenant_id, industry=IndustryCode.fashion,
                      kind="inventory", headers=headers, records=records)

    async with db.session(str(tenant_id)) as session:
        rows = (await session.execute(
            text("SELECT on_hand_units FROM inventory_levels WHERE tenant_id = :t"),
            {"t": tenant_id},
        )).all()
    assert len(rows) == 1
    assert int(rows[0][0]) == 300


async def test_import_products_single_upsert(db, tenant_id):
    headers = ["sku", "name", "brand", "category", "price"]
    records = [{"sku": "P-1", "name": "Widget", "brand": "Acme", "category": "Tools", "price": "9.99"}]
    stats = await import_rows(db=db, tenant_id=tenant_id, industry=IndustryCode.fashion,
                              kind="products", headers=headers, records=records)
    assert stats["rows_imported"] == 1

    async with db.session(str(tenant_id)) as session:
        row = (await session.execute(
            text("SELECT unit_price, attributes->>'brand' FROM skus WHERE tenant_id = :t AND sku_code = 'P-1'"),
            {"t": tenant_id},
        )).one()
    assert float(row[0]) == 9.99
    assert row[1] == "Acme"


async def test_import_missing_required_column_raises(db, tenant_id):
    with pytest.raises(ValueError, match="missing required column"):
        await import_rows(db=db, tenant_id=tenant_id, industry=IndustryCode.fashion,
                          kind="sales", headers=["foo", "bar"], records=[{"foo": "1"}])


# ── Catalog endpoint (authenticated) ──────────────────────────────────────────
async def test_catalog_endpoint_lists_all_providers(client, db_session, test_tenant_id):
    await _seed_user(db_session, test_tenant_id, "catalog@test.com", "GoodPass123!")
    headers = await _login(client, "catalog@test.com", "GoodPass123!")
    resp = await client.get("/api/v1/integrations/catalog", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 30
    assert body["live"] >= 3
    keys = {c["key"] for g in body["groups"] for c in g["connectors"]}
    assert {"shopify", "csv_upload", "sap", "snowflake"} <= keys


# ── Push ingest (token-authenticated, no JWT) ─────────────────────────────────
async def test_push_ingest_token_auth_and_sales(client, db_session, test_tenant_id):
    token = "test-push-token-123"
    await db_session.execute(
        text(
            """
            INSERT INTO integration_connections
                (id, tenant_id, provider, status, target_industry, state, last_sync_stats)
            VALUES (:id, :tid, 'rest_api', 'connected', 'fashion',
                    CAST(:state AS jsonb), '{}')
            """
        ),
        {"id": str(uuid.uuid4()), "tid": str(test_tenant_id),
         "state": f'{{"config": {{"push_token_sha256": "{_hash_token(token)}"}}, "credentials_enc": {{}}}}'},
    )
    await db_session.commit()

    # Bad token → 401 from the endpoint's own token check (not the middleware).
    bad = await client.post("/api/v1/integrations/ingest",
                            headers={"X-Sanket-Token": "nope"}, json={"sku": "X", "quantity": 1})
    assert bad.status_code == 401

    # Good token, two events (one invalid) → 1 accepted.
    good = await client.post(
        "/api/v1/integrations/ingest",
        headers={"X-Sanket-Token": token},
        json={"events": [
            {"sku": "PUSH-1", "quantity": 2, "revenue": 2500, "timestamp": "2026-06-15T14:20:00Z"},
            {"sku": "", "quantity": 1},
        ]},
    )
    assert good.status_code == 200, good.text
    assert good.json()["accepted"] == 1

    n = await db_session.scalar(
        text("SELECT COUNT(*) FROM historical_sales WHERE tenant_id = :t AND metadata->>'source' = 'rest_api'"),
        {"t": test_tenant_id},
    )
    assert n == 1


def test_spec_lookup_for_push_providers():
    assert get_spec("rest_api").availability.value == "beta"
    assert get_spec("webhooks").availability.value == "beta"
