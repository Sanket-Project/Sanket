from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.core.exceptions import AuthenticationError, IndustryNotEnabledError
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

    Note: the new industry takes effect on the next token refresh — the auth
    session handler re-syncs the stale ``ind`` claim. The SPA also applies the
    choice to its local industry store for immediate UI effect.
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

    log.info("industry.activated", tenant_id=str(tenant_id), code=code)
    return {"active_industry": code}
