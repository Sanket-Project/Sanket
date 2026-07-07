"""Planning calendar & rules endpoints.

Reads/writes ``Tenant.settings["planning"]`` (JSONB). Used by onboarding's
calendar step and the planning settings panel. Mutations require owner/admin.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request

from app.core.exceptions import AuthenticationError
from app.core.rbac import require_admin
from app.models.tenant import Tenant
from app.routers.industry_router import TenantId
from app.schemas.planning import (
    PlanningConfig,
    PlanningConfigUpdate,
    load_planning_config,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/planning", tags=["planning"])


@router.get("/config", response_model=PlanningConfig)
async def get_config(request: Request, tenant_id: TenantId) -> PlanningConfig:
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise AuthenticationError()
        return load_planning_config(tenant.settings)


@router.put("/config", response_model=PlanningConfig)
async def update_config(
    body: PlanningConfigUpdate,
    request: Request,
    tenant_id: TenantId,
    _rbac: None = require_admin,
) -> PlanningConfig:
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise AuthenticationError()

        config = load_planning_config(tenant.settings)
        if body.calendar is not None:
            config.calendar = body.calendar
        if body.rules is not None:
            config.rules = body.rules

        settings = dict(tenant.settings or {})
        settings["planning"] = config.model_dump(mode="json")
        tenant.settings = settings
        await session.flush()

    log.info("planning.config.updated", tenant_id=str(tenant_id))
    return config
