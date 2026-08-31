from __future__ import annotations

import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, text
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    IndustryNotEnabledError,
)
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
from app.schemas.onboarding import load_onboarding_state
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


@router.get("/industry/catalog")
async def industry_catalog() -> dict:
    """Every industry SANKET supports. Public.

    Public because the signup form needs the canonical list before the caller
    has a token, and because prospects may legitimately browse every vertical.
    It replaces an authenticated ``/industry/available``, which enumerated all
    five to someone already inside a workspace -- a list they cannot act on and
    should not be shown, since they have exactly one industry.

    The list comes from the backend registry, so a frontend picker cannot drift
    from the codes the API will actually accept.
    """
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


# Tables whose emptiness defines "this workspace holds no real data yet".
# Data locks the industry because it was ingested and interpreted under the old
# one; silently re-reading a fashion catalogue as pharma inventory would be
# worse than refusing the change.
_DATA_TABLES: tuple[str, ...] = (
    "products",
    "skus",
    "historical_sales",
    "integration_connections",
)


async def _lock_reason(session: Any, tenant: Tenant) -> str | None:
    """Why this workspace's industry can no longer change, or None if it can.

    Read from the database, never from a token claim. A claim describes what was
    true when it was minted, and lock state is precisely the thing that changes
    underneath it -- so trusting one here would let a stale session edit a
    workspace that has since been locked by someone else.
    """
    if load_onboarding_state(tenant.settings).status == "complete":
        return "setup is already complete"
    for table in _DATA_TABLES:
        exists = await session.scalar(
            text(f"SELECT 1 FROM {table} WHERE tenant_id = :tid LIMIT 1"),  # noqa: S608
            {"tid": str(tenant.id)},
        )
        if exists:
            return "this workspace already holds data"
    return None


@router.post("/industry/activate")
async def activate_industry(
    body: IndustryActivateIn,
    request: Request,
    tenant_id: TenantId,
    user_id: UserId,
    _rbac: None = require_admin,
) -> dict:
    """Correct the workspace's industry during initial setup.

    This is no longer a switch. A workspace is scoped to one industry, and this
    endpoint exists only so an owner who picked the wrong one at signup can fix
    it before the choice starts mattering. It closes for good once setup
    completes or real data arrives (:func:`_lock_reason`), and returns 409 after
    that -- a later change needs a deliberate, support-assisted migration, not
    an API call that silently reinterprets existing data.

    Re-minting the token
    --------------------
    ``ind`` is baked into the bearer at login and read straight off the claim by
    ``TenantContextMiddleware``. Writing the database without reissuing the
    token left the rest of the session running on the old industry -- for a
    pharma tenant that meant a 26-week horizon, fashion signals and standard
    audit level behind a header rendering "GXP - 21 CFR PART 11"
    (docs/audit/02 P0-4). The first session is when a tenant runs their baseline
    forecast, so the window was small and badly placed.

    Because this is now the *only* writer of ``tenants.industry``, the staleness
    window is closed rather than merely narrow: dev mode gets a re-minted
    bearer, and Firebase mode gets fresh custom claims plus a refresh-token
    revocation, so the superseded ``ind`` cannot be replayed for the remaining
    hour of the old ID token's life.
    """
    code = body.code.value if hasattr(body.code, "value") else str(body.code)
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise AuthenticationError()

        locked = await _lock_reason(session, tenant)
        if locked is not None:
            raise ConflictError(
                f"This workspace is set to {tenant.industry.value} and cannot be "
                f"changed because {locked}. Contact support to migrate."
            )

        tenant.industry = body.code
        user = await session.get(User, user_id)
        await session.flush()

        user_email = user.email if user is not None else None
        user_role = user.role.value if user is not None else None
        firebase_uid = user.firebase_uid if user is not None else None

    result: dict = {"active_industry": code}

    settings = get_settings()
    if settings.firebase_enabled:
        if firebase_uid and user_role is not None:
            await run_in_threadpool(
                get_verifier().set_user_claims,
                firebase_uid,
                puid=str(user_id),
                tid=str(tenant_id),
                role=user_role,
                ind=code,
            )
            # The already-issued ID token keeps the previous `ind` for up to an
            # hour. Revoke so the superseded industry cannot be replayed; the
            # client signs in again and picks up the corrected claim.
            await run_in_threadpool(get_verifier().revoke_refresh_tokens, firebase_uid)
            result["reauth_required"] = True
    elif user_role is not None:
        token, expires_in = get_verifier().mint_dev_token(
            uid=str(user_id),
            puid=str(user_id),
            email=user_email,
            tid=str(tenant_id),
            role=user_role,
            ind=code,
        )
        result["access_token"] = token
        result["expires_in"] = expires_in

    log.info(
        "industry.corrected",
        tenant_id=str(tenant_id),
        code=code,
        token_reissued="access_token" in result,
    )
    return result
