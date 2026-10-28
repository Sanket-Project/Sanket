"""Server-side proxy to the internal ML inference service.

The SPA used to call the ML service directly with a client-supplied
``tenant_id`` — an IDOR: the ML service pushes that id into the RLS GUC, so a
browser could request any tenant's forecast. The ML service is now internal and
token-gated; this endpoint is the only sanctioned path from the browser.

``tenant_id`` is derived from the *verified* bearer token (``request.state``),
never from the request body, and the call to the ML service carries the shared
service token.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.config import Settings, get_settings
from app.routers.industry_router import ActiveIndustry, TenantId
from app.services.forecast_gate import assert_forecastable

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/forecasts", tags=["forecast"])


@router.get("/average-sales")
async def average_sales_projection(
    request: Request, tenant_id: TenantId, industry: ActiveIndustry,
    horizon_weeks: int = Query(default=12, ge=1, le=52),
    offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=100),
    search: str = Query(default="", max_length=200),
) -> dict[str, Any]:
    from app.services.period_projection import projection
    return await projection(request.app.state.db, tenant_id, industry.code,
                            horizon_weeks=horizon_weeks, offset=offset, limit=limit, search=search)
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _forecast_queue(request: Request):
    return getattr(request.app.state, 'arq', None)


@router.get('/latest')
async def latest_forecast(
    request: Request, tenant_id: TenantId, industry: ActiveIndustry,
    view: Literal['summary', 'skus'] = 'skus',
    offset: int = Query(default=0, ge=0), limit: int = Query(default=6, ge=1, le=100),
    search: str = Query(default="", max_length=200),
    run_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    from app.services.persisted_forecasts import read_latest
    return await read_latest(request.app.state.db, tenant_id, industry.code,
                             view=view, offset=offset, limit=limit, search=search, run_id=run_id)


class RefreshForecastBody(BaseModel):
    horizon: int = Field(default=26, ge=1, le=104)
    force: bool = False
    force_zero_shot: bool = True


@router.post('/refresh', status_code=202)
async def refresh_forecast(
    body: RefreshForecastBody, request: Request, tenant_id: TenantId, industry: ActiveIndustry,
) -> dict[str, Any]:
    from app.services.persisted_forecasts import request_refresh
    async with request.app.state.db.session(str(tenant_id)) as session:
        await assert_forecastable(session, tenant_id=tenant_id, industry=industry.code)
    return await request_refresh(request.app.state.db, _forecast_queue(request), tenant_id,
                                 industry.code, horizon=body.horizon, force=body.force,
                                 force_zero_shot=body.force_zero_shot)


class GenerateForecastBody(BaseModel):
    # industry is taken from the active-industry context by default; an explicit
    # value is still validated against the licensed set by the middleware.
    horizon: int = Field(default=26, ge=1, le=104)
    force_zero_shot: bool = False


@router.post("/generate")
async def generate_forecast(
    body: GenerateForecastBody,
    request: Request,
    tenant_id: TenantId,
    industry: ActiveIndustry,
    settings: SettingsDep,
) -> dict[str, Any]:
    """Generate a probabilistic forecast for the caller's tenant + active industry."""
    async with request.app.state.db.session(str(tenant_id)) as session:
        await assert_forecastable(session, tenant_id=tenant_id, industry=industry.code)
    return await _forecast_via_ml(
        request,
        settings,
        tenant_id,
        {
            "tenant_id": str(tenant_id),  # authoritative: from the verified token
            "industry": industry.code,
            "horizon": body.horizon,
            "force_zero_shot": body.force_zero_shot,
        },
    )


class BacktestBody(BaseModel):
    #: Forecast as if it were this Monday: the model sees only earlier weeks.
    cutoff: date
    horizon: int = Field(default=8, ge=1, le=26)

    @field_validator("cutoff")
    @classmethod
    def _past_monday(cls, v: date) -> date:
        if v.weekday() != 0:
            raise ValueError("cutoff must be a Monday (the start of a UTC week)")
        today = datetime.now(UTC).date()
        if v >= today - timedelta(days=today.weekday()):
            raise ValueError("cutoff must be before the current week — a backtest looks back")
        return v


@router.post("/backtest")
async def backtest_forecast(
    body: BacktestBody,
    request: Request,
    tenant_id: TenantId,
    industry: ActiveIndustry,
    settings: SettingsDep,
) -> dict[str, Any]:
    """Explicit historical forecast from history before ``cutoff`` only.

    The run is stored with ``mode = "backtest"`` and reported separately from
    production accuracy, which only ever scores forecasts made before their
    week began. Always zero-shot: a trained artifact may have seen the weeks
    being predicted.
    """
    async with request.app.state.db.session(str(tenant_id)) as session:
        await assert_forecastable(session, tenant_id=tenant_id, industry=industry.code)
    return await _forecast_via_ml(
        request,
        settings,
        tenant_id,
        {
            "tenant_id": str(tenant_id),
            "industry": industry.code,
            "horizon": body.horizon,
            "force_zero_shot": True,
            "history_end": body.cutoff.isoformat(),
        },
    )


async def _post_to_ml(
    request: Request, url: str, payload: dict, headers: dict, timeout: float
) -> httpx.Response:
    http: httpx.AsyncClient | None = getattr(request.app.state, "http", None)
    if http is not None:
        return await http.post(url, json=payload, headers=headers, timeout=timeout)
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(url, json=payload, headers=headers)


async def _forecast_via_ml(
    request: Request, settings: Settings, tenant_id: Any, payload: dict
) -> dict[str, Any]:
    url = f"{settings.ml_api_url.rstrip('/')}/forecast"
    headers = {"Authorization": f"Bearer {settings.ml_service_token_effective}"}
    try:
        r = await _post_to_ml(request, url, payload, headers, settings.ml_api_timeout_s)
        r.raise_for_status()
        result = r.json()
        # The Forecasts page uses this proxy rather than the hybrid-run worker.
        # Split the ML service's persisted SKU run before exposing its location
        # view. For historical runs, shares use only history before the cutoff.
        try:
            from app.models.forecast import ForecastRun
            from app.services.location_forecast import ensure_location_split

            async with request.app.state.db.session(str(tenant_id)) as session:
                run = await session.get(ForecastRun, uuid.UUID(result["run_id"]))
                if run is None:
                    result["location_reason"] = "The forecast run was not persisted; location split unavailable"
                else:
                    history_end = (run.metrics or {}).get("history_end")
                    cutoff = datetime.fromisoformat(history_end).replace(tzinfo=UTC) if history_end else datetime.now(UTC)
                    await ensure_location_split(session, tenant_id=tenant_id,
                        industry=payload["industry"], run=run, now=cutoff)
        except Exception as exc:
            log.warning("forecasts.location_split_failed", error=str(exc))
            result["location_reason"] = "Location split failed; the SKU forecast is still available"
        return result
    except httpx.TimeoutException as exc:
        log.warning("forecasts.ml.timeout", tenant=str(tenant_id))
        raise HTTPException(status_code=504, detail="Forecast service timed out") from exc
    except httpx.HTTPStatusError as exc:
        # Surface 4xx domain errors (e.g. 422 "no history") to the client, BUT
        # never forward a 401 from the ML service — that is a backend
        # misconfiguration (wrong/missing ML_SERVICE_TOKEN), not a client auth
        # failure. Forwarding it causes the frontend 401 interceptor to treat it
        # as an expired user session and sign the user out immediately.
        status = exc.response.status_code
        if status == 401 or status == 403:
            log.error(
                "forecasts.ml.auth_error",
                status=status,
                hint="Check ML_SERVICE_TOKEN matches between backend and ml service",
            )
            raise HTTPException(
                status_code=502,
                detail="Forecast service configuration error",
            ) from exc
        if status < 500:
            raise HTTPException(status_code=status, detail=_safe_detail(exc.response)) from exc
        log.error("forecasts.ml.http_error", status=status, body=exc.response.text[:200])
        raise HTTPException(status_code=502, detail="Forecast service error") from exc
    except httpx.HTTPError as exc:
        log.warning("forecasts.ml.unreachable", error=str(exc))
        raise HTTPException(status_code=503, detail="Forecast service unavailable") from exc


@router.get("/ml-health")
async def ml_health(request: Request, settings: SettingsDep) -> dict[str, Any]:
    """Lightweight upstream health check (no service token required upstream)."""
    url = f"{settings.ml_api_url.rstrip('/')}/health"
    http: httpx.AsyncClient | None = getattr(request.app.state, "http", None)
    try:
        if http is not None:
            r = await http.get(url, timeout=5.0)
        else:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(url)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError:
        return {"status": "unavailable"}


def _safe_detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
        if isinstance(detail, str):
            return detail
    except Exception:  # noqa: S110 - best-effort extraction
        pass
    return "Forecast request rejected"


@router.get("/confidence")
async def forecast_confidence(
    request: Request,
    tenant_id: TenantId,
    industry: ActiveIndustry,
    limit: int = 200,
) -> dict[str, Any]:
    """Per-SKU trust score for the latest forecast, with the reasons behind it.

    A p10/p50/p90 band shows uncertainty but not *why*. This returns a 0–100
    score, a band, and the specific deductions ("only 9 weeks of history",
    "62% of weeks had no sales") so a planner knows whether to act on the number
    or go fix the data first.
    """
    from app.models.enums import IndustryCode
    from app.models.product import Sku
    from app.services.decision_builder import (
        confidence_for,
        forecast_bands,
        latest_completed_run,
        weekly_history,
    )

    db = request.app.state.db
    ind = IndustryCode(industry.code)

    async with db.session(str(tenant_id)) as session:
        run = await latest_completed_run(session, tenant_id, ind)
        if run is None:
            return {
                "industry": industry.code,
                "run_id": None,
                "scored": 0,
                "reason": "No completed forecast run yet.",
                "skus": [],
            }

        bands = await forecast_bands(session, tenant_id, run.id)
        ids = list(bands)[: get_settings().forecast_max_skus]
        if not ids:
            return {
                "industry": industry.code,
                "run_id": str(run.id),
                "scored": 0,
                "reason": "The latest run produced no SKU-level results.",
                "skus": [],
            }

        codes = {
            r.id: r.sku_code
            for r in (
                await session.execute(
                    select(Sku.id, Sku.sku_code).where(
                        Sku.tenant_id == tenant_id, Sku.id.in_(ids)
                    )
                )
            ).fetchall()
        }
        history = await weekly_history(session, tenant_id, ind, ids)

    rows = []
    for sku_id in ids:
        score, _ = confidence_for(bands[sku_id], history.get(sku_id), run)
        rows.append(
            {
                "sku_id": str(sku_id),
                "sku_code": codes.get(sku_id),
                "confidence": score.score,
                "band": score.band,
                "actionable": score.is_actionable,
                "reasons": score.reasons,
                "deductions": score.deductions,
            }
        )
    rows.sort(key=lambda r: r["confidence"])

    bands_count: dict[str, int] = {}
    for r in rows:
        bands_count[r["band"]] = bands_count.get(r["band"], 0) + 1

    return {
        "industry": industry.code,
        "run_id": str(run.id),
        "scored": len(rows),
        "portfolio_confidence": round(sum(r["confidence"] for r in rows) / len(rows)) if rows else 0,
        "by_band": bands_count,
        "skus": rows[:limit],
    }
