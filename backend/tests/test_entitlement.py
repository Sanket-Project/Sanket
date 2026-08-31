"""Server-side entitlement: the paywall must live in the API, not in React.

docs/audit/02 P0-1. With no subscription row at all, /products, /skus,
/inventory/levels, /signals, /alerts, /webhooks/endpoints and
/financial/impact all returned 200. The gate was SubscriptionGate.tsx, a React
component with nothing behind it, so anyone reading the network tab used the
product for free and a churned tenant kept full access.

These tests drive real HTTP with a real token against a real database, because
the claim being made is about the API surface, not about a function.

Note the tenants seeded here carry ``tier='enterprise'`` and
``status='active'`` on the ``tenants`` row while holding no live subscription.
That is deliberate: it pins that entitlement reads ``subscriptions`` and not
``tenants.tier``, which in production is hardcoded to 'growth' at signup and
never updated.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import hash_password
from app.models.enums import UserRole

pytestmark = pytest.mark.asyncio

PASSWORD = "EntitleTest!2026x"

# Every endpoint docs/audit/02 P0-1 observed returning 200 while unsubscribed.
GATED_ENDPOINTS = [
    "/api/v1/products",
    "/api/v1/skus",
    "/api/v1/inventory/levels",
    "/api/v1/signals",
    "/api/v1/alerts",
    "/api/v1/webhooks/endpoints",
    "/api/v1/financial/impact",
]


async def _seed_tenant(db: AsyncSession, slug: str) -> uuid.UUID:
    row = (
        await db.execute(text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": slug})
    ).fetchone()
    if row:
        return row[0]
    tid = uuid.uuid4()
    await db.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status,
                                 industry, max_users)
            VALUES (:id, :slug, :display_name, 'enterprise', 'active',
                    'fashion', 100)
            """
        ),
        {"id": str(tid), "slug": slug, "display_name": slug},
    )
    await db.commit()
    return tid


async def _seed_owner(db: AsyncSession, tenant_id: uuid.UUID, email: str) -> None:
    await db.execute(
        text(
            """
            INSERT INTO users (id, tenant_id, email, password_hash, full_name,
                               role, active_industry, is_active)
            VALUES (:id, :tid, :email, :hash, 'Entitlement Test',
                    :role, 'fashion', TRUE)
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "tid": str(tenant_id),
            "email": email,
            "hash": hash_password(PASSWORD, get_settings()),
            "role": UserRole.owner.value,
        },
    )
    await db.commit()


async def _set_subscription(
    db: AsyncSession, tenant_id: uuid.UUID, *, status: str, days_left: int
) -> None:
    """Give the tenant exactly one subscription in the given state."""
    await db.execute(
        text("DELETE FROM subscriptions WHERE tenant_id = :tid"), {"tid": str(tenant_id)}
    )
    now = datetime.now(tz=UTC)
    await db.execute(
        text(
            """
            INSERT INTO subscriptions (id, tenant_id, plan_id, status,
                                       current_period_start, current_period_end,
                                       cancel_at_period_end, metadata)
            VALUES (:id, :tid, 'growth_monthly', CAST(:status AS subscription_status),
                    :start, :end, FALSE, '{}'::jsonb)
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "tid": str(tenant_id),
            "status": status,
            "start": now - timedelta(days=30),
            "end": now + timedelta(days=days_left),
        },
    )
    await db.commit()


async def _clear_subscriptions(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    await db.execute(
        text("DELETE FROM subscriptions WHERE tenant_id = :tid"), {"tid": str(tenant_id)}
    )
    await db.commit()


async def _token(client: AsyncClient, email: str, slug: str) -> str:
    r = await client.post(
        "/api/v1/auth/dev-login",
        json={"email": email, "password": PASSWORD, "tenant_slug": slug},
    )
    assert r.status_code == 200, f"login failed: {r.text}"
    return r.json()["access_token"]


@pytest.fixture
async def entitled_tenant(db_session: AsyncSession, client: AsyncClient):
    """A tenant + owner + bearer token, with the subscription left to each test."""
    slug = f"ent-{uuid.uuid4().hex[:10]}"
    email = f"{slug}@example.com"
    tenant_id = await _seed_tenant(db_session, slug)
    await _seed_owner(db_session, tenant_id, email)
    token = await _token(client, email, slug)
    return tenant_id, {"Authorization": f"Bearer {token}"}


# ── Denial ────────────────────────────────────────────────────────────────────


async def test_no_subscription_at_all_denies_every_tenant_data_endpoint(
    db_session, client, entitled_tenant
):
    """The exact sweep from docs/audit/02 P0-1, which returned 200 across the board."""
    tenant_id, headers = entitled_tenant
    await _clear_subscriptions(db_session, tenant_id)

    for path in GATED_ENDPOINTS:
        r = await client.get(path, headers=headers)
        assert r.status_code == 402, f"{path} returned {r.status_code}, expected 402"


@pytest.mark.parametrize(
    ("status", "days_left", "why"),
    [
        ("cancelled", 30, "cancelled mid-period must lose access immediately"),
        ("past_due", 30, "a failed payment is exactly when access should stop"),
        ("incomplete", 30, "an abandoned checkout never granted anything"),
        ("paused", 30, "a paused mandate is not a live subscription"),
        ("active", -1, "status alone is not enough — the period has elapsed"),
        ("trialing", -1, "an expired trial must not keep the workspace open"),
    ],
)
async def test_dead_subscription_states_are_denied(
    db_session, client, entitled_tenant, status, days_left, why
):
    tenant_id, headers = entitled_tenant
    await _set_subscription(db_session, tenant_id, status=status, days_left=days_left)

    r = await client.get("/api/v1/products", headers=headers)
    assert r.status_code == 402, f"{why} (status={status}, days_left={days_left})"


async def test_expired_active_subscription_is_denied_across_the_whole_sweep(
    db_session, client, entitled_tenant
):
    """A row stuck at `active` with an elapsed period is what a missed webhook leaves behind."""
    tenant_id, headers = entitled_tenant
    await _set_subscription(db_session, tenant_id, status="active", days_left=-5)

    for path in GATED_ENDPOINTS:
        r = await client.get(path, headers=headers)
        assert r.status_code == 402, f"{path} returned {r.status_code}, expected 402"


# ── Access ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["active", "trialing"])
async def test_live_subscription_grants_access(db_session, client, entitled_tenant, status):
    """Positive control. Without this the suite would pass by denying everything."""
    tenant_id, headers = entitled_tenant
    await _set_subscription(db_session, tenant_id, status=status, days_left=15)

    r = await client.get("/api/v1/products", headers=headers)
    assert r.status_code == 200, f"{status} subscription was denied: {r.text}"


async def test_trial_still_running_is_not_denied(db_session, client, entitled_tenant):
    tenant_id, headers = entitled_tenant
    await _set_subscription(db_session, tenant_id, status="trialing", days_left=1)

    r = await client.get("/api/v1/products", headers=headers)
    assert r.status_code == 200


# ── The gate must not lock a tenant out of paying ─────────────────────────────


async def test_unsubscribed_tenant_can_still_reach_the_paths_needed_to_subscribe(
    db_session, client, entitled_tenant
):
    """Gating billing or onboarding behind a subscription is a deadlock.

    A tenant with no subscription has to be able to render the shell, finish
    setup, read the plans, and start a checkout. If any of these 402s, the
    product can never take money.
    """
    tenant_id, headers = entitled_tenant
    await _clear_subscriptions(db_session, tenant_id)

    for path in (
        "/api/v1/billing/plans",
        "/api/v1/billing/subscription",
        "/api/v1/billing/usage",
        "/api/v1/industry/profile",
        "/api/v1/industry/available",
        "/api/v1/onboarding/state",
        # Onboarding's calendar step reads and writes this before any purchase.
        "/api/v1/planning/config",
        # Onboarding's team step.
        "/api/v1/invites",
    ):
        r = await client.get(path, headers=headers)
        assert r.status_code != 402, f"{path} is gated and must not be — it blocks onboarding"


async def test_onboarding_file_upload_is_not_gated(db_session, client, entitled_tenant):
    """The wizard's data step runs outside the paywall, so upload must not 402.

    Posting nothing yields a 4xx from validation — the point is only that it is
    not 402. See entitlement._SETUP_PATHS for why these two are exempt.
    """
    tenant_id, headers = entitled_tenant
    await _clear_subscriptions(db_session, tenant_id)

    for path in ("/api/v1/integrations/upload/analyze", "/api/v1/integrations/upload"):
        r = await client.post(path, headers=headers)
        assert r.status_code != 402, f"{path} is gated and must not be — it blocks onboarding"


async def test_connectors_stay_gated_even_though_upload_is_not(db_session, client, entitled_tenant):
    """The exemption is exactly two upload paths, not the whole integrations hub.

    Connecting a live source and triggering a sync are product value and must
    still require payment — otherwise the upload carve-out becomes a hole.
    """
    tenant_id, headers = entitled_tenant
    await _clear_subscriptions(db_session, tenant_id)

    r = await client.get("/api/v1/integrations/catalog", headers=headers)
    assert r.status_code == 402

    r = await client.post("/api/v1/integrations/postgres/sync", headers=headers)
    assert r.status_code == 402


async def test_entitlement_denies_with_402_not_403(db_session, client, entitled_tenant):
    """402 routes the SPA to the paywall; 403 means a role problem and must not.

    Also pins that the body is a plain string the frontend can render, not a
    validation-error array.
    """
    tenant_id, headers = entitled_tenant
    await _clear_subscriptions(db_session, tenant_id)

    r = await client.get("/api/v1/products", headers=headers)
    assert r.status_code == 402
    assert r.status_code != 403
    assert isinstance(r.json()["detail"], str)


async def test_unauthenticated_still_401_not_402(client):
    """Entitlement must not mask an auth failure as a billing problem."""
    r = await client.get("/api/v1/products")
    assert r.status_code == 401
