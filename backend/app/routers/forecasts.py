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

from typing import Annotated, Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import Settings, get_settings
from app.routers.industry_router import ActiveIndustry, TenantId

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/forecasts", tags=["forecast"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


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
    url = f"{settings.ml_api_url.rstrip('/')}/forecast"
    payload = {
        "tenant_id": str(tenant_id),  # authoritative: from the verified token
        "industry": industry.code,
        "horizon": body.horizon,
        "force_zero_shot": body.force_zero_shot,
    }
    headers = {"Authorization": f"Bearer {settings.ml_service_token_effective}"}
    http: httpx.AsyncClient | None = getattr(request.app.state, "http", None)
    try:
        if http is not None:
            r = await http.post(
                url, json=payload, headers=headers, timeout=settings.ml_api_timeout_s
            )
        else:
            async with httpx.AsyncClient(timeout=settings.ml_api_timeout_s) as client:
                r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()
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
        MAX_SKUS,
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
        ids = list(bands)[:MAX_SKUS]
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
