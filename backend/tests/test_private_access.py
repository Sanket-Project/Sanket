"""Private application entry points must fail closed before touching a database."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.config import Settings
from app.routers.auth import google_signup, sandbox_session, signup
from app.schemas.auth import GoogleSignUpRequest, SignUpRequest


def private_settings():
    return Settings(_env_file=None, jwt_secret="private-access-unit-test-secret-2026")  # noqa: S106 — test secret


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["password", "google", "sandbox"])
async def test_public_account_entry_is_disabled_by_default(entry):
    settings = private_settings()
    request = Request({"type": "http", "app": SimpleNamespace(state=SimpleNamespace())})

    async def call_entry():
        if entry == "password":
            await signup(
                SignUpRequest(
                    name="Test",
                    email="test@example.com",
                    password="Sup3rSecret!",  # noqa: S106 — synthetic test credentials
                    tenant_slug="private-test",
                    industry="fashion",
                ),
                request,
                settings,
            )
        elif entry == "google":
            await google_signup(
                GoogleSignUpRequest(
                    id_token="unused",  # noqa: S106 — deliberately invalid test token
                    workspace_slug="private-test",
                    name="Test",
                    industry="fashion",
                ),
                request,
                settings,
            )
        else:
            await sandbox_session(request, settings)

    with pytest.raises(HTTPException) as error:
        await call_entry()
    assert error.value.status_code in (403, 404)


def test_public_signup_is_disabled_in_default_configuration():
    assert private_settings().public_signup_enabled is False


@pytest.mark.asyncio
async def test_unknown_identity_cannot_join_development_workspace(client, db_session, monkeypatch):
    import uuid

    from sqlalchemy import text

    from app.config import get_settings
    from app.routers import auth

    await db_session.execute(
        text(
            "INSERT INTO tenants (id,slug,display_name,tier,status,industry) VALUES (:id,'sanket-dev','Private development','growth','active','fashion') ON CONFLICT (slug) DO NOTHING"
        ),
        {"id": str(uuid.uuid4())},
    )
    await db_session.commit()
    monkeypatch.setattr(get_settings(), "public_signup_enabled", False)
    monkeypatch.setattr(
        auth,
        "get_verifier",
        lambda: SimpleNamespace(
            verify_identity=lambda token: {"uid": "uninvited", "email": "uninvited@example.com"}
        ),
    )
    response = await client.post(
        "/api/v1/auth/session", headers={"Authorization": "Bearer test-token"}
    )
    assert response.status_code == 401
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM users WHERE email='uninvited@example.com'")
        )
        == 0
    )
