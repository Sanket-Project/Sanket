from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import hash_password

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clear_login_attempts():
    """The in-process brute-force counter is module global — reset it between
    tests so per-IP failures from one test don't leak into the next."""
    from app.core import login_attempt

    login_attempt._in_process.clear()
    yield
    login_attempt._in_process.clear()


async def _seed_user(
    db: AsyncSession, tenant_id: uuid.UUID, email: str, password: str
) -> uuid.UUID:
    user_id = uuid.uuid4()
    settings = get_settings()
    await db.execute(
        text(
            """
            INSERT INTO users (id, tenant_id, email, password_hash,
                               full_name, role, active_industry, is_active)
            VALUES (:id, :tid, :email, :hash, 'Test User',
                    'admin', 'fashion', TRUE)
            """
        ),
        {
            "id": str(user_id),
            "tid": str(tenant_id),
            "email": email,
            "hash": hash_password(password, settings),
        },
    )
    await db.commit()
    return user_id


# ── /auth/dev-login (dev-fallback identity provider) ─────────────────────────


async def test_dev_login_success(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    await _seed_user(db_session, test_tenant_id, "user@test.com", "Sup3rSecret!")
    r = await client.post(
        "/api/v1/auth/dev-login",
        json={
            "email": "user@test.com",
            "password": "Sup3rSecret!",
            "tenant_slug": "test-tenant",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["active_industry"] == "fashion"
    assert body["role"] == "admin"
    assert body["email"] == "user@test.com"
    assert len(body["access_token"]) > 50


async def test_dev_login_wrong_password_returns_401(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    await _seed_user(db_session, test_tenant_id, "user2@test.com", "RightPass1!")
    r = await client.post(
        "/api/v1/auth/dev-login",
        json={
            "email": "user2@test.com",
            "password": "WrongPass1!",
            "tenant_slug": "test-tenant",
        },
    )
    assert r.status_code == 401
    assert "Invalid" in r.json()["detail"]


async def test_dev_login_unknown_tenant_returns_401(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/dev-login",
        json={
            "email": "noone@nowhere.com",
            "password": "doesntmatter",
            "tenant_slug": "ghost-tenant",
        },
    )
    assert r.status_code == 401


async def test_dev_login_lockout_after_five_failures(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    # Clear Redis keys to avoid test pollution when Redis is running
    app = getattr(client, "_transport", None) and getattr(client._transport, "app", None)
    if app is not None:
        redis_client = getattr(app.state, "redis", None)
        if redis_client is not None:
            await redis_client.delete("lf:login_attempt:test-tenant:lockme@test.com")
            await redis_client.delete("lf:login_attempt:ip:127.0.0.1")
            await redis_client.delete("lf:login_attempt:ip:unknown")

    await _seed_user(db_session, test_tenant_id, "lockme@test.com", "CorrectHorse1!")
    payload = {
        "email": "lockme@test.com",
        "password": "WrongOne1!",
        "tenant_slug": "test-tenant",
    }
    for _ in range(5):
        r = await client.post("/api/v1/auth/dev-login", json=payload)
        assert r.status_code == 401
    # 6th attempt — now locked (per-account threshold is 5)
    r = await client.post("/api/v1/auth/dev-login", json=payload)
    assert r.status_code == 429
    assert "Retry-After" in r.headers


# ── /auth/sandbox-session (server-side public demo login) ────────────────────


async def test_sandbox_session_returns_dev_token(
    client: AsyncClient,
    db_session: AsyncSession,
    test_tenant_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public sandbox authenticates entirely server-side: the client sends
    no body and no credentials, yet gets a usable dev bearer back."""
    await _seed_user(db_session, test_tenant_id, "sandbox@test.com", "Irrelevant1!")
    settings = get_settings()
    monkeypatch.setattr(settings, "sandbox_tenant_slug", "test-tenant")
    monkeypatch.setattr(settings, "sandbox_email", "sandbox@test.com")

    r = await client.post("/api/v1/auth/sandbox-session")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "dev"
    assert body["custom_token"] is None
    assert len(body["access_token"]) > 50
    assert body["email"] == "sandbox@test.com"
    assert body["role"] == "admin"


async def test_sandbox_session_disabled_returns_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "sandbox_enabled", False)
    r = await client.post("/api/v1/auth/sandbox-session")
    assert r.status_code == 404


# ── /auth/session + middleware token verification ────────────────────────────


async def test_session_exchange_with_dev_token(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    await _seed_user(db_session, test_tenant_id, "sess@test.com", "GoodPass123!")
    login = await client.post(
        "/api/v1/auth/dev-login",
        json={
            "email": "sess@test.com",
            "password": "GoodPass123!",
            "tenant_slug": "test-tenant",
        },
    )
    token = login.json()["access_token"]
    r = await client.post(
        "/api/v1/auth/session", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "sess@test.com"
    assert r.json()["role"] == "admin"


async def test_protected_route_requires_token(client: AsyncClient) -> None:
    r = await client.get("/api/v1/industry/context")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate") == "Bearer"


async def test_protected_route_rejects_tampered_token(client: AsyncClient) -> None:
    r = await client.get(
        "/api/v1/industry/context",
        headers={"Authorization": "Bearer not.a.valid.token"},
    )
    assert r.status_code == 401


async def test_industry_switch_to_unsubscribed_is_forbidden(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    # test-tenant is subscribed to fashion/electronics/pharma, NOT agrocenter.
    await _seed_user(db_session, test_tenant_id, "switch@test.com", "GoodPass123!")
    login = await client.post(
        "/api/v1/auth/dev-login",
        json={
            "email": "switch@test.com",
            "password": "GoodPass123!",
            "tenant_slug": "test-tenant",
        },
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Allowed switch (electronics is subscribed) → not a 403
    ok = await client.get(
        "/api/v1/industry/context",
        headers={**headers, "X-Industry-Code": "electronics"},
    )
    assert ok.status_code != 403

    # Denied switch (agrocenter not subscribed) → 403
    denied = await client.get(
        "/api/v1/industry/context",
        headers={**headers, "X-Industry-Code": "agrocenter"},
    )
    assert denied.status_code == 403


async def test_security_headers_present(client: AsyncClient) -> None:
    r = await client.get("/api/v1/auth/config")
    assert r.status_code == 200
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in r.headers


async def test_session_auto_provisions_unregistered_google_user(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1. Create the 'sanket-dev' tenant in the test DB
    tenant_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status,
                                 industries, active_industry)
            VALUES (:id, 'sanket-dev', 'SANKET Dev Tenant', 'growth', 'active',
                    ARRAY['fashion']::industry_code[], 'fashion')
            ON CONFLICT (slug) DO NOTHING
            """
        ),
        {"id": str(tenant_id)},
    )
    await db_session.commit()

    # 2. Mock get_verifier().verify_identity to return a decoded Google token
    mock_identity = {
        "uid": "google-oauth2|1234567890",
        "email": "new_google_user@sanket-dev.com",
        "name": "New Google User",
    }
    
    class MockVerifier:
        def verify_identity(self, token: str):
            return mock_identity

    from app.routers import auth
    monkeypatch.setattr(auth, "get_verifier", lambda: MockVerifier())

    # 3. Call /auth/session with a dummy bearer token
    r = await client.post(
        "/api/v1/auth/session",
        headers={"Authorization": "Bearer dummy-google-token"}
    )

    # 4. Assert response is 200 OK and contains the new user's details
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "new_google_user@sanket-dev.com"
    assert body["full_name"] == "New Google User"
    assert body["role"] == "admin"

    # 5. Verify user is in database
    result = await db_session.execute(
        text("SELECT email, firebase_uid, full_name FROM users WHERE email = 'new_google_user@sanket-dev.com'")
    )
    user = result.fetchone()
    assert user is not None
    assert user[1] == "google-oauth2|1234567890"
    assert user[2] == "New Google User"

