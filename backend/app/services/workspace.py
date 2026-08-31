"""Workspace (tenant) creation.

One path, shared by every self-service signup flow. Both ``/auth/signup`` and
``/auth/google-signup`` previously carried their own sixty-line copy of this
logic -- including the identical five-industry grant and an identical inline
feature-flag table -- so a change to one silently missed the other. That is how
the Google path kept granting every vertical after anyone thought about the
password path.

A workspace is created with exactly one industry. There is no argument here
that can produce more than one.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import IndustryCode, TenantStatus, TenantTier
from app.models.industry import IndustryProfile
from app.models.tenant import Tenant
from app.schemas.onboarding import default_onboarding_state

INDUSTRY_FEATURE_FLAGS: dict[str, dict[str, bool]] = {
    "fashion": {"markdown_optimizer": True, "assortment_planning": True},
    "electronics": {"component_risk": True, "competitor_tracking": True},
    "pharma": {"gxp_mode": True, "shortage_alerts": True, "batch_tracking": True},
    "agrocenter": {
        "seasonal_replenishment": True,
        "weather_signals": True,
        "input_coverage": True,
    },
    "hardware": {
        "supply_risk": True,
        "competitor_tracking": True,
        "safety_stock_optimizer": True,
    },
}

DEFAULT_MAX_SKUS = 10000
DEFAULT_MAX_USERS = 5
DEFAULT_RETENTION_DAYS = 730


async def create_tenant(
    session: AsyncSession,
    *,
    slug: str,
    display_name: str,
    industry: IndustryCode,
) -> Tenant:
    """Create a workspace scoped to one industry, plus that industry's profile.

    The caller must already have rejected a duplicate slug: self-service signup
    must never be a way into an existing workspace.

    Only the chosen industry gets a profile. Seeding all five was what made a
    fresh workspace look entitled to every vertical.
    """
    tenant = Tenant(
        id=uuid.uuid4(),
        slug=slug,
        display_name=display_name,
        tier=TenantTier.growth,
        status=TenantStatus.trial,
        industry=industry,
        max_skus=DEFAULT_MAX_SKUS,
        max_users=DEFAULT_MAX_USERS,
        data_retention_days=DEFAULT_RETENTION_DAYS,
        # Seed setup readiness so the SPA routes the first user into the
        # onboarding wizard. Legacy tenants (no key) stay implicitly done.
        settings={"onboarding": default_onboarding_state().model_dump(mode="json")},
    )
    session.add(tenant)
    await session.flush()

    session.add(
        IndustryProfile(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            industry=industry,
            custom_horizon_weeks=None,
            custom_signal_types=[],
            model_overrides={},
            feature_flags=INDUSTRY_FEATURE_FLAGS.get(industry.value, {}),
        )
    )
    await session.flush()
    return tenant
