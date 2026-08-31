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


async def test_cross_industry_correlation_is_unavailable(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    """Cross-industry analysis cannot be offered to a one-industry workspace."""
    token = await _token(db_session, test_tenant_id, "fashion")
    r = await client.get(
        "/api/v1/alerts/cross-industry", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 404
