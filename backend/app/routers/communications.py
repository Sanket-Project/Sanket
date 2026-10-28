"""Personal language and opt-in recurring email preferences."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from app.config import get_settings
from app.routers.industry_router import ActiveIndustry, TenantId, UserId
from app.services.notifications.communications import read_preferences, write_preferences
from app.services.notifications.email import EmailConfig
from app.services.notifications.preferences import Preferences, next_delivery
from app.services.notifications.weekly import schedule_weekly

preferences_router = APIRouter(prefix="/communications", tags=["communications"])
router = APIRouter(prefix="/communications", tags=["communications"])


async def describe(request, tenant_id, user_id):
    prefs = await read_preferences(request.app.state.db, tenant_id, user_id)
    async with request.app.state.db.session(str(tenant_id)) as session:
        last = (
            (
                await session.execute(
                    text(
                        "SELECT state,updated_at FROM communication_deliveries WHERE tenant_id=:tid AND user_id=:uid AND delivery_key LIKE 'weekly:%' ORDER BY updated_at DESC LIMIT 1"
                    ),
                    {"tid": tenant_id, "uid": user_id},
                )
            )
            .mappings()
            .first()
        )
    return {
        "preferences": prefs.model_dump(),
        "next_delivery": next_delivery(
            datetime.now(UTC), prefs.timezone, prefs.send_hour
        ).isoformat()
        if prefs.weekly_enabled
        else None,
        "delivery_available": EmailConfig.from_settings(get_settings()).configured,
        "scheduling_available": getattr(request.app.state, "arq", None) is not None,
        "last_delivery": dict(last) if last else None,
    }


@preferences_router.get("/preferences")
async def get_preferences(request: Request, tenant_id: TenantId, user_id: UserId):
    try:
        return await describe(request, tenant_id, user_id)
    except ValueError as exc:
        raise HTTPException(403, str(exc)) from None


@preferences_router.put("/preferences")
async def save_preferences(
    body: Preferences,
    request: Request,
    tenant_id: TenantId,
    user_id: UserId,
    industry: ActiveIndustry,
):
    try:
        await write_preferences(request.app.state.db, tenant_id, user_id, body)
        await schedule_weekly(
            getattr(request.app.state, "arq", None), tenant_id, user_id, industry.code, body
        )
        return await describe(request, tenant_id, user_id)
    except ValueError as exc:
        raise HTTPException(403, str(exc)) from None


@router.post("/weekly/recover")
async def recover_weekly(
    request: Request, tenant_id: TenantId, user_id: UserId, industry: ActiveIndustry
):
    """Restore only the authenticated user's job. Never enumerate other tenants."""
    try:
        prefs = await read_preferences(request.app.state.db, tenant_id, user_id)
        due = await schedule_weekly(
            getattr(request.app.state, "arq", None), tenant_id, user_id, industry.code, prefs
        )
        return {"scheduled": due is not None, "next_delivery": due}
    except ValueError as exc:
        raise HTTPException(403, str(exc)) from None
