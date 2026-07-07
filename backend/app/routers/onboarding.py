"""Onboarding readiness endpoints.

Reads/writes the setup wizard's progress, stored in ``Tenant.settings["onboarding"]``
(JSONB — no dedicated table). The session payload already carries this state for the
initial route guard; these endpoints let the wizard read it back and persist progress
step-by-step. Mutations require owner/admin.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Request

from app.core.exceptions import AuthenticationError
from app.core.rbac import require_admin
from app.models.tenant import Tenant
from app.routers.industry_router import TenantId
from app.schemas.onboarding import (
    OnboardingState,
    OnboardingStateUpdate,
    StepState,
    load_onboarding_state,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/state", response_model=OnboardingState)
async def get_state(request: Request, tenant_id: TenantId) -> OnboardingState:
    """Return the tenant's onboarding readiness (defaults to complete for tenants
    that predate the feature)."""
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise AuthenticationError()
        return load_onboarding_state(tenant.settings)


@router.put("/state", response_model=OnboardingState)
async def update_state(
    body: OnboardingStateUpdate,
    request: Request,
    tenant_id: TenantId,
    _rbac: None = require_admin,
) -> OnboardingState:
    """Apply a partial update to the wizard's progress and persist it.

    ``mark_step`` flips one step to done (stamping ``at``); ``step_meta`` merges
    small facts onto that step (or the current step if none named); ``status`` /
    ``current_step`` move the overall pointer. Setting ``status=complete`` stamps
    ``completed_at`` and parks ``current_step`` at ``done``.
    """
    now = datetime.now(tz=UTC)
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise AuthenticationError()

        state = load_onboarding_state(tenant.settings)
        # A legacy/implicit-complete tenant that starts editing becomes a real
        # in_progress record so subsequent reads round-trip correctly.
        if not tenant.settings or "onboarding" not in tenant.settings:
            state = OnboardingState(status="in_progress", current_step="industry", steps={})

        if body.mark_step:
            step = state.steps.get(body.mark_step) or StepState()
            step.done = True
            step.at = now
            if body.step_meta:
                step.meta = {**step.meta, **body.step_meta}
            state.steps[body.mark_step] = step
        elif body.step_meta and state.current_step != "done":
            step = state.steps.get(state.current_step) or StepState()
            step.meta = {**step.meta, **body.step_meta}
            state.steps[state.current_step] = step

        if body.current_step:
            state.current_step = body.current_step
        if body.status:
            state.status = body.status
            if body.status == "complete":
                state.completed_at = now
                state.current_step = "done"

        # Reassign the JSONB column so SQLAlchemy flushes the change.
        settings = dict(tenant.settings or {})
        settings["onboarding"] = state.model_dump(mode="json")
        tenant.settings = settings
        await session.flush()

    log.info(
        "onboarding.state.updated",
        tenant_id=str(tenant_id),
        status=state.status,
        current_step=state.current_step,
    )
    return state
