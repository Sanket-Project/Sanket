"""The industry authorization boundary.

Distinct from tenant isolation. RLS answers *whose company data may this user
read*; these tests cover *which product modules may this company access*.

Before this boundary existed it was not enforced at all: every router under
`routers/industries/` accepted an `ActiveIndustry` dependency and then hardcoded
its own `IndustryCode` in the query without ever comparing the two, so any
authenticated tenant got a 200 from any industry's endpoints.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import Request
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PermissionDeniedError, ValidationError
from app.core.firebase_auth import get_verifier
from app.models.enums import IndustryCode

pytestmark = pytest.mark.asyncio


def _request(industry: str | None, tenant_id: str | None = "t") -> Request:
    req = Request({"type": "http", "headers": [], "method": "GET", "path": "/"})
    req.state.tenant_id = tenant_id
    req.state.industry_code = industry
    return req


# ── The primitive ────────────────────────────────────────────────────────────


async def test_tenant_industry_reads_the_verified_claim() -> None:
    from app.core.industry_scope import tenant_industry

    assert tenant_industry(_request("pharma")) is IndustryCode.pharma


async def test_tenant_industry_refuses_an_unauthenticated_request() -> None:
    from app.core.exceptions import AuthenticationError
    from app.core.industry_scope import tenant_industry

    with pytest.raises(AuthenticationError):
        tenant_industry(_request("pharma", tenant_id=None))


async def test_assert_industry_allows_the_workspaces_own() -> None:
    from app.core.industry_scope import assert_industry

    assert assert_industry("pharma", IndustryCode.pharma) is IndustryCode.pharma


async def test_assert_industry_defaults_to_the_workspace_when_absent() -> None:
    """Omitting a target industry means the workspace's, never a client choice."""
    from app.core.industry_scope import assert_industry

    assert assert_industry(None, IndustryCode.hardware) is IndustryCode.hardware


async def test_assert_industry_refuses_another_industry() -> None:
    from app.core.industry_scope import assert_industry

    with pytest.raises(PermissionDeniedError) as exc:
        assert_industry("fashion", IndustryCode.pharma)
    assert exc.value.status_code == 403


async def test_assert_industry_refuses_an_unknown_code() -> None:
    from app.core.industry_scope import assert_industry

    with pytest.raises(ValidationError):
        assert_industry("crypto", IndustryCode.pharma)


# ── The boundary, end to end ─────────────────────────────────────────────────


async def _token(db: AsyncSession, tenant_id: uuid.UUID, industry: str) -> str:
    user_id = uuid.uuid4()
    email = f"scope-{user_id.hex[:8]}@scope.example.com"
    await db.execute(
        text(
            """
            INSERT INTO users (id, tenant_id, email, full_name, role,
                               active_industry, is_active)
            VALUES (:uid, :tid, :email, 'Scope User', 'admin', :ind, TRUE)
            """
        ),
        {"uid": str(user_id), "tid": str(tenant_id), "email": email, "ind": industry},
    )
    await db.commit()
    token, _ = get_verifier().mint_dev_token(
        uid=str(user_id),
        puid=str(user_id),
        email=email,
        tid=str(tenant_id),
        role="admin",
        ind=industry,
    )
    return token


async def test_own_industry_endpoint_succeeds(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    token = await _token(db_session, test_tenant_id, "fashion")
    r = await client.get(
        "/api/v1/fashion/overview", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, r.text


async def test_every_other_industry_endpoint_is_forbidden(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    """A directly typed URL must fail even with a completely valid token."""
    token = await _token(db_session, test_tenant_id, "fashion")
    for path in (
        "/api/v1/pharma/overview",
        "/api/v1/electronics/overview",
        "/api/v1/agrocenter/overview",
        "/api/v1/hardware/overview",
    ):
        r = await client.get(path, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403, f"{path} returned {r.status_code}"


async def test_the_boundary_holds_from_the_other_side(
    client: AsyncClient, db_session: AsyncSession, pharma_tenant_id: uuid.UUID
) -> None:
    """A pharma workspace reaches pharma and nothing else -- the mirror image."""
    token = await _token(db_session, pharma_tenant_id, "pharma")
    headers = {"Authorization": f"Bearer {token}"}

    allowed = await client.get("/api/v1/pharma/overview", headers=headers)
    assert allowed.status_code == 200, allowed.text

    denied = await client.get("/api/v1/fashion/overview", headers=headers)
    assert denied.status_code == 403


async def test_other_industry_is_403_even_without_a_subscription(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The industry answer comes before the paywall.

    A brand-new workspace has no subscription, so every gated router would
    otherwise answer 402 first — and "another industry" would be indistinguishable
    from "you have not paid" depending on billing state. The reason a fashion
    workspace cannot read pharma has nothing to do with billing, so it should not
    change when they subscribe.
    """
    token = await _signup(client, "unpaid-co", "fashion")
    headers = {"Authorization": f"Bearer {token}"}

    denied = await client.get("/api/v1/pharma/overview", headers=headers)
    assert denied.status_code == 403, denied.text

    # Their own industry still hits the paywall, which is the correct answer there.
    own = await client.get("/api/v1/fashion/overview", headers=headers)
    assert own.status_code == 402, own.text


async def test_cross_industry_correlation_is_unavailable(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    """Cross-industry analysis cannot be offered to a one-industry workspace."""
    token = await _token(db_session, test_tenant_id, "fashion")
    r = await client.get(
        "/api/v1/alerts/cross-industry", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 404


# ── Enumeration: public catalog, no authenticated listing ────────────────────


async def test_industry_catalog_is_public(client: AsyncClient) -> None:
    """The signup form needs the canonical list before anyone holds a token.

    It is also the honest public position: prospects may browse every vertical
    SANKET supports. What they may not do is reach one from inside a workspace
    scoped to another.
    """
    r = await client.get("/api/v1/industry/catalog")
    assert r.status_code == 200, r.text
    assert set(r.json()) == {
        "fashion",
        "electronics",
        "pharma",
        "agrocenter",
        "hardware",
    }


async def test_authenticated_industry_enumeration_is_gone(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    """An authenticated user has exactly one industry; there is nothing to list."""
    token = await _token(db_session, test_tenant_id, "fashion")
    r = await client.get(
        "/api/v1/industry/available", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 404


# ── The correction window ────────────────────────────────────────────────────


async def _signup(client: AsyncClient, slug: str, industry: str) -> str:
    """Create a workspace through the real signup path and return a bearer."""
    r = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": f"{slug} Owner",
            "email": f"owner@{slug}.example.com",
            "password": "Sup3rSecret!",
            "tenant_slug": slug,
            "industry": industry,
        },
    )
    assert r.status_code == 201, r.text
    login = await client.post(
        "/api/v1/auth/dev-login",
        json={
            "email": f"owner@{slug}.example.com",
            "password": "Sup3rSecret!",
            "tenant_slug": slug,
        },
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


async def test_industry_can_be_corrected_while_setup_is_incomplete(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Choosing the wrong industry at signup must be recoverable, briefly."""
    token = await _signup(client, "mistake-co", "fashion")
    r = await client.post(
        "/api/v1/industry/activate",
        json={"code": "pharma"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text

    row = await db_session.execute(
        text(
            "SELECT industry::text, industries::text[] FROM tenants "
            "WHERE slug = 'mistake-co'"
        )
    )
    industry, industries = row.one()
    assert industry == "pharma"
    assert industries == ["pharma"], "the mirror follows the correction"


async def test_correction_reissues_a_token_carrying_the_new_industry(
    client: AsyncClient
) -> None:
    """Without a fresh token the rest of the session runs on the old claim."""
    token = await _signup(client, "reissue-co", "fashion")
    r = await client.post(
        "/api/v1/industry/activate",
        json={"code": "hardware"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    new_token = r.json().get("access_token")
    assert new_token, "dev mode must hand back a re-minted bearer"

    # The new bearer resolves to the corrected industry. (Asserted against
    # /industry/context rather than an industry dashboard: a freshly created
    # workspace has no subscription, so every gated route answers 402 first and
    # would tell us nothing about the claim.)
    ctx = await client.get(
        "/api/v1/industry/context",
        headers={"Authorization": f"Bearer {new_token}"},
    )
    assert ctx.status_code == 200, ctx.text
    assert ctx.json()["code"] == "hardware"

    # And the superseded bearer still names the old one, which is exactly why
    # it has to be replaced rather than left to expire.
    stale = await client.get(
        "/api/v1/industry/context", headers={"Authorization": f"Bearer {token}"}
    )
    assert stale.json()["code"] == "fashion"


async def test_industry_locks_once_setup_completes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _signup(client, "locked-co", "fashion")
    await db_session.execute(
        text(
            "UPDATE tenants SET settings = jsonb_set(settings, "
            "'{onboarding,status}', '\"complete\"') WHERE slug = 'locked-co'"
        )
    )
    await db_session.commit()

    r = await client.post(
        "/api/v1/industry/activate",
        json={"code": "pharma"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409, r.text


# ── Ingestion cannot cross the boundary ──────────────────────────────────────


# These run against `pharma-tenant` rather than the shared `test-tenant`.
# Ingestion tests leave rows behind -- a product, an integration connection --
# and `test-tenant` is used by most of the suite, including a push-ingest test
# that raw-INSERTs its own `rest_api` connection and collides with one created
# here on the tenant/provider unique constraint.


async def test_upload_cannot_target_another_industry(
    client: AsyncClient, db_session: AsyncSession, pharma_tenant_id: uuid.UUID
) -> None:
    """An old client posting a mismatched target_industry is refused.

    Not silently coerced: a client that believes it can write into another
    industry is telling us its state is wrong, and that deserves an error.
    """
    token = await _token(db_session, pharma_tenant_id, "pharma")
    r = await client.post(
        "/api/v1/integrations/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"kind": "products", "target_industry": "fashion"},
        files={"file": ("p.csv", b"name,category\nA Tablet,analgesics\n", "text/csv")},
    )
    assert r.status_code == 403, r.text


async def test_upload_defaults_to_the_workspace_industry(
    client: AsyncClient, db_session: AsyncSession, pharma_tenant_id: uuid.UUID
) -> None:
    """Omitting the field is now the normal path: the server knows the industry."""
    token = await _token(db_session, pharma_tenant_id, "pharma")
    r = await client.post(
        "/api/v1/integrations/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"kind": "products"},
        files={"file": ("p.csv", b"name,category\nA Tablet,analgesics\n", "text/csv")},
    )
    assert r.status_code == 200, r.text

    industry = await db_session.scalar(
        text(
            "SELECT industry::text FROM products WHERE tenant_id = :tid "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"tid": str(pharma_tenant_id)},
    )
    assert industry == "pharma"


async def test_connect_cannot_target_another_industry(
    client: AsyncClient, db_session: AsyncSession, pharma_tenant_id: uuid.UUID
) -> None:
    token = await _token(db_session, pharma_tenant_id, "pharma")
    r = await client.post(
        "/api/v1/integrations/rest_api/connect",
        json={"target_industry": "fashion", "credentials": {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403, r.text


async def test_connect_records_the_workspace_industry(
    client: AsyncClient, db_session: AsyncSession, pharma_tenant_id: uuid.UUID
) -> None:
    token = await _token(db_session, pharma_tenant_id, "pharma")
    r = await client.post(
        "/api/v1/integrations/rest_api/connect",
        json={"credentials": {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code in (200, 201), r.text

    industry = await db_session.scalar(
        text(
            "SELECT target_industry::text FROM integration_connections "
            "WHERE tenant_id = :tid AND provider = 'rest_api'"
        ),
        {"tid": str(pharma_tenant_id)},
    )
    assert industry == "pharma"


async def test_industry_locks_once_the_workspace_holds_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Data arriving locks the industry even mid-setup: it was ingested under
    the old one, and silently reinterpreting it as another industry's would be
    worse than refusing."""
    token = await _signup(client, "hasdata-co", "fashion")
    tenant_id = await db_session.scalar(
        text("SELECT id FROM tenants WHERE slug = 'hasdata-co'")
    )
    await db_session.execute(
        text(
            """
            INSERT INTO products (id, tenant_id, industry, name, category, status)
            VALUES (gen_random_uuid(), :tid, 'fashion', 'A Product', 'tops',
                    'active')
            """
        ),
        {"tid": str(tenant_id)},
    )
    await db_session.commit()

    r = await client.post(
        "/api/v1/industry/activate",
        json={"code": "pharma"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409, r.text
