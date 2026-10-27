"""Authenticated settings; business-data endpoints are registered behind entitlement."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StrictBool
from pydantic import Field

from app.routers.industry_router import ActiveIndustry, TenantId, UserId
from app.services.llm.errors import AIError
from app.services.llm.policy import AIContext, PolicyStore, Sharing

settings_router = APIRouter(prefix="/ai", tags=["ai"])
router = APIRouter(prefix="/ai", tags=["ai"])


class SummaryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: UUID | None = None
    run_id: UUID | None = None
    connector: str | None = Field(default=None, max_length=80)
    language: Literal["en", "hi", "te", "ta"] = "en"


class CleanupBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku_ids: list[UUID] = Field(min_length=1, max_length=40)


class CleanupChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku_id: UUID
    field: Literal["category", "size", "color", "material", "season", "gender"]
    value: str = Field(min_length=1, max_length=100)
    revision: str = Field(min_length=1, max_length=100)


class CleanupConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changes: list[CleanupChange] = Field(min_length=1, max_length=160)
    confirm: StrictBool = False


class QualityFixBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["dedupe_sales", "drop_future_sales", "drop_negative_sales"]
    confirm: StrictBool = False
    preview_token: str | None = Field(default=None, max_length=4000)


@router.post("/data-quality/fix")
async def quality_fix(body: QualityFixBody, request: Request, tenant_id: TenantId, user_id: UserId, industry: ActiveIndustry):
    from app.config import get_settings
    from app.models.enums import IndustryCode
    from app.services.llm.quality_review import preview_fix, confirm_fix
    ctx = AIContext(tenant_id, user_id, IndustryCode(industry.code), task_name="data_quality")
    try:
        if body.confirm:
            if not body.preview_token:
                raise ValueError("Preview the affected records before confirming")
            return await confirm_fix(request.app.state.db, ctx, get_settings().jwt_secret, body.action, body.preview_token)
        return await preview_fix(request.app.state.db, ctx, get_settings().jwt_secret, body.action)
    except AIError as exc:
        raise error_response(exc) from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post("/product-cleanup")
async def product_cleanup(body: CleanupBody, request: Request, tenant_id: TenantId, user_id: UserId, industry: ActiveIndustry):
    from app.models.enums import IndustryCode
    from app.services.llm.product_cleanup import suggest_cleanup
    ctx = AIContext(tenant_id, user_id, IndustryCode(industry.code), task_name="product_cleanup")
    try:
        return await suggest_cleanup(request.app.state.db, getattr(request.app.state, "ai", None), ctx, body.sku_ids)
    except AIError as exc:
        raise error_response(exc) from None
    except ValueError:
        raise HTTPException(status_code=400, detail="Products cannot be safely suggested; review them manually") from None


@router.post("/product-cleanup/confirm")
async def confirm_cleanup(body: CleanupConfirmation, request: Request, tenant_id: TenantId, user_id: UserId, industry: ActiveIndustry):
    from app.models.enums import IndustryCode
    from app.services.llm.product_cleanup import apply_cleanup
    ctx = AIContext(tenant_id, user_id, IndustryCode(industry.code), task_name="product_cleanup")
    try:
        return await apply_cleanup(request.app.state.db, ctx, [c.model_dump(mode="json") for c in body.changes], confirm=body.confirm)
    except AIError as exc:
        raise error_response(exc) from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


async def _summary(feature, body, request, tenant_id, user_id, industry):
    from app.models.enums import IndustryCode
    from app.services.llm.context import generate_summary
    ctx = AIContext(tenant_id, user_id, IndustryCode(industry.code), task_name=feature)
    try:
        return await generate_summary(request.app.state.db, getattr(request.app.state, "ai", None), ctx,
                                      entity_id=body.entity_id, connector=body.connector, language=body.language, run_id=body.run_id)
    except AIError as exc:
        raise error_response(exc) from None
    except ValueError:
        raise HTTPException(status_code=400, detail="Summary source is unavailable or invalid") from None


@settings_router.post("/summary/onboarding")
async def onboarding_summary(body: SummaryBody, request: Request, tenant_id: TenantId, user_id: UserId, industry: ActiveIndustry):
    return await _summary("onboarding", body, request, tenant_id, user_id, industry)


@router.post("/summary/{feature}")
async def business_summary(feature: Literal["data_quality", "decision_explanation", "alert_explanation", "planning_brief", "industry_advice"], body: SummaryBody, request: Request,
                           tenant_id: TenantId, user_id: UserId, industry: ActiveIndustry):
    return await _summary(feature, body, request, tenant_id, user_id, industry)


class AISettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool
    tasks: dict[str, StrictBool]
    sharing: Sharing
    aggregate_context: StrictBool = False
    product_names: StrictBool = False


class FormatChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    disabled: StrictBool | None = None


@settings_router.get("/import-formats")
async def import_formats(request: Request, tenant_id: TenantId, user_id: UserId, industry: ActiveIndustry):
    from app.models.enums import IndustryCode
    from app.services.integrations.import_profiles import list_profiles
    try:
        return await list_profiles(request.app.state.db, AIContext(tenant_id, user_id, IndustryCode(industry.code)))
    except (AIError, ValueError):
        raise HTTPException(status_code=403, detail="Only workspace owners and admins can manage saved formats") from None


@settings_router.post("/import-formats/{profile_id}")
async def change_import_format(profile_id: UUID, body: FormatChange, request: Request,
                                tenant_id: TenantId, user_id: UserId, industry: ActiveIndustry):
    from app.models.enums import IndustryCode
    from app.services.integrations.import_profiles import manage_profile
    try:
        await manage_profile(request.app.state.db, AIContext(tenant_id, user_id, IndustryCode(industry.code)), profile_id,
                             expected_revision=body.expected_revision, disabled=body.disabled)
        return {"updated": True}
    except (AIError, ValueError):
        raise HTTPException(status_code=409, detail="Saved format is unavailable or changed; refresh the list") from None


def error_response(exc):
    return HTTPException(status_code=403 if exc.code == "invalid_context" else 400, detail=exc.code)


@settings_router.get("/settings")
async def settings(request: Request, tenant_id: TenantId, user_id: UserId, industry: ActiveIndustry):
    from app.models.enums import IndustryCode
    ctx = AIContext(tenant_id, user_id, IndustryCode(industry.code))
    try:
        return await PolicyStore(request.app.state.db).describe(ctx)
    except AIError as exc:
        raise error_response(exc) from None


@settings_router.put("/settings")
async def update_settings(body: AISettingsBody, request: Request, tenant_id: TenantId, user_id: UserId, industry: ActiveIndustry):
    from app.models.enums import IndustryCode
    ctx = AIContext(tenant_id, user_id, IndustryCode(industry.code))
    store = PolicyStore(request.app.state.db)
    try:
        await store.configure(ctx, **body.model_dump())
        return await store.describe(ctx)
    except AIError as exc:
        raise error_response(exc) from None
