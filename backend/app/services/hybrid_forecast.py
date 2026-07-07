"""Hybrid forecast compute core — shared by the HTTP layer and the arq worker.

The heavy lifting (ML baseline + trend fusion + shortage alerts) lives here so it
can run either:

* inline inside a request (the deprecated synchronous ``POST /forecast/hybrid``), or
* out-of-process in the arq worker, driven by ``execute_hybrid_run`` which manages
  the ``hybrid_forecast_runs`` row lifecycle and emits realtime progress events.

Keeping it framework-agnostic (no ``Request`` / ``app.state`` access) is what lets
the worker call it with its own Database / httpx / realtime handles.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from typing import Any

import httpx
import numpy as np
import pandas as pd
import structlog
from sanket_ml.alerts import AlertPublisher, InventoryPosition, ShortageDetector
from sanket_ml.fusion import HybridForecaster, SignalRecord
from sanket_ml.models.base import ForecastQuantiles
from sqlalchemy import select, update

from app.config import get_settings
from app.models.enums import IndustryCode
from app.models.product import Sku
from app.models.trend import HybridForecastRun, TrendSignal
from app.realtime.events import (
    EVENT_FORECAST_COMPLETED,
    EVENT_FORECAST_FAILED,
    EVENT_FORECAST_PROGRESS,
    ForecastProgressData,
    RealtimeEvent,
)
from app.schemas.trends import (
    HybridForecastOut,
    HybridForecastRequest,
    HybridForecastSeriesOut,
    ScenarioOut,
    TrendScoreOut,
)
from app.services.industry_config import filter_signals_by_focus, resolve_effective_config
from app.services.industry_context import get_industry_context
from app.services.inventory import InventorySnapshot, current_levels, resolve_on_hand

log = structlog.get_logger(__name__)

_PROGRESS_TOTAL = 4  # data → fit → ensemble → validate (persist handled by caller)


@dataclass
class HybridComputeResult:
    """Pure compute output plus the adjuster params needed for the audit row."""

    out: HybridForecastOut
    trend_score: float
    signal_volatility: float
    alpha: float
    beta: float
    scenarios: dict[str, dict]
    drivers: list[dict]


async def _emit(realtime: Any | None, event: RealtimeEvent) -> None:
    """Publish a realtime event if a manager is wired; never fail the job on it."""
    if realtime is None:
        return
    try:
        await realtime.publish(event)
    except Exception as exc:  # pragma: no cover - best-effort fan-out
        log.warning("hybrid.event.publish_failed", error=str(exc))


def _progress_event(
    tenant_id: uuid.UUID,
    industry_code: str,
    run_id: uuid.UUID,
    stage: str,
    step: int,
    message: str,
) -> RealtimeEvent:
    return RealtimeEvent(
        type=EVENT_FORECAST_PROGRESS,
        tenant_id=tenant_id,
        industry=industry_code,
        data=ForecastProgressData(
            run_id=run_id,
            stage=stage,  # type: ignore[arg-type]
            step=step,
            total_steps=_PROGRESS_TOTAL,
            message=message,
        ).model_dump(mode="json"),
    )


async def _fetch_ml_baseline(
    tenant_id: uuid.UUID,
    industry: str,
    horizon_weeks: int,
    http_client: httpx.AsyncClient | None = None,
) -> dict | None:
    """Call ml-api/forecast for the real probabilistic baseline.

    Returns the parsed JSON body on success, or None if the ML service is
    unreachable / errored — caller then falls back to the synthetic generator.
    """
    settings = get_settings()
    url = f"{settings.ml_api_url.rstrip('/')}/forecast"
    payload = {
        "tenant_id": str(tenant_id),
        "industry": industry,
        "horizon": horizon_weeks,
        "force_zero_shot": False,
    }
    headers = {"Authorization": f"Bearer {settings.ml_service_token_effective}"}
    try:
        if http_client is not None:
            r = await http_client.post(
                url, json=payload, headers=headers, timeout=settings.ml_api_timeout_s
            )
        else:
            async with httpx.AsyncClient(timeout=settings.ml_api_timeout_s) as client:
                r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()
    except httpx.TimeoutException:
        log.warning("hybrid.ml_api.timeout", url=url, timeout=settings.ml_api_timeout_s)
    except httpx.ConnectError as exc:
        log.warning("hybrid.ml_api.unreachable", url=url, error=str(exc))
    except httpx.HTTPStatusError as exc:
        log.warning(
            "hybrid.ml_api.http_error",
            url=url,
            status=exc.response.status_code,
            body=exc.response.text[:200],
        )
    except Exception as exc:
        log.exception("hybrid.ml_api.unexpected", error=str(exc))
    return None


async def compute_hybrid_forecast(
    *,
    db,
    http_client: httpx.AsyncClient | None,
    realtime: Any | None,
    run_id: uuid.UUID,
    tenant_id: uuid.UUID,
    industry_code: str,
    body: HybridForecastRequest,
) -> HybridComputeResult:
    """Run the full hybrid pipeline. Pure compute — does not touch the run row.

    Emits ``forecast.run.progress`` events through ``realtime`` (if provided) so
    the UI can show a live progress bar while the ~60s ML inference runs.
    """
    industry = IndustryCode(industry_code)
    # body.horizon_weeks is normally resolved at the router; guard the worker /
    # direct-call paths so an omitted horizon still falls back to the archetype default.
    horizon_weeks = body.horizon_weeks or get_industry_context(industry_code).default_horizon_weeks

    # ── 1. Load target SKUs ─────────────────────────────────────────────────
    await _emit(
        realtime,
        _progress_event(tenant_id, industry_code, run_id, "data", 1, "Loading SKUs"),
    )
    async with db.session(str(tenant_id)) as session:
        sku_q = select(Sku).where(
            Sku.tenant_id == tenant_id,
            Sku.industry == industry,
            Sku.is_active == True,  # noqa: E712
        )
        if body.sku_ids:
            sku_q = sku_q.where(Sku.id.in_(body.sku_ids))
        sku_q = sku_q.limit(50)
        rows = await session.execute(sku_q)
        sku_list = list(rows.scalars().all()) if hasattr(rows, "scalars") else list(rows or [])

    if not sku_list:
        # No fabricated stand-in SKU: fail honestly so the run is marked failed
        # with an actionable message instead of returning a fake forecast.
        raise ValueError(
            f"No active SKUs found for industry '{industry_code}'. "
            "Import products/SKUs (CSV upload or a connector) before forecasting."
        )

    # ── 2. Build baseline ForecastQuantiles ─────────────────────────────────
    await _emit(
        realtime,
        _progress_event(
            tenant_id, industry_code, run_id, "fit", 2, "Running ML baseline (Chronos)"
        ),
    )
    all_unique_id: list[str] = []
    all_ds: list[datetime] = []
    all_p10: list[float] = []
    all_p50: list[float] = []
    all_p90: list[float] = []
    per_sku_baseline: dict[str, dict[str, list[float]]] = {}
    baseline_source = "trained"

    ml_response = await _fetch_ml_baseline(
        tenant_id, industry_code, horizon_weeks, http_client=http_client
    )
    sku_id_filter = {str(s.id) for s in sku_list}

    if ml_response and ml_response.get("rows"):
        grouped: dict[str, list[dict]] = {}
        for row in ml_response["rows"]:
            sid = row["sku_id"]
            if sku_id_filter and sid not in sku_id_filter:
                continue
            grouped.setdefault(sid, []).append(row)

        if grouped:
            baseline_source = ml_response.get("source", "trained")
            for sid, grp in grouped.items():
                grp.sort(key=lambda r: r["forecast_date"])
                grp = grp[:horizon_weeks]
                ds_local = [datetime.fromisoformat(r["forecast_date"]) for r in grp]
                p10_arr = np.array([float(r["p10"]) for r in grp])
                p50_arr = np.array([float(r["p50"]) for r in grp])
                p90_arr = np.array([float(r["p90"]) for r in grp])
                n = len(grp)
                all_unique_id.extend([sid] * n)
                all_ds.extend(ds_local)
                all_p10.extend(p10_arr.tolist())
                all_p50.extend(p50_arr.tolist())
                all_p90.extend(p90_arr.tolist())
                per_sku_baseline[sid] = {"p50": p50_arr.tolist()}
            log.info(
                "hybrid.baseline.ml",
                source=baseline_source,
                series=len(grouped),
                rows=len(ml_response["rows"]),
            )

    if not all_unique_id:
        # No fabricated baseline: the ML service is required to produce a real
        # probabilistic forecast. Fail honestly so the run surfaces the reason.
        log.warning("hybrid.baseline.unavailable", reason="ml_empty_or_unreachable")
        raise RuntimeError(
            "ML baseline unavailable: the ml-api returned no forecast rows or was "
            "unreachable. Ensure the ML inference API is running and a model "
            "(trained or Chronos zero-shot) is loaded, then retry."
        )

    baseline = ForecastQuantiles(
        unique_id=all_unique_id,
        ds=[pd.Timestamp(d) for d in all_ds],
        p10=np.array(all_p10),
        p50=np.array(all_p50),
        p90=np.array(all_p90),
        model_name=f"phase6_baseline:{baseline_source}",
    )

    # ── 3. Load recent signals ──────────────────────────────────────────────
    cutoff = datetime.now(UTC) - timedelta(days=7)
    async with db.session(str(tenant_id)) as session:
        config = await resolve_effective_config(session, tenant_id, industry_code)
        sig_q = select(TrendSignal).where(
            TrendSignal.industry == industry,
            TrendSignal.captured_at >= cutoff,
        )
        sig_rows = await session.execute(sig_q)
        sigs_db = (
            list(sig_rows.scalars().all()) if hasattr(sig_rows, "scalars") else list(sig_rows or [])
        )

    # Scope signals to the tenant's focus watchlist so two tenants in the same
    # archetype (e.g. a rice mill vs a farm-supply store, both agrocenter) fuse
    # different, business-relevant signals.
    if not config.focus.is_empty:
        n_before = len(sigs_db)
        sigs_db = filter_signals_by_focus(sigs_db, config.focus)
        log.info(
            "hybrid.signals.focus_filtered",
            industry=industry_code,
            keywords=list(config.focus.keywords),
            before=n_before,
            after=len(sigs_db),
        )

    signal_records: list[SignalRecord] = []
    for s in sigs_db:
        try:
            signal_records.append(
                SignalRecord(
                    source=s.source.value if hasattr(s.source, "value") else str(s.source),
                    kind=s.kind.value if hasattr(s.kind, "value") else str(s.kind),
                    series_key=s.series_key,
                    industry=s.industry.value if hasattr(s.industry, "value") else str(s.industry),
                    normalized_score=float(s.normalized_score),
                    confidence=float(s.confidence),
                    captured_at=s.captured_at,
                    category_tags=list(s.category_tags or []),
                )
            )
        except Exception:
            continue

    # ── 4. Fuse ─────────────────────────────────────────────────────────────
    await _emit(
        realtime,
        _progress_event(tenant_id, industry_code, run_id, "ensemble", 3, "Fusing trend signals"),
    )
    fuser = HybridForecaster()
    result = fuser.fuse(
        industry=industry_code,
        baseline=baseline,
        signals=signal_records,
        horizon_days=horizon_weeks * 7,
    )

    # ── 5. (Optional) shortage alerts ───────────────────────────────────────
    await _emit(
        realtime,
        _progress_event(tenant_id, industry_code, run_id, "validate", 4, "Scanning for shortages"),
    )
    alerts_count = 0
    if body.include_alerts:
        sku_uuids = [s.id for s in sku_list if isinstance(getattr(s, "id", None), uuid.UUID)]
        inv_map: dict[str, InventorySnapshot] = {}
        try:
            async with db.session(str(tenant_id)) as session:
                inv_map = await current_levels(
                    session,
                    tenant_id=tenant_id,
                    industry=industry_code,
                    sku_ids=sku_uuids or None,
                )
        except Exception:
            log.warning("hybrid.inventory.load_failed", exc_info=True)

        positions: list[InventoryPosition] = []
        per_sku_demand: dict[str, tuple[float, float, float]] = {}
        on_hand_sources: dict[str, int] = {}
        for sku in sku_list:
            sku_id = str(sku.id)
            override = body.inventory_overrides.get(sku_id, {})
            snapshot = inv_map.get(sku_id)
            on_hand, on_hand_source = resolve_on_hand(
                override_units=override.get("on_hand_units"),
                snapshot=snapshot,
                safety_stock_units=float(sku.safety_stock or 0),
            )
            on_hand_sources[on_hand_source] = on_hand_sources.get(on_hand_source, 0) + 1
            default_inbound = snapshot.inbound_units if snapshot else 0.0
            positions.append(
                InventoryPosition(
                    sku_id=sku_id,
                    sku_code=getattr(sku, "sku_code", sku_id),
                    on_hand_units=on_hand,
                    inbound_units=float(override.get("inbound_units", default_inbound)),
                    safety_stock_units=float(sku.safety_stock or 0),
                    lead_time_days=float(sku.lead_time_days or 14),
                )
            )
            mask = [u == sku_id for u in result.adjusted.unique_id]
            arr10 = np.array([v for v, m in zip(result.adjusted.p10, mask, strict=False) if m])
            arr50 = np.array([v for v, m in zip(result.adjusted.p50, mask, strict=False) if m])
            arr90 = np.array([v for v, m in zip(result.adjusted.p90, mask, strict=False) if m])
            if len(arr50) == 0:
                continue
            per_sku_demand[sku_id] = (
                float(arr10.mean()) / 7.0,
                float(arr50.mean()) / 7.0,
                float(arr90.mean()) / 7.0,
            )

        log.info(
            "hybrid.inventory.resolved",
            tenant=str(tenant_id),
            industry=industry_code,
            n_positions=len(positions),
            on_hand_sources=on_hand_sources,
        )

        detector = ShortageDetector()
        alerts = detector.scan_portfolio(
            industry=industry_code,
            positions=positions,
            per_sku_demand=per_sku_demand,
            trend=result.trend,
            horizon_days=horizon_weeks * 7,
        )
        if alerts:
            publisher = AlertPublisher(realtime=realtime)
            async with db.session(str(tenant_id)) as session:
                inserted = await publisher.publish_many(
                    session=session,
                    tenant_id=tenant_id,
                    alerts=alerts,
                )
            alerts_count = len(inserted)

    # ── 6. Shape response ──────────────────────────────────────────────────
    series_payload: list[HybridForecastSeriesOut] = []
    sku_lookup = {str(s.id): s for s in sku_list}
    for sku_id in set(result.adjusted.unique_id):
        mask = [u == sku_id for u in result.adjusted.unique_id]
        ds_str = [str(d) for d, m in zip(result.adjusted.ds, mask, strict=False) if m]
        series_payload.append(
            HybridForecastSeriesOut(
                sku_id=sku_id,
                sku_code=getattr(sku_lookup.get(sku_id), "sku_code", None),
                ds=ds_str,
                p10=[float(v) for v, m in zip(result.adjusted.p10, mask, strict=False) if m],
                p50=[float(v) for v, m in zip(result.adjusted.p50, mask, strict=False) if m],
                p90=[float(v) for v, m in zip(result.adjusted.p90, mask, strict=False) if m],
                baseline_p50=per_sku_baseline.get(sku_id, {}).get("p50", []),
            )
        )

    scenarios = {name: ScenarioOut(**s.to_dict()) for name, s in result.scenarios.items()}

    out = HybridForecastOut(
        industry=industry,
        horizon_weeks=horizon_weeks,
        generated_at=datetime.now(UTC),
        trend=TrendScoreOut(
            industry=industry,
            score=result.trend.score,
            volatility=result.trend.volatility,
            sample_count=result.trend.sample_count,
            by_kind=result.trend.by_kind,
            drivers=result.trend.drivers,
            demand_factors=getattr(result.trend, "demand_factors", []),
            horizon_days=result.trend.horizon_days,
            as_of=datetime.now(UTC),
        ),
        explanation=result.explanation,
        scenarios=scenarios,
        series=series_payload,
        alerts_generated=alerts_count,
        data_source=baseline_source,
    )

    return HybridComputeResult(
        out=out,
        trend_score=float(result.trend.score),
        signal_volatility=float(result.trend.volatility),
        alpha=float(result.params.alpha),
        beta=float(result.params.beta),
        scenarios={k: v.to_dict() for k, v in result.scenarios.items()},
        drivers=result.trend.drivers,
    )


async def _persist_accuracy_snapshot(
    *,
    db,
    tenant_id: uuid.UUID,
    industry_code: str,
    out: HybridForecastOut,
) -> None:
    """Write a forecast_runs + forecast_results snapshot from this completed
    hybrid run so the Forecast Accuracy page (MAPE/WAPE vs ground-truth
    actuals) keeps accumulating fresh data on its own over time, instead of
    relying on a one-off manual seed. Every real hybrid run from here on
    writes a real per-SKU snapshot; GET /forecast/accuracy picks up the most
    recently completed one automatically once actuals for those weeks land
    in historical_sales.

    Best-effort: a failure here must never fail the hybrid run itself, since
    the run's own result (already saved on hybrid_forecast_runs) is the
    thing the user is actually waiting on.
    """
    from app.models.forecast import ForecastResult, ForecastRun

    try:
        run_row_id = uuid.uuid4()
        async with db.session(str(tenant_id)) as session:
            session.add(
                ForecastRun(
                    id=run_row_id,
                    tenant_id=tenant_id,
                    industry=IndustryCode(industry_code),
                    run_name="Hybrid forecast (auto-snapshot)",
                    model_stack=["hybrid-trend-fused"],
                    horizon_weeks=out.horizon_weeks,
                    granularity="weekly",
                    status="completed",
                    started_at=out.generated_at,
                    completed_at=out.generated_at,
                )
            )
            # Force the parent row to be inserted before any ForecastResult
            # rows are added — without this, the two inserts can be flushed
            # out of dependency order and the results' run_id FK violates
            # (observed in testing: "Key is not present in table
            # forecast_runs" even though the run row was added first).
            await session.flush()
            for s in out.series:
                try:
                    sku_uuid = uuid.UUID(s.sku_id)
                except ValueError:
                    continue
                for ds, p10, p50, p90 in zip(s.ds, s.p10, s.p50, s.p90, strict=False):
                    forecast_date = datetime.fromisoformat(ds).date() if isinstance(ds, str) else ds
                    session.add(
                        ForecastResult(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            run_id=run_row_id,
                            sku_id=sku_uuid,
                            forecast_date=forecast_date,
                            p10=D(str(round(p10, 4))),
                            p50=D(str(round(p50, 4))),
                            p90=D(str(round(p90, 4))),
                            model_name="hybrid-trend-fused",
                        )
                    )
            await session.commit()
        log.info(
            "hybrid.run.accuracy_snapshot_saved",
            tenant=str(tenant_id),
            industry=industry_code,
            forecast_run_id=str(run_row_id),
            series=len(out.series),
        )
    except Exception as exc:  # pragma: no cover - best-effort, never fail the run
        log.warning("hybrid.run.accuracy_snapshot_failed", error=str(exc))


async def execute_hybrid_run(
    *,
    db,
    http_client: httpx.AsyncClient | None,
    realtime: Any | None,
    run_id: uuid.UUID,
    tenant_id: uuid.UUID,
    industry_code: str,
    body: HybridForecastRequest,
) -> None:
    """Drive a single ``hybrid_forecast_runs`` row through its lifecycle.

    pending → running → (completed | failed). The full ``HybridForecastOut`` is
    stored in the ``result`` JSONB column; the adjuster params land in the audit
    columns. Terminal state is broadcast as a realtime event. Never raises — the
    failure is recorded on the row so callers/pollers can read it back.
    """
    log.info("hybrid.run.start", run_id=str(run_id), tenant=str(tenant_id))
    try:
        async with db.session(str(tenant_id)) as session:
            await session.execute(
                update(HybridForecastRun)
                .where(HybridForecastRun.id == run_id)
                .values(status="running")
            )

        computed = await compute_hybrid_forecast(
            db=db,
            http_client=http_client,
            realtime=realtime,
            run_id=run_id,
            tenant_id=tenant_id,
            industry_code=industry_code,
            body=body,
        )

        async with db.session(str(tenant_id)) as session:
            await session.execute(
                update(HybridForecastRun)
                .where(HybridForecastRun.id == run_id)
                .values(
                    status="completed",
                    result=computed.out.model_dump(mode="json"),
                    trend_score=D(str(round(computed.trend_score, 4))),
                    signal_volatility=D(str(round(computed.signal_volatility, 4))),
                    alpha=D(str(round(computed.alpha, 4))),
                    beta=D(str(round(computed.beta, 4))),
                    scenarios=computed.scenarios,
                    drivers=computed.drivers,
                    completed_at=datetime.now(UTC),
                )
            )

        await _emit(
            realtime,
            RealtimeEvent(
                type=EVENT_FORECAST_COMPLETED,
                tenant_id=tenant_id,
                industry=industry_code,
                data={
                    "run_id": str(run_id),
                    "series": len(computed.out.series),
                    "alerts_generated": computed.out.alerts_generated,
                    "data_source": computed.out.data_source,
                },
            ),
        )
        log.info("hybrid.run.completed", run_id=str(run_id), data_source=computed.out.data_source)

        await _persist_accuracy_snapshot(
            db=db,
            tenant_id=tenant_id,
            industry_code=industry_code,
            out=computed.out,
        )

    except Exception as exc:
        log.exception("hybrid.run.failed", run_id=str(run_id), error=str(exc))
        try:
            async with db.session(str(tenant_id)) as session:
                await session.execute(
                    update(HybridForecastRun)
                    .where(HybridForecastRun.id == run_id)
                    .values(
                        status="failed",
                        error=str(exc)[:1000],
                        completed_at=datetime.now(UTC),
                    )
                )
        except Exception:
            log.exception("hybrid.run.failed.persist_error", run_id=str(run_id))
        await _emit(
            realtime,
            RealtimeEvent(
                type=EVENT_FORECAST_FAILED,
                tenant_id=tenant_id,
                industry=industry_code,
                data={"run_id": str(run_id), "error": str(exc)[:300]},
            ),
        )
