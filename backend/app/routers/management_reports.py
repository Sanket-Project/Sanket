"""Reviewable, snapshot-bound management artifacts and explicitly confirmed email."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator
from sqlalchemy import select

from app.config import get_settings
from app.models.enums import IndustryCode
from app.models.product import Sku
from app.models.recommendation import Recommendation
from app.routers.industry_router import ActiveIndustry, TenantId, UserId
from app.services import management_reports as reports
from app.services import roi
from app.services.notifications.communications import deliver_email, load_member, read_preferences
from app.services.notifications.email import EmailConfig, address

router = APIRouter(prefix="/management", tags=["management"])
Language = Literal["en", "hi", "te", "ta"]


class PreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    window_days: int = Field(default=90, ge=7, le=730)
    language: Language | None = None


class SupplierPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Language | None = None


class ReviewedEmail(PreviewBody):
    preview_token: str = Field(min_length=1, max_length=4000)
    recipient: str = Field(min_length=3, max_length=254)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=40000)
    delivery_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    confirm: StrictBool = False

    @field_validator("recipient")
    @classmethod
    def valid_recipient(cls, value):
        return address(value)

    @field_validator("subject")
    @classmethod
    def valid_subject(cls, value):
        if "\r" in value or "\n" in value:
            raise ValueError("Subject must be a single line")
        return value


def _token(tenant_id, user_id, purpose, snapshot, language, *, window_days=None, as_of=None):
    return jwt.encode(
        {
            "purpose": purpose,
            "tenant": str(tenant_id),
            "actor": str(user_id),
            "snapshot": snapshot,
            "language": language,
            "window_days": window_days,
            "as_of": as_of,
            "exp": datetime.now(UTC) + timedelta(minutes=10),
        },
        get_settings().jwt_secret,
        algorithm="HS256",
    )


def _verify(body, tenant_id, user_id, purpose):
    try:
        claims = jwt.decode(
            body.preview_token,
            get_settings().jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp"]},
        )
        expected = {"purpose": purpose, "tenant": str(tenant_id), "actor": str(user_id)}
        if not body.confirm or any(claims.get(k) != v for k, v in expected.items()):
            raise ValueError()
        return claims
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=409, detail="Review and confirm a fresh preview before sending"
        ) from None


async def current_report(db, tenant_id, user_id, industry, window_days):
    async with db.session(str(tenant_id)) as session:
        await _member(session, tenant_id, user_id)
        return reports.project_report(
            await roi.summary(
                session, tenant_id=tenant_id, industry=industry, window_days=window_days
            )
        )


async def _member(session, tenant_id, user_id):
    try:
        return await load_member(session, tenant_id, user_id)
    except ValueError:
        raise HTTPException(
            status_code=403, detail="Current workspace membership is required"
        ) from None


async def current_draft(db, tenant_id, user_id, industry, decision_id, language):
    async with db.session(str(tenant_id)) as session:
        await _member(session, tenant_id, user_id)
        return await _draft_in_session(session, tenant_id, industry, decision_id, language)


async def _draft_in_session(session, tenant_id, industry, decision_id, language):
    rec = await session.scalar(
        select(Recommendation)
        .where(
            Recommendation.id == decision_id,
            Recommendation.tenant_id == tenant_id,
            Recommendation.industry == IndustryCode(industry),
        )
        .with_for_update()
    )
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation is unavailable")
    sku_code = await session.scalar(
        select(Sku.sku_code)
        .where(
            Sku.id == rec.sku_id, Sku.tenant_id == tenant_id, Sku.industry == IndustryCode(industry)
        )
        .with_for_update()
    )
    if sku_code is None:
        raise HTTPException(status_code=404, detail="Recommendation SKU is unavailable")
    try:
        return reports.supplier_draft(rec, sku_code, language=language)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


async def _language(db, tenant_id, user_id, requested):
    try:
        return requested or (await read_preferences(db, tenant_id, user_id)).language
    except ValueError:
        raise HTTPException(
            status_code=403, detail="Current workspace membership is required"
        ) from None


@router.post("/roi/preview")
async def roi_preview(
    body: PreviewBody, request: Request, tenant_id: TenantId, user_id: UserId, ctx: ActiveIndustry
):
    language = await _language(request.app.state.db, tenant_id, user_id, body.language)
    report = await current_report(
        request.app.state.db, tenant_id, user_id, ctx.code, body.window_days
    )
    subject, text = reports.report_email(report, language=language)
    from app.services.llm.policy import AIContext

    summary = await reports.artifact_summary(
        request.app.state.db,
        getattr(request.app.state, "ai", None),
        AIContext(tenant_id, user_id, IndustryCode(ctx.code), task_name="roi_report"),
        report,
        language=language,
    )
    return {
        "report": report,
        "subject": subject,
        "body": text,
        "language": language,
        "summary": summary,
        "preview_token": _token(
            tenant_id,
            user_id,
            "roi_email",
            report["snapshot"],
            language,
            window_days=body.window_days,
            as_of=report["as_of"],
        ),
    }


@router.post("/roi/email")
async def roi_email(
    body: ReviewedEmail, request: Request, tenant_id: TenantId, user_id: UserId, ctx: ActiveIndustry
):
    claims = _verify(body, tenant_id, user_id, "roi_email")
    if (
        claims.get("window_days") != body.window_days
        or body.language
        and claims.get("language") != body.language
    ):
        raise HTTPException(status_code=409, detail="Report selection changed; review again")
    report = await current_report(
        request.app.state.db, tenant_id, user_id, ctx.code, body.window_days
    )
    if report["snapshot"] != claims.get("snapshot"):
        raise HTTPException(status_code=409, detail="Report source changed; review again")
    report["as_of"] = claims["as_of"]
    attachment = await asyncio.to_thread(
        reports.render_report_pdf, report, language=claims["language"]
    )

    async def eligibility(session, _user):
        latest = reports.project_report(
            await roi.summary(
                session, tenant_id=tenant_id, industry=ctx.code, window_days=body.window_days
            )
        )
        if latest["snapshot"] != claims.get("snapshot"):
            raise ValueError("Report source changed; review again")

    try:
        return await deliver_email(
            request.app.state.db,
            tenant_id,
            user_id,
            f"roi:{body.delivery_key}",
            body.recipient,
            body.subject,
            body.body,
            confirm=body.confirm,
            config=EmailConfig.from_settings(get_settings()),
            attachment=attachment,
            eligibility=eligibility,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post("/supplier/{decision_id}/preview")
async def supplier_preview(
    decision_id: UUID,
    body: SupplierPreviewBody,
    request: Request,
    tenant_id: TenantId,
    user_id: UserId,
    ctx: ActiveIndustry,
):
    language = await _language(request.app.state.db, tenant_id, user_id, body.language)
    draft = await current_draft(
        request.app.state.db, tenant_id, user_id, ctx.code, decision_id, language
    )
    from app.services.llm.policy import AIContext

    summary = await reports.artifact_summary(
        request.app.state.db,
        getattr(request.app.state, "ai", None),
        AIContext(tenant_id, user_id, IndustryCode(ctx.code), task_name="supplier_draft"),
        draft,
        language=language,
    )
    return {
        **draft,
        "summary": summary,
        "preview_token": _token(
            tenant_id, user_id, f"supplier:{decision_id}", draft["revision"], language
        ),
    }


@router.post("/supplier/{decision_id}/email")
async def supplier_email(
    decision_id: UUID,
    body: ReviewedEmail,
    request: Request,
    tenant_id: TenantId,
    user_id: UserId,
    ctx: ActiveIndustry,
):
    claims = _verify(body, tenant_id, user_id, f"supplier:{decision_id}")
    if body.language and body.language != claims.get("language"):
        raise HTTPException(status_code=409, detail="Draft language changed; review again")
    draft = await current_draft(
        request.app.state.db, tenant_id, user_id, ctx.code, decision_id, claims["language"]
    )
    if draft["revision"] != claims.get("snapshot"):
        raise HTTPException(status_code=409, detail="Decision changed; review a new supplier draft")

    async def eligibility(session, _user):
        latest = await _draft_in_session(
            session, tenant_id, ctx.code, decision_id, claims["language"]
        )
        if latest["revision"] != claims.get("snapshot"):
            raise ValueError("Decision changed; review a new supplier draft")

    try:
        return await deliver_email(
            request.app.state.db,
            tenant_id,
            user_id,
            f"supplier:{body.delivery_key}",
            body.recipient,
            body.subject,
            body.body,
            confirm=body.confirm,
            config=EmailConfig.from_settings(get_settings()),
            eligibility=eligibility,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
