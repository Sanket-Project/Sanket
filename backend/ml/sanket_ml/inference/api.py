"""SANKET ML Inference API.

Endpoints:
  GET  /health             — liveness probe + which zero-shot model is preloaded
  POST /forecast           — primary endpoint: trained artifact, with automatic
                             Chronos zero-shot fallback when no artifact exists
  POST /forecast/zero-shot — explicit zero-shot path, never touches artifacts

The Chronos pipeline is preloaded during FastAPI lifespan startup (controlled
by ML_CHRONOS_PRELOAD_ON_STARTUP) so the first request after boot is fast.
"""

from __future__ import annotations

import hmac
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import structlog
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from sanket_ml.config import MLSettings, get_ml_settings
from sanket_ml.inference.service import InferenceService
from sanket_ml.inference.throttle import ThrottleRejectionError, build_throttle
from sanket_ml.inference.zero_shot import (
    ZeroShotForecaster,
    get_chronos_pipeline,
)

log = structlog.get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────────


class ForecastRequest(BaseModel):
    tenant_id: uuid.UUID
    industry: str = Field(pattern=r"^(fashion|electronics|pharma|agrocenter|hardware)$")
    horizon: int = Field(ge=1, le=104)
    artifact_path: str | None = None

    # Zero-shot controls (only used if no trained artifact is found, or when
    # the caller forces the zero-shot path).
    force_zero_shot: bool = False
    zero_shot_model: Literal["chronos", "timesfm"] = "chronos"
    # Optional in-request context: { sku_id: [historical values, oldest → newest] }.
    # If omitted, zero-shot pulls history from historical_sales via RLS-scoped query.
    series_context: dict[str, list[float]] | None = None
    num_samples: int | None = Field(default=None, ge=20, le=500)


class ZeroShotForecastRequest(BaseModel):
    """Explicit zero-shot request — same shape minus artifact handling."""
    tenant_id: uuid.UUID
    industry: str = Field(pattern=r"^(fashion|electronics|pharma|agrocenter|hardware)$")
    horizon: int = Field(ge=1, le=104)
    model: Literal["chronos", "timesfm"] = "chronos"
    series_context: dict[str, list[float]] | None = None
    num_samples: int | None = Field(default=None, ge=20, le=500)


class ForecastRow(BaseModel):
    sku_id: str
    forecast_date: str
    p10: float
    p50: float
    p90: float


class ForecastResponse(BaseModel):
    run_id: uuid.UUID
    n_predictions: int
    source: Literal["trained", "chronos_zero_shot", "timesfm_zero_shot"]
    context_source: Literal["request", "database", "artifact"] = "artifact"
    n_series: int | None = None
    rows: list[ForecastRow]


# ──────────────────────────────────────────────────────────────────────────
# App factory
# ──────────────────────────────────────────────────────────────────────────


def make_require_service_token(settings: MLSettings):
    """Build a FastAPI dependency that enforces the shared service token.

    Constant-time comparison; rejects browser/anonymous callers. When no token
    is configured and ``require_auth`` is on (the default), the service refuses
    to serve — fail closed rather than silently accept everyone.
    """

    async def _require_service_token(
        authorization: str | None = Header(default=None),
    ) -> None:
        expected = settings.service_token
        if not expected:
            if settings.require_auth:
                log.error("ml.auth.unconfigured")
                raise HTTPException(status_code=503, detail="ML service auth not configured")
            return
        presented = ""
        if authorization and authorization.startswith("Bearer "):
            presented = authorization[7:]
        if not (presented and hmac.compare_digest(presented, expected)):
            raise HTTPException(status_code=401, detail="unauthorized")

    return _require_service_token


def _resolve_artifact_dir(settings: MLSettings, req: ForecastRequest) -> Path | None:
    """Return the artifact dir to use, or None if nothing trained yet.

    A caller-supplied ``artifact_path`` is contained to ``artifact_root`` so a
    crafted path cannot traverse outside the artifact store.
    """
    root = settings.artifact_root.resolve()
    if req.artifact_path:
        p = Path(req.artifact_path).resolve()
        if not p.is_relative_to(root):
            log.warning("forecast.artifact_path.rejected", path=str(req.artifact_path))
            return None
        return p if p.exists() else None
    base = settings.artifact_root / str(req.tenant_id) / req.industry
    if not base.exists():
        return None
    candidates = sorted(
        (p for p in base.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _rows_from_quantiles(fc) -> list[ForecastRow]:
    return [
        ForecastRow(
            sku_id=u,
            forecast_date=str(d.date() if hasattr(d, "date") else d),
            p10=float(fc.p10[i]),
            p50=float(fc.p50[i]),
            p90=float(fc.p90[i]),
        )
        for i, (u, d) in enumerate(zip(fc.unique_id, fc.ds))
    ]


def create_app() -> FastAPI:
    settings = get_ml_settings()
    service = InferenceService(settings)
    zero_shot = ZeroShotForecaster(settings)
    throttle = build_throttle(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Preload Chronos at startup so the first /forecast call after a cold
        # boot doesn't pay the model-download tax. Failures here are logged
        # but non-fatal — the first request will retry the load.
        app.state.chronos_ready = False
        if settings.chronos_preload_on_startup:
            try:
                get_chronos_pipeline(settings)
                app.state.chronos_ready = True
                log.info("startup.chronos.preloaded")
            except Exception as exc:
                log.warning("startup.chronos.preload_failed", error=str(exc))
        else:
            log.info("startup.chronos.preload_skipped")
        yield
        log.info("shutdown.complete")

    app = FastAPI(
        title="SANKET ML Inference",
        version="0.2.0",
        lifespan=lifespan,
    )

    require_service_token = make_require_service_token(settings)
    auth = [Depends(require_service_token)]

    def _reject(exc: ThrottleRejectionError) -> HTTPException:
        """Translate an admission-control rejection into HTTP 429 + Retry-After."""
        return HTTPException(
            status_code=429,
            detail=f"inference overloaded: {exc.reason}",
            headers={"Retry-After": str(exc.retry_after_s)},
        )

    # ── health ────────────────────────────────────────────────────────────
    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "service": "sanket-ml-inference",
            "chronos_preloaded": getattr(app.state, "chronos_ready", False),
            "chronos_repo": settings.chronos_repo,
            "device": settings.device,
            "throttle": throttle.stats(),
        }

    # ── Prometheus metrics ──────────────────────────────────────────────────
    # Hand-rendered text exposition (no extra dependency). Exposes admission-
    # control counters so SanketInferenceLoadShedding can fire on real data.
    @app.get("/metrics")
    async def metrics() -> PlainTextResponse:
        s = throttle.stats()
        lines = [
            "# HELP sanket_ml_inference_accepted_total Forecasts admitted by the throttle.",
            "# TYPE sanket_ml_inference_accepted_total counter",
            f"sanket_ml_inference_accepted_total {s['accepted_total']}",
            "# HELP sanket_ml_inference_rejected_total Forecasts rejected by admission control.",
            "# TYPE sanket_ml_inference_rejected_total counter",
        ]
        for reason, count in s["rejected_total"].items():
            lines.append(f'sanket_ml_inference_rejected_total{{reason="{reason}"}} {count}')
        lines += [
            "# HELP sanket_ml_inference_inflight Forecasts currently executing or queued.",
            "# TYPE sanket_ml_inference_inflight gauge",
            f"sanket_ml_inference_inflight {s['inflight']}",
        ]
        return PlainTextResponse("\n".join(lines) + "\n")

    # ── primary forecast endpoint ─────────────────────────────────────────
    @app.post("/forecast", response_model=ForecastResponse, dependencies=auth)
    async def forecast(req: ForecastRequest) -> ForecastResponse:
        # Admission control wraps the whole compute path: a tenant over its rate,
        # or a replica past its queue capacity, is rejected with 429 BEFORE any
        # CPU is spent. Heavy synchronous inference runs in a thread pool so the
        # semaphore actually bounds concurrency (sync calls would otherwise block
        # the event loop and serialise everything anyway).
        try:
            async with throttle.slot(str(req.tenant_id)):
                return await _forecast_inner(req)
        except ThrottleRejectionError as exc:
            raise _reject(exc) from exc

    async def _forecast_inner(req: ForecastRequest) -> ForecastResponse:
        # 1. Try trained artifact unless the caller forces zero-shot
        artifact_dir: Path | None = None
        if not req.force_zero_shot:
            artifact_dir = _resolve_artifact_dir(settings, req)

        if artifact_dir is not None:
            log.info(
                "forecast.trained.start",
                tenant=str(req.tenant_id),
                industry=req.industry,
                horizon=req.horizon,
                artifact=str(artifact_dir),
            )
            try:
                result = await run_in_threadpool(
                    service.forecast, req.tenant_id, req.industry, artifact_dir, req.horizon
                )
            except FileNotFoundError as exc:
                # Artifact dir exists but ensemble.joblib is missing — log and
                # fall through to zero-shot rather than 500'ing.
                log.warning(
                    "forecast.trained.artifact_incomplete",
                    artifact=str(artifact_dir),
                    error=str(exc),
                )
                artifact_dir = None
            except Exception as exc:
                log.exception("forecast.trained.failed")
                raise HTTPException(status_code=500, detail="internal forecast error") from exc
            else:
                return ForecastResponse(
                    run_id=result.run_id,
                    n_predictions=len(result.forecast.unique_id),
                    source="trained",
                    context_source="artifact",
                    n_series=len(set(result.forecast.unique_id)),
                    rows=_rows_from_quantiles(result.forecast),
                )

        # 2. Zero-shot fallback
        log.info(
            "forecast.zero_shot.fallback",
            tenant=str(req.tenant_id),
            industry=req.industry,
            horizon=req.horizon,
            model=req.zero_shot_model,
            reason="forced" if req.force_zero_shot else "no_artifact",
        )
        try:
            zs = await run_in_threadpool(
                lambda: zero_shot.forecast(
                    tenant_id=req.tenant_id,
                    industry=req.industry,
                    horizon=req.horizon,
                    model=req.zero_shot_model,
                    series_context=req.series_context,
                    num_samples=req.num_samples,
                )
            )
        except ValueError as exc:
            # No history at all → genuinely cannot forecast. 422 surfaces in UI cleanly.
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            # Foundation model package missing or failed to load.
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            log.exception("forecast.zero_shot.failed")
            raise HTTPException(status_code=500, detail="internal forecast error") from exc

        # Persist alongside trained runs for audit parity
        try:
            run_id = service.persist_forecast(
                tenant_id=req.tenant_id,
                industry=req.industry,
                fc=zs.forecast,
                horizon=req.horizon,
                model_stack=[zs.source_model],
                run_metadata={
                    "mode": "zero_shot",
                    "model": zs.source_model,
                    "context_source": zs.context_source,
                    "n_series": zs.n_series,
                    "used_observations": zs.used_observations,
                },
            )
        except Exception as exc:
            # Persistence failure is not fatal — return the forecast anyway with
            # a synthetic run_id so the client still gets results.
            log.warning("forecast.zero_shot.persist_failed", error=str(exc))
            run_id = uuid.uuid4()

        return ForecastResponse(
            run_id=run_id,
            n_predictions=len(zs.forecast.unique_id),
            source=zs.source_model,  # type: ignore[arg-type]
            context_source=zs.context_source,  # type: ignore[arg-type]
            n_series=zs.n_series,
            rows=_rows_from_quantiles(zs.forecast),
        )

    # ── explicit zero-shot endpoint ───────────────────────────────────────
    @app.post("/forecast/zero-shot", response_model=ForecastResponse, dependencies=auth)
    async def zero_shot_endpoint(req: ZeroShotForecastRequest) -> ForecastResponse:
        try:
            async with throttle.slot(str(req.tenant_id)):
                return await _zero_shot_inner(req)
        except ThrottleRejectionError as exc:
            raise _reject(exc) from exc

    async def _zero_shot_inner(req: ZeroShotForecastRequest) -> ForecastResponse:
        try:
            zs = await run_in_threadpool(
                lambda: zero_shot.forecast(
                    tenant_id=req.tenant_id,
                    industry=req.industry,
                    horizon=req.horizon,
                    model=req.model,
                    series_context=req.series_context,
                    num_samples=req.num_samples,
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            log.exception("forecast.zero_shot.failed")
            raise HTTPException(status_code=500, detail="internal forecast error") from exc

        try:
            run_id = service.persist_forecast(
                tenant_id=req.tenant_id,
                industry=req.industry,
                fc=zs.forecast,
                horizon=req.horizon,
                model_stack=[zs.source_model],
                run_metadata={
                    "mode": "zero_shot_explicit",
                    "model": zs.source_model,
                    "context_source": zs.context_source,
                    "n_series": zs.n_series,
                },
            )
        except Exception as exc:
            log.warning("forecast.zero_shot.persist_failed", error=str(exc))
            run_id = uuid.uuid4()

        return ForecastResponse(
            run_id=run_id,
            n_predictions=len(zs.forecast.unique_id),
            source=zs.source_model,  # type: ignore[arg-type]
            context_source=zs.context_source,  # type: ignore[arg-type]
            n_series=zs.n_series,
            rows=_rows_from_quantiles(zs.forecast),
        )

    return app


app = create_app()
