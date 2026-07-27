from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.config import get_settings
from app.core.exceptions import AuthenticationError, IndustryNotEnabledError
from app.core.firebase_auth import get_verifier
from app.core.rbac import require_admin
from app.models.enums import IndustryCode
from app.models.industry import IndustryProfile
from app.models.tenant import Tenant, User
from app.schemas.industry import (
    EffectiveIndustryConfigOut,
    FocusProfileIn,
    IndustryActivateIn,
    IndustryProfileUpdate,
)
from app.services.industry_config import (
    EffectiveIndustryConfig,
    merge_focus_into_flags,
    resolve_effective_config,
)
from app.services.industry_context import INDUSTRY_REGISTRY, IndustryContext, get_industry_context

log = structlog.get_logger(__name__)

router = APIRouter(tags=["industry"])


def require_auth(request: Request) -> None:
    if request.state.tenant_id is None:
        raise AuthenticationError()


def get_active_industry(request: Request) -> IndustryContext:
    """FastAPI dependency: resolve IndustryContext for the current request.

    Uses request.state.industry_code set by TenantContextMiddleware.
    Raises if the code is unrecognized or not licensed by the tenant.
    """
    require_auth(request)
    code = request.state.industry_code
    if code is None:
        raise AuthenticationError("Industry context missing from token")
    try:
        ctx = get_industry_context(code)
    except ValueError:
        raise IndustryNotEnabledError(code)
    return ctx


def get_tenant_id(request: Request) -> uuid.UUID:
    require_auth(request)
    return request.state.tenant_id


def get_user_id(request: Request) -> uuid.UUID:
    require_auth(request)
    return request.state.user_id


ActiveIndustry = Annotated[IndustryContext, Depends(get_active_industry)]
TenantId = Annotated[uuid.UUID, Depends(get_tenant_id)]
UserId = Annotated[uuid.UUID, Depends(get_user_id)]


@router.get("/industry/context")
async def current_industry_context(ctx: ActiveIndustry) -> dict:
    """Return the resolved industry configuration for the active workspace."""
    return {
        "code": ctx.code,
        "display_name": ctx.display_name,
        "default_horizon_weeks": ctx.default_horizon_weeks,
        "granularity_dimensions": ctx.granularity_dimensions,
        "required_signal_types": ctx.required_signal_types,
        "forecast_models": ctx.forecast_models,
        "optimization_models": ctx.optimization_models,
        "audit_level": ctx.audit_level,
        "is_gxp": ctx.is_gxp,
    }


@router.get("/industry/available")
async def list_available_industries() -> dict:
    """Return all industries known to the platform."""
    return {
        code: {
            "display_name": ctx.display_name,
            "default_horizon_weeks": ctx.default_horizon_weeks,
            "audit_level": ctx.audit_level,
        }
        for code, ctx in INDUSTRY_REGISTRY.items()
    }


def _to_effective_out(config: EffectiveIndustryConfig) -> EffectiveIndustryConfigOut:
    return EffectiveIndustryConfigOut(
        code=config.code,
        display_name=config.base.display_name,
        effective_horizon=config.effective_horizon,
        active_signal_types=list(config.active_signal_types),
        focus=FocusProfileIn(
            keywords=list(config.focus.keywords),
            categories=list(config.focus.categories),
        ),
        feature_flags=config.feature_flags,
    )


@router.get("/industry/profile", response_model=EffectiveIndustryConfigOut)
async def get_industry_profile(
    request: Request, ctx: ActiveIndustry, tenant_id: TenantId
) -> EffectiveIndustryConfigOut:
    """Return the tenant's effective config for the active industry — archetype
    defaults merged with their IndustryProfile overrides and focus watchlist."""
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        config = await resolve_effective_config(session, tenant_id, ctx.code)
    return _to_effective_out(config)


@router.put("/industry/profile", response_model=EffectiveIndustryConfigOut)
async def update_industry_profile(
    body: IndustryProfileUpdate,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
) -> EffectiveIndustryConfigOut:
    """Upsert the tenant's focus profile for the active industry.

    Omitted fields are left unchanged. The focus watchlist is merged into
    ``feature_flags['focus']`` without disturbing other flags.
    """
    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    async with db.session(str(tenant_id)) as session:
        profile = await session.scalar(
            select(IndustryProfile).where(
                IndustryProfile.tenant_id == tenant_id,
                IndustryProfile.industry == industry,
            )
        )
        if profile is None:
            profile = IndustryProfile(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                industry=industry,
                custom_signal_types=[],
                model_overrides={},
                feature_flags={},
            )
            session.add(profile)

        if body.custom_horizon_weeks is not None:
            profile.custom_horizon_weeks = body.custom_horizon_weeks
        if body.custom_signal_types is not None:
            profile.custom_signal_types = list(body.custom_signal_types)
        if body.focus is not None:
            profile.feature_flags = merge_focus_into_flags(
                profile.feature_flags, body.focus.keywords, body.focus.categories
            )

        await session.flush()
        config = await resolve_effective_config(session, tenant_id, ctx.code)
    return _to_effective_out(config)


@router.post("/industry/activate")
async def activate_industry(
    body: IndustryActivateIn,
    request: Request,
    tenant_id: TenantId,
    user_id: UserId,
    _rbac: None = require_admin,
) -> dict:
    """Set the tenant's primary industry (used by onboarding's first step).

    Validates the code against the tenant's licensed industries, then updates
    both ``Tenant.active_industry`` and the calling ``User.active_industry``.

    Returns a re-minted access token carrying the new ``ind`` claim
    (dev-fallback mode only — see below).

    Why re-mint here
    ----------------
    ``ind`` is baked into the token at login and read straight off the claim by
    ``TenantContextMiddleware`` (``middleware/tenant_context.py:107``). Choosing
    an industry during onboarding wrote the database but left the claim alone,
    so for the remainder of that session every request that did *not* carry an
    ``X-Industry-Code`` override was served the signup default — for a pharma
    tenant that means a 26-week horizon, fashion signals, and **standard audit
    level**, while the header renders ``GXP · 21 CFR PART 11``
    (docs/audit/02 P0-4, narrowed by 04). The first session is when a tenant
    runs their baseline forecast, so the window is small and badly placed.

    Re-minting was chosen over resolving ``ind`` from the database on every
    request for three reasons:

    * the deny-by-default ``X-Industry-Code`` validation
      (``tenant_context.py:114-138``) is built on the token being authoritative
      for both ``ind`` and ``industries``; making one of them DB-derived and
      the other claim-derived splits the trust model of a control that
      currently works;
    * a per-request lookup adds a database round-trip to the hot path that the
      claim design exists specifically to avoid;
    * industry changes are rare and funnel through this one endpoint, so the
      staleness window is enumerable rather than open-ended.

    The trade-off: any *other* future writer of ``active_industry`` must
    re-mint too, or reintroduce the bug. If industry ever becomes mutable from
    several places, switch to DB resolution and accept the round-trip.

    Firebase mode is unchanged and still stale: ``ind`` is a custom claim set
    at provisioning, so the equivalent fix is ``set_custom_user_claims`` plus a
    client-side ``getIdToken(true)``. Not implemented here because there is no
    Firebase project configured to verify it against — tracked in
    docs/audit/00-open-questions.md.
    """
    code = body.code.value if hasattr(body.code, "value") else str(body.code)
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise AuthenticationError()
        licensed = [i.value if hasattr(i, "value") else str(i) for i in tenant.industries]
        if code not in licensed:
            raise IndustryNotEnabledError(code)

        tenant.active_industry = body.code
        user = await session.get(User, user_id)
        if user is not None:
            user.active_industry = body.code
        await session.flush()

        industries = [i.value if hasattr(i, "value") else str(i) for i in tenant.industries]
        user_email = user.email if user is not None else None
        user_role = user.role.value if user is not None else None

    result: dict = {"active_industry": code}

    # Dev-fallback only. In Firebase mode the SDK owns the token and
    # mint_dev_token refuses to run, so the claim stays stale until the
    # provisioning claims are updated — see the docstring.
    settings = get_settings()
    if not settings.firebase_enabled and user_role is not None:
        token, expires_in = get_verifier().mint_dev_token(
            uid=str(user_id),
            puid=str(user_id),
            email=user_email,
            tid=str(tenant_id),
            role=user_role,
            ind=code,
            industries=industries,
        )
        result["access_token"] = token
        result["expires_in"] = expires_in

    log.info(
        "industry.activated",
        tenant_id=str(tenant_id),
        code=code,
        token_reissued="access_token" in result,
    )
    return result
