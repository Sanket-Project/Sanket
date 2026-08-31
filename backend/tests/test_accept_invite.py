"""Redeeming an invitation.

``POST /invites`` has always minted a link to ``/accept-invite?token=...`` and
nothing has ever redeemed it -- ``routers/invites.py`` says acceptance is "a
separate, authenticated flow (out of scope for this endpoint set)", and that
flow was never built. So "members inherit the workspace's industry" had nothing
to exercise it.

Everything that decides privilege -- which workspace, which role, which
industry -- comes from the invite row an owner created. None of it is accepted
from the request.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _owner_token(client: AsyncClient, slug: str, industry: str) -> str:
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


async def _invite(client: AsyncClient, token: str, email: str, role: str) -> str:
    created = await client.post(
        "/api/v1/invites",
        json={"email": email, "role": role},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 201, created.text
    return created.json()["invite_url"].split("token=")[1]


async def test_an_inviter_cannot_choose_an_industry() -> None:
    """There is no field to place a teammate in a different industry."""
    from app.schemas.invite import InviteCreate

    assert "industry" not in InviteCreate.model_fields


async def test_accepted_invite_inherits_the_workspace_industry(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = await _owner_token(client, "invite-pharma", "pharma")
    raw = await _invite(client, owner, "teammate@invite.example.com", "analyst")

    r = await client.post(
        "/api/v1/auth/accept-invite",
        json={
            "token": raw,
            "name": "Team Mate",
            "password": "An0therSecret!",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["active_industry"] == "pharma", "members inherit, never choose"
    assert body["role"] == "analyst"

    active = await db_session.scalar(
        text(
            "SELECT active_industry::text FROM users "
            "WHERE email = 'teammate@invite.example.com'"
        )
    )
    assert active == "pharma"


async def test_accepted_member_can_sign_in_and_gets_the_same_industry(
    client: AsyncClient
) -> None:
    """The invitee ends up with a working account, not just a row."""
    owner = await _owner_token(client, "invite-signin", "hardware")
    raw = await _invite(client, owner, "signin@invite.example.com", "viewer")
    await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": raw, "name": "Sign In", "password": "An0therSecret!"},
    )

    login = await client.post(
        "/api/v1/auth/dev-login",
        json={
            "email": "signin@invite.example.com",
            "password": "An0therSecret!",
            "tenant_slug": "invite-signin",
        },
    )
    assert login.status_code == 200, login.text
    assert login.json()["active_industry"] == "hardware"
    assert login.json()["role"] == "viewer"


async def test_cannot_redeem_an_invite_for_someone_who_already_has_an_account(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Account takeover guard.

    Redemption provisions Firebase credentials with ``reset_password=True``,
    which overwrites an existing Firebase user's password. Combined with a
    duplicate check scoped to the *invite's* tenant, that gave anyone a working
    primitive against any address on the platform: sign up for a free
    workspace, invite victim@corp.com, read the raw token out of your own
    invite response, and redeem it with a password of your choosing.

    So the check is global, exactly as ``/auth/signup`` has always been. One
    identity maps to at most one SANKET user anyway -- ``users.firebase_uid`` is
    globally unique -- so an address that already has an account cannot be
    adopted into a second workspace regardless.
    """
    # The victim already has an account in their own workspace.
    await _owner_token(client, "victim-co", "pharma")
    victim_email = "owner@victim-co.example.com"

    # The attacker owns an unrelated workspace and invites the victim to it.
    attacker = await _owner_token(client, "attacker-co", "fashion")
    raw = await _invite(client, attacker, victim_email, "viewer")

    r = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": raw, "name": "Not The Victim", "password": "Att4ckerPass!"},
    )
    assert r.status_code == 409, r.text

    # The victim's own account is untouched and still signs in.
    login = await client.post(
        "/api/v1/auth/dev-login",
        json={
            "email": victim_email,
            "password": "Sup3rSecret!",
            "tenant_slug": "victim-co",
        },
    )
    assert login.status_code == 200, login.text
    assert login.json()["active_industry"] == "pharma"


async def test_invite_token_is_single_use(client: AsyncClient) -> None:
    owner = await _owner_token(client, "invite-once", "fashion")
    raw = await _invite(client, owner, "once@invite.example.com", "viewer")
    body = {"token": raw, "name": "Once", "password": "An0therSecret!"}

    first = await client.post("/api/v1/auth/accept-invite", json=body)
    assert first.status_code == 201, first.text

    second = await client.post("/api/v1/auth/accept-invite", json=body)
    assert second.status_code == 404, "a redeemed invite must not work twice"


async def test_unknown_invite_token_is_rejected(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/accept-invite",
        json={
            "token": "not-a-real-token-but-long-enough",
            "name": "Nobody",
            "password": "An0therSecret!",
        },
    )
    assert r.status_code == 404


async def test_expired_invite_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = await _owner_token(client, "invite-expired", "fashion")
    raw = await _invite(client, owner, "expired@invite.example.com", "viewer")
    await db_session.execute(
        text(
            "UPDATE invites SET expires_at = now() - interval '1 day' "
            "WHERE email = 'expired@invite.example.com'"
        )
    )
    await db_session.commit()

    r = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": raw, "name": "Late", "password": "An0therSecret!"},
    )
    assert r.status_code == 404


async def test_revoked_invite_is_rejected(client: AsyncClient) -> None:
    owner = await _owner_token(client, "invite-revoked", "fashion")
    created = await client.post(
        "/api/v1/invites",
        json={"email": "revoked@invite.example.com", "role": "viewer"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    raw = created.json()["invite_url"].split("token=")[1]
    invite_id = created.json()["id"]

    revoked = await client.delete(
        f"/api/v1/invites/{invite_id}", headers={"Authorization": f"Bearer {owner}"}
    )
    assert revoked.status_code == 200, revoked.text

    r = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": raw, "name": "Revoked", "password": "An0therSecret!"},
    )
    assert r.status_code == 404


async def test_acceptance_rejects_a_body_trying_to_pick_a_role(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Extra fields are refused outright, not quietly dropped.

    Ignoring them would also be safe, but it makes the guarantee rest on a
    Pydantic default staying put. Refusing says so out loud.
    """
    owner = await _owner_token(client, "invite-noesc", "fashion")
    raw = await _invite(client, owner, "noesc@invite.example.com", "viewer")

    r = await client.post(
        "/api/v1/auth/accept-invite",
        json={
            "token": raw,
            "name": "Sneaky",
            "password": "An0therSecret!",
            "role": "owner",
            "industry": "pharma",
        },
    )
    assert r.status_code == 422, r.text

    # And nothing was created on the way to that refusal.
    created = await db_session.scalar(
        text("SELECT count(*) FROM users WHERE email = 'noesc@invite.example.com'")
    )
    assert created == 0


async def test_acceptance_takes_role_and_industry_from_the_invite(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A well-formed redemption gets exactly what the inviter chose."""
    owner = await _owner_token(client, "invite-fromrow", "fashion")
    raw = await _invite(client, owner, "fromrow@invite.example.com", "viewer")

    r = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": raw, "name": "Legit", "password": "An0therSecret!"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "viewer"
    assert r.json()["active_industry"] == "fashion"

    row = await db_session.execute(
        text(
            "SELECT role::text, active_industry::text FROM users "
            "WHERE email = 'fromrow@invite.example.com'"
        )
    )
    role, industry = row.one()
    assert role == "viewer"
    assert industry == "fashion"


async def test_acceptance_respects_the_seat_limit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Seats are re-checked at redemption, not only when the invite is made."""
    owner = await _owner_token(client, "invite-seats", "fashion")
    raw = await _invite(client, owner, "seat@invite.example.com", "viewer")
    await db_session.execute(
        text("UPDATE tenants SET max_users = 1 WHERE slug = 'invite-seats'")
    )
    await db_session.commit()

    r = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": raw, "name": "No Seat", "password": "An0therSecret!"},
    )
    assert r.status_code == 409, r.text
