from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import hash_password

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _clear_login_attempts(client: AsyncClient):
    """Reset the brute-force counters around every test in this module.

    Clearing only the in-process dict was not enough. When Redis is running the
    counters live there instead, and nothing cleared them between *sessions* --
    so the lockout test, which deliberately drives the per-IP counter past its
    threshold, left 127.0.0.1 locked out for the next run. The following run's
    first wrong-password test then got a 429 where it expected a 401, and the
    suite failed for reasons that had nothing to do with the code under test.
    """
    from app.core import login_attempt

    async def _reset() -> None:
        login_attempt._in_process.clear()
        app = getattr(client, "_transport", None) and getattr(
            client._transport, "app", None
        )
        redis_client = getattr(app.state, "redis", None) if app is not None else None
        if redis_client is None:
            return
        keys = await redis_client.keys("lf:login_attempt:*")
        if keys:
            await redis_client.delete(*keys)

    await _reset()
    yield
    await _reset()


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


async def test_sandbox_session_missing_account_returns_503(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "sandbox_tenant_slug", "missing-sandbox-tenant")
    r = await client.post("/api/v1/auth/sandbox-session")
    assert r.status_code == 503
    assert r.json()["detail"] == "Sandbox is temporarily unavailable"


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


async def test_industry_header_cannot_switch_industry(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    """The header may agree with the workspace. It may not choose.

    This replaces a test that asserted the opposite -- that a tenant could
    switch freely among the industries in its token claim. That behaviour is
    what is being removed: signup granted every tenant all five verticals, so
    "switch to a subscribed industry" meant "switch to any industry".
    """
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

    # test-tenant is a fashion workspace. Its own industry is fine.
    same = await client.get(
        "/api/v1/industry/context",
        headers={**headers, "X-Industry-Code": "fashion"},
    )
    assert same.status_code == 200
    assert same.json()["code"] == "fashion"

    # Every other industry is refused, whether or not it once appeared in a claim.
    for other in ("electronics", "pharma", "agrocenter", "hardware"):
        denied = await client.get(
            "/api/v1/industry/context",
            headers={**headers, "X-Industry-Code": other},
        )
        assert denied.status_code == 403, f"{other} was not refused"

    # An unknown code is still a bad request, not a forbidden one.
    unknown = await client.get(
        "/api/v1/industry/context",
        headers={**headers, "X-Industry-Code": "crypto"},
    )
    assert unknown.status_code == 400


# ── /auth/signup (self-service workspace creation) ───────────────────────────


async def test_signup_requires_an_industry(client: AsyncClient) -> None:
    """There is no default. A workspace without an industry cannot exist."""
    r = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Acme Owner",
            "email": "owner@acme-none.example.com",
            "password": "Sup3rSecret!",
            "tenant_slug": "acme-none",
        },
    )
    assert r.status_code == 422, r.text
    # Assert on the field, not just the status: a 422 for some other reason
    # (a rejected email domain, say) would otherwise look like a pass.
    assert any(
        d["loc"][-1] == "industry" and d["type"] == "missing" for d in r.json()["detail"]
    ), r.text


async def test_signup_rejects_an_industry_outside_the_canonical_enum(
    client: AsyncClient,
) -> None:
    r = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Acme Owner",
            "email": "owner@acme-bogus.example.com",
            "password": "Sup3rSecret!",
            "tenant_slug": "acme-bogus",
            "industry": "crypto",
        },
    )
    assert r.status_code == 422, r.text
    assert any(d["loc"][-1] == "industry" for d in r.json()["detail"]), r.text


async def test_signup_creates_a_workspace_with_exactly_that_industry(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    r = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Acme Owner",
            "email": "owner@acme-pharma.example.com",
            "password": "Sup3rSecret!",
            "tenant_slug": "acme-pharma",
            "industry": "pharma",
        },
    )
    assert r.status_code == 201, r.text

    row = await db_session.execute(
        text(
            "SELECT industry::text, industries::text[] FROM tenants "
            "WHERE slug = 'acme-pharma'"
        )
    )
    industry, industries = row.one()
    assert industry == "pharma"
    assert industries == ["pharma"], "a new workspace must not receive every industry"


async def test_signup_owner_inherits_the_workspace_industry(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Hardware Owner",
            "email": "owner@acme-hw.example.com",
            "password": "Sup3rSecret!",
            "tenant_slug": "acme-hw",
            "industry": "hardware",
        },
    )
    active = await db_session.scalar(
        text("SELECT active_industry::text FROM users WHERE email = 'owner@acme-hw.example.com'")
    )
    assert active == "hardware"


async def test_signup_seeds_one_industry_profile_not_five(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Agro Owner",
            "email": "owner@acme-agro.example.com",
            "password": "Sup3rSecret!",
            "tenant_slug": "acme-agro",
            "industry": "agrocenter",
        },
    )
    rows = (
        await db_session.execute(
            text(
                "SELECT p.industry::text FROM industry_profiles p "
                "JOIN tenants t ON t.id = p.tenant_id WHERE t.slug = 'acme-agro'"
            )
        )
    ).scalars().all()
    assert rows == ["agrocenter"]


async def test_signup_still_refuses_to_join_an_existing_workspace(
    client: AsyncClient, test_tenant_id: uuid.UUID
) -> None:
    """Public signup must never be a way into someone else's workspace."""
    r = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Intruder",
            "email": "intruder@test.com",
            "password": "Sup3rSecret!",
            "tenant_slug": "test-tenant",
            "industry": "fashion",
        },
    )
    assert r.status_code == 409


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
            INSERT INTO tenants (id, slug, display_name, tier, status, industry)
            VALUES (:id, 'sanket-dev', 'SANKET Dev Tenant', 'growth', 'active',
                    'fashion')
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
