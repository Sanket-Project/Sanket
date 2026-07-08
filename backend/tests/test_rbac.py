from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import hash_password
from app.models.enums import UserRole

pytestmark = pytest.mark.asyncio


async def _seed_tenant(db: AsyncSession, slug: str, name: str) -> uuid.UUID:
    """Seed a tenant if not already present and return its ID."""
    result = await db.execute(text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": slug})
    row = result.fetchone()
    if row:
        return row[0]

    tid = uuid.uuid4()
    await db.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status,
                                 industries, active_industry, max_users)
            VALUES (:id, :slug, :name, 'enterprise', 'active',
                    ARRAY['fashion','electronics','pharma']::industry_code[],
                    'fashion', 100)
            """
        ),
        {"id": str(tid), "slug": slug, "name": name},
    )
    await db.commit()
    return tid


async def _seed_user(
    db: AsyncSession, tenant_id: uuid.UUID, email: str, password: str, role: UserRole
) -> uuid.UUID:
    """Seed a user with the specified role and return their user ID."""
    user_id = uuid.uuid4()
    settings = get_settings()
    await db.execute(
        text(
            """
            INSERT INTO users (id, tenant_id, email, password_hash,
                               full_name, role, active_industry, is_active)
            VALUES (:id, :tid, :email, :hash, :name,
                    :role, 'fashion', TRUE)
            """
        ),
        {
            "id": str(user_id),
            "tid": str(tenant_id),
            "email": email,
            "hash": hash_password(password, settings),
            "name": f"Test {role.value.capitalize()}",
            "role": role.value,
        },
    )
    await db.commit()
    return user_id


async def _get_token(client: AsyncClient, email: str, password: str, tenant_slug: str) -> str:
    """Helper to log in and get a bearer token."""
    r = await client.post(
        "/api/v1/auth/dev-login",
        json={
            "email": email,
            "password": password,
            "tenant_slug": tenant_slug,
        },
    )
    assert r.status_code == 200, f"Login failed for {email}: {r.text}"
    return r.json()["access_token"]


async def _seed_product(db: AsyncSession, tenant_id: uuid.UUID, name: str) -> uuid.UUID:
    """Helper to seed a product under a specific tenant."""
    pid = uuid.uuid4()
    await db.execute(
        text(
            """
            INSERT INTO products (id, tenant_id, industry, name, category, status, attributes)
            VALUES (:id, :tid, 'fashion', :name, 'Test Category', 'active', '{}'::jsonb)
            """
        ),
        {"id": str(pid), "tid": str(tenant_id), "name": name},
    )
    await db.commit()
    return pid


# ── Authentication Tests ──────────────────────────────────────────────────────


async def test_protected_routes_require_authentication(client: AsyncClient) -> None:
    """Protected endpoints must return 401 Unauthorized when no credentials are sent."""
    r = await client.get("/api/v1/products")
    assert r.status_code == 401


# ── RBAC Authorization Tests ──────────────────────────────────────────────────


async def test_rbac_roles_enforce_admin_restrictions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Only roles of Owner or Admin can execute admin-restricted endpoints like invites and deletions.

    Analyst and Viewer must be blocked with 403 Forbidden.
    """
    tenant_a = await _seed_tenant(db_session, "tenant-rbac-test", "RBAC Test Tenant")
    password = "StrongPassword123!"

    # Seed users for each role
    await _seed_user(db_session, tenant_a, "owner@rbac.com", password, UserRole.owner)
    await _seed_user(db_session, tenant_a, "admin@rbac.com", password, UserRole.admin)
    await _seed_user(db_session, tenant_a, "analyst@rbac.com", password, UserRole.analyst)
    await _seed_user(db_session, tenant_a, "viewer@rbac.com", password, UserRole.viewer)

    # Login and acquire tokens
    owner_token = await _get_token(client, "owner@rbac.com", password, "tenant-rbac-test")
    admin_token = await _get_token(client, "admin@rbac.com", password, "tenant-rbac-test")
    analyst_token = await _get_token(client, "analyst@rbac.com", password, "tenant-rbac-test")
    viewer_token = await _get_token(client, "viewer@rbac.com", password, "tenant-rbac-test")

    # We will test two endpoints that require admin role:
    # 1. POST /api/v1/invites (Create invite)
    # 2. DELETE /api/v1/products/{id} (Delete product)

    # --- Test 1: CREATE INVITE (POST /invites) ---
    invite_payload = {"email": "new-user@rbac.com", "role": "analyst"}

    # Viewer gets 403
    r_viewer = await client.post(
        "/api/v1/invites",
        json=invite_payload,
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert r_viewer.status_code == 403

    # Analyst gets 403
    r_analyst = await client.post(
        "/api/v1/invites",
        json=invite_payload,
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert r_analyst.status_code == 403

    # Admin gets 201
    r_admin = await client.post(
        "/api/v1/invites",
        json=invite_payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r_admin.status_code == 201

    # Owner gets 201 (after revoking or using different email due to conflicts)
    invite_payload_owner = {"email": "another-new-user@rbac.com", "role": "analyst"}
    r_owner = await client.post(
        "/api/v1/invites",
        json=invite_payload_owner,
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r_owner.status_code == 201

    # --- Test 2: DELETE PRODUCT (DELETE /products/{id}) ---
    # Seed a product
    pid = await _seed_product(db_session, tenant_a, "Product to Delete")

    # Viewer gets 403
    r_del_viewer = await client.delete(
        f"/api/v1/products/{pid}",
        headers={"Authorization": f"Bearer {viewer_token}", "X-Industry-Code": "fashion"},
    )
    assert r_del_viewer.status_code == 403

    # Analyst gets 403
    r_del_analyst = await client.delete(
        f"/api/v1/products/{pid}",
        headers={"Authorization": f"Bearer {analyst_token}", "X-Industry-Code": "fashion"},
    )
    assert r_del_analyst.status_code == 403

    # Owner gets 200 (happy path)
    r_del_owner = await client.delete(
        f"/api/v1/products/{pid}",
        headers={"Authorization": f"Bearer {owner_token}", "X-Industry-Code": "fashion"},
    )
    assert r_del_owner.status_code == 200
    assert r_del_owner.json()["deleted"] is True


# ── Tenant Isolation Tests ────────────────────────────────────────────────────


async def test_tenant_isolation_at_api_level(client: AsyncClient, db_session: AsyncSession) -> None:
    """Verifies that a user in Tenant B cannot read, write, or delete Tenant A's products."""
    tenant_a = await _seed_tenant(db_session, "tenant-a-iso", "Tenant A")
    tenant_b = await _seed_tenant(db_session, "tenant-b-iso", "Tenant B")
    password = "StrongPassword123!"

    # Seed users
    await _seed_user(db_session, tenant_a, "owner@tenanta.com", password, UserRole.owner)
    await _seed_user(db_session, tenant_b, "owner@tenantb.com", password, UserRole.owner)

    # Login and acquire tokens
    token_a = await _get_token(client, "owner@tenanta.com", password, "tenant-a-iso")
    token_b = await _get_token(client, "owner@tenantb.com", password, "tenant-b-iso")

    # Seed products under Tenant A
    product_a_id = await _seed_product(db_session, tenant_a, "Tenant A Exclusive Product")

    # 1. Tenant A should see their product
    r_list_a = await client.get(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token_a}", "X-Industry-Code": "fashion"},
    )
    assert r_list_a.status_code == 200
    pids_a = [p["id"] for p in r_list_a.json()]
    assert str(product_a_id) in pids_a

    # 2. Tenant B should NOT see Tenant A's product
    r_list_b = await client.get(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token_b}", "X-Industry-Code": "fashion"},
    )
    assert r_list_b.status_code == 200
    pids_b = [p["id"] for p in r_list_b.json()]
    assert str(product_a_id) not in pids_b

    # 3. Tenant B attempting to delete Tenant A's product should return 404
    # (Since RLS / tenant context makes the resource invisible to Tenant B)
    r_delete_cross = await client.delete(
        f"/api/v1/products/{product_a_id}",
        headers={"Authorization": f"Bearer {token_b}", "X-Industry-Code": "fashion"},
    )
    assert r_delete_cross.status_code == 404
