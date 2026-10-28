"""Zero-shot forecasting fallback.

Used by the inference API whenever a tenant has no trained artifact yet —
typically on first signup, or during onboarding while the first training
run is still queued. We use Amazon Chronos as the primary zero-shot model
because it is the smallest, fastest-to-load, and most consistently
calibrated of the foundation models we support. TimesFM is exposed as
an opt-in alternative for callers that want decoder-only behavior.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

import numpy as np
import pandas as pd
import structlog
import torch

from sanket_ml.config import MLSettings, get_ml_settings
from sanket_ml.data.calendar import CALENDAR, current_week_start
from sanket_ml.data.censoring import correct_censored_demand
from sanket_ml.data.loader import HistoricalSalesLoader, TimeSeriesPanel
from sanket_ml.models.base import ForecastQuantiles

log = structlog.get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# Pipeline loaders — kept module-level so the same pipeline can be shared
# across requests and across the per-model wrappers in models/foundation/.
# ──────────────────────────────────────────────────────────────────────────

_CHRONOS_PIPELINE = None
_TIMESFM_PIPELINE = None


def _resolve_device(settings: MLSettings) -> str:
    if settings.device == "cuda" and torch.cuda.is_available():
        return "cuda"
    if settings.device == "mps" and torch.backends.mps.is_available():
        return "mps"
    if settings.device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return "cpu"


def get_chronos_pipeline(settings: MLSettings | None = None):
    """Return a process-wide Chronos pipeline, loading it lazily on first call.

    Safe to call from FastAPI lifespan startup or from a request handler.
    Subsequent calls return the cached instance — the actual download/decode
    only happens once per process.
    """
    global _CHRONOS_PIPELINE
    if _CHRONOS_PIPELINE is not None:
        return _CHRONOS_PIPELINE
    settings = settings or get_ml_settings()
    try:
        from chronos import ChronosPipeline  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "chronos-forecasting is not installed in this venv. "
            "Run `pip install chronos-forecasting`."
        ) from exc

    device = _resolve_device(settings)
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    log.info("chronos.pipeline.loading", repo=settings.chronos_repo, device=device)
    _CHRONOS_PIPELINE = ChronosPipeline.from_pretrained(
        settings.chronos_repo,
        device_map=device,
        torch_dtype=dtype,
    )
    log.info("chronos.pipeline.ready", repo=settings.chronos_repo, device=device)
    return _CHRONOS_PIPELINE


def get_timesfm_pipeline(settings: MLSettings | None = None):
    """Return a process-wide TimesFM pipeline (optional, larger than Chronos)."""
    global _TIMESFM_PIPELINE
    if _TIMESFM_PIPELINE is not None:
        return _TIMESFM_PIPELINE
    settings = settings or get_ml_settings()
    try:
        import timesfm  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "timesfm is not installed in this venv. "
            "Run `pip install timesfm`."
        ) from exc
    backend = "gpu" if (torch.cuda.is_available() and settings.device != "cpu") else "cpu"
    log.info("timesfm.pipeline.loading", repo=settings.timesfm_repo, backend=backend)
    _TIMESFM_PIPELINE = timesfm.TimesFm(
        hparams=timesfm.TimesFmHparams(
            backend=backend,
            per_core_batch_size=32,
            horizon_len=128,
            context_len=512,
            num_layers=20,
        ),
        checkpoint=timesfm.TimesFmCheckpoint(huggingface_repo_id=settings.timesfm_repo),
    )
    log.info("timesfm.pipeline.ready")
    return _TIMESFM_PIPELINE


# ──────────────────────────────────────────────────────────────────────────
# ZeroShotForecaster
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ZeroShotResult:
    forecast: ForecastQuantiles
    source_model: str           # "chronos_zero_shot" | "timesfm_zero_shot"
    context_source: str         # "request" | "database"
    n_series: int
    used_observations: int
    #: Exclusive end of the history the model saw (a Monday, UTC).
    history_end: date | None = None
    first_forecast_week: date | None = None
    #: Active SKUs with no forecast: {sku_id, reason, observations}.
    omitted: list[dict] = field(default_factory=list)
    calendar: str = CALENDAR


# Frequency string → industry-default season length tokens for foundation models.
# Chronos doesn't take a freq arg, but TimesFM does (0=daily, 1=weekly, 2=monthly).
_INDUSTRY_FREQ = {
    "fashion": "W",
    "electronics": "W",
    "pharma": "W",
}


class ZeroShotForecaster:
    """Forecasts without any tenant-trained artifact.

    Two ways to supply context:
      1. `series_context` dict[sku_id, list[float]] passed in the request.
      2. Otherwise, pull last N weeks of historical_sales from PostgreSQL
         using the tenant's RLS-scoped loader.
    """

    def __init__(self, settings: MLSettings | None = None) -> None:
        self.settings = settings or get_ml_settings()
        self.loader = HistoricalSalesLoader(self.settings)

    # ── public API ────────────────────────────────────────────────────────
    def forecast(
        self,
        *,
        tenant_id: uuid.UUID,
        industry: str,
        horizon: int,
        model: Literal["chronos", "timesfm"] = "chronos",
        series_context: dict[str, list[float]] | None = None,
        freq: str | None = None,
        num_samples: int | None = None,
        history_end: date | None = None,
    ) -> ZeroShotResult:
        """Forecast every eligible SKU and report the ones that were not.

        ``history_end`` (a Monday) limits the model to history before that
        week — an explicit, leakage-free backtest. Without it the model sees
        every complete week up to now.
        """
        freq = freq or _INDUSTRY_FREQ.get(industry, "W")
        num_samples = num_samples or self.settings.zero_shot_num_samples
        min_obs = self.settings.zero_shot_min_observations
        if history_end is not None and history_end.weekday() != 0:
            raise ValueError(f"history_end must be a Monday (week start); got {history_end}")

        omitted: list[dict] = []
        # ── 1. Resolve context (request override > DB) ────────────────────
        if series_context:
            context_source = "request"
            context_arrays: dict[str, np.ndarray] = {
                str(k): np.asarray(v, dtype=np.float32)
                for k, v in series_context.items()
                if v and len(v) >= min_obs
            }
            if not context_arrays:
                raise ValueError(
                    "series_context contained no series with enough history "
                    f"(min={min_obs})."
                )
            # Request context carries no dates: its last value is taken to be the
            # last complete week, so the forecast starts with the current week.
            last_week = pd.Timestamp(current_week_start() - timedelta(weeks=1))
        else:
            context_source = "database"
            panel = self.loader.load(
                tenant_id=tenant_id,
                industry=industry,
                freq=freq,
                min_observations=min_obs,
                end=history_end,
            )
            if panel.n_series == 0:
                raise ValueError(_no_eligible_message(panel, min_obs))
            # Unconstrain censored (stockout) demand so the foundation model
            # conditions on true demand, not on stockout-driven zeros. Same
            # correction as the training path — keeps the two serving paths
            # consistent. No-ops when disabled or nothing is safe to correct.
            panel_df = panel.data
            if self.settings.censoring_enabled:
                panel_df = correct_censored_demand(
                    panel_df,
                    availability_threshold=self.settings.censoring_availability_threshold,
                    heuristic_when_missing=self.settings.censoring_heuristic_when_missing,
                    local_window=self.settings.censoring_local_window,
                    seasonal_period=self.settings.censoring_seasonal_period,
                    min_history=self.settings.censoring_min_history,
                ).data
            context_arrays = _panel_to_context_arrays(
                panel_df,
                max_series=self.settings.zero_shot_max_series,
                context_weeks=self.settings.zero_shot_default_context_weeks,
            )
            last_week = panel.last_week if panel.last_week is not None else panel_df["ds"].max()
            omitted = _omissions(panel, min_obs, set(context_arrays))

        used_obs = int(sum(len(v) for v in context_arrays.values()))

        # ── 2. Generate future timestamps ─────────────────────────────────
        # Continue the history's own buckets: weekly history is Monday-anchored
        # (calendar W-MON-UTC), so the first forecast week is the Monday after
        # the last observed one — never the pandas default Sunday.
        if freq == "W":
            first = last_week + pd.Timedelta(weeks=1)
            future_dates = pd.date_range(first, periods=horizon, freq="W-MON")
        else:
            offset = pd.tseries.frequencies.to_offset(freq)
            future_dates = pd.date_range(last_week + offset, periods=horizon, freq=freq)

        # ── 3. Dispatch to model ──────────────────────────────────────────
        if model == "chronos":
            quantiles = self._chronos_predict(context_arrays, horizon, num_samples)
            source = "chronos_zero_shot"
        elif model == "timesfm":
            quantiles = self._timesfm_predict(context_arrays, horizon, freq)
            source = "timesfm_zero_shot"
        else:
            raise ValueError(f"Unknown zero-shot model: {model}")

        p10, p50, p90 = quantiles  # each shape (N, H)

        # ── 4. Assemble ForecastQuantiles ─────────────────────────────────
        sku_ids = list(context_arrays.keys())
        uid_col: list[str] = []
        ds_col: list[pd.Timestamp] = []
        p10_flat: list[float] = []
        p50_flat: list[float] = []
        p90_flat: list[float] = []
        for i, sku in enumerate(sku_ids):
            for t in range(horizon):
                uid_col.append(sku)
                ds_col.append(future_dates[t])
                p10_flat.append(float(p10[i, t]))
                p50_flat.append(float(p50[i, t]))
                p90_flat.append(float(p90[i, t]))

        p50_arr = np.clip(np.asarray(p50_flat, dtype="float32"), 0.0, None)
        fc = ForecastQuantiles(
            unique_id=uid_col,
            ds=ds_col,
            p10=np.clip(np.asarray(p10_flat, dtype="float32"), 0.0, None),
            p50=p50_arr,
            p90=np.maximum(np.asarray(p90_flat, dtype="float32"), p50_arr),
            model_name=source,
        )

        log.info(
            "zero_shot.forecast.done",
            tenant=str(tenant_id),
            industry=industry,
            model=source,
            context_source=context_source,
            n_series=len(sku_ids),
            horizon=horizon,
            used_observations=used_obs,
        )
        return ZeroShotResult(
            forecast=fc,
            source_model=source,
            context_source=context_source,
            n_series=len(sku_ids),
            used_observations=used_obs,
            history_end=(last_week + pd.Timedelta(weeks=1)).date() if freq == "W" else None,
            first_forecast_week=pd.Timestamp(future_dates[0]).date() if horizon else None,
            omitted=omitted,
        )

    # ── per-model adapters ────────────────────────────────────────────────
    def _chronos_predict(
        self,
        context_arrays: dict[str, np.ndarray],
        horizon: int,
        num_samples: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        pipeline = get_chronos_pipeline(self.settings)
        ctx_tensors = [torch.tensor(v, dtype=torch.float32) for v in context_arrays.values()]
        by_series = max(1, int(self.settings.zero_shot_batch_size))
        by_paths = max(1, int(self.settings.zero_shot_max_sample_paths) // max(1, num_samples))
        size = min(by_series, by_paths)
        parts: list[np.ndarray] = []
        for start in range(0, len(ctx_tensors), size):
            forecast = pipeline.predict(
                ctx_tensors[start : start + size],
                prediction_length=horizon,
                num_samples=num_samples,
            )
            samples = (
                forecast.cpu().numpy() if isinstance(forecast, torch.Tensor) else np.asarray(forecast)
            )
            # Reduce the sample axis before retaining a batch. Otherwise a
            # 25k-SKU catalogue retains and concatenates every decoded sample,
            # defeating the bounded prediction batch's memory protection.
            parts.append(np.quantile(samples, [0.1, 0.5, 0.9], axis=1))
            del samples, forecast
        # Each reduced batch is (3, batch_series, horizon).
        p10, p50, p90 = np.concatenate(parts, axis=1)
        return p10, p50, p90

    def _timesfm_predict(
        self,
        context_arrays: dict[str, np.ndarray],
        horizon: int,
        freq: str,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        pipeline = get_timesfm_pipeline(self.settings)
        inputs = [v[-512:].astype(np.float32) for v in context_arrays.values()]
        freq_token = {"D": 0, "W": 1, "M": 2}.get(freq, 1)
        point_fc, quantile_fc = pipeline.forecast(
            inputs,
            freq=[freq_token] * len(inputs),
        )
        # quantile_fc shape: (N, horizon_internal, 10) — indices 0..9 → q 0.1..1.0
        h = min(horizon, point_fc.shape[1])
        p10 = quantile_fc[:, :h, 0] if quantile_fc.shape[2] > 0 else point_fc[:, :h]
        p50 = quantile_fc[:, :h, 4] if quantile_fc.shape[2] > 4 else point_fc[:, :h]
        p90 = quantile_fc[:, :h, 8] if quantile_fc.shape[2] > 8 else point_fc[:, :h]
        # Pad if internal horizon < requested
        if h < horizon:
            pad = horizon - h
            p10 = np.pad(p10, ((0, 0), (0, pad)), mode="edge")
            p50 = np.pad(p50, ((0, 0), (0, pad)), mode="edge")
            p90 = np.pad(p90, ((0, 0), (0, pad)), mode="edge")
        return p10, p50, p90


# ──────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────


def _omissions(panel: TimeSeriesPanel, min_obs: int, forecast_ids: set[str]) -> list[dict]:
    """Every active SKU not in the forecast, with the reason it is not."""
    out: list[dict] = []
    for sku_id in panel.active_sku_ids:
        if sku_id in forecast_ids:
            continue
        n = int(panel.observation_counts.get(sku_id, 0))
        if n == 0:
            reason = "no_sales_history"
        elif n < min_obs:
            reason = "insufficient_history"
        else:
            reason = "series_cap"
        out.append({"sku_id": sku_id, "reason": reason, "observations": n})
    return out


def _no_eligible_message(panel: TimeSeriesPanel, min_obs: int) -> str:
    unsold = sum(1 for s in panel.active_sku_ids if not panel.observation_counts.get(s))
    short = sum(1 for n in panel.observation_counts.values() if 0 < n < min_obs)
    return (
        f"Cannot zero-shot forecast: no SKU has the {min_obs} weekly observations this model "
        f"needs. {unsold} active SKU(s) have no sales history and {short} have fewer than "
        f"{min_obs} weeks. Zero-shot means no tenant-trained model, not no history — load "
        "more sales history first."
    )


def _panel_to_context_arrays(
    panel: pd.DataFrame,
    *,
    max_series: int,
    context_weeks: int,
) -> dict[str, np.ndarray]:
    """Convert a long-format panel into per-series 1D arrays sorted by ds.

    Trims each series to the last `context_weeks` observations. Series are
    ordered by total demand desc, then truncated to `max_series` to keep
    cold-start latency bounded.
    """
    if panel.empty:
        return {}

    totals = panel.groupby("unique_id")["y"].sum().sort_values(ascending=False)
    keep_ids = totals.head(max_series).index.astype(str).tolist()

    out: dict[str, np.ndarray] = {}
    for uid, g in panel[panel["unique_id"].isin(keep_ids)].groupby("unique_id", sort=False):
        arr = g.sort_values("ds")["y"].to_numpy(dtype=np.float32)
        if len(arr) >= context_weeks:
            arr = arr[-context_weeks:]
        out[str(uid)] = arr
    return out
