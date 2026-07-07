from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import mlflow
import pandas as pd
import structlog

from sanket_ml.config import MLSettings, get_ml_settings
from sanket_ml.data.censoring import correct_censored_demand
from sanket_ml.data.loader import ExternalSignalLoader, HistoricalSalesLoader, TimeSeriesPanel
from sanket_ml.data.splits import holdout_split
from sanket_ml.models.base import BaseForecaster, ForecastQuantiles
from sanket_ml.models.ensemble import StackedEnsemble
from sanket_ml.registry import ModelSpec, stack_for
from sanket_ml.registry import get as registry_get
from sanket_ml.training.backtest import (
    BacktestMetrics,
    align_truth,
    evaluate,
    walk_forward_backtest,
)

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TrainConfig:
    tenant_id: uuid.UUID
    industry: str
    horizon_weeks: int
    history_weeks: int = 156
    freq: str = "W"
    model_names: list[str] | None = None
    n_cv_splits: int = 3
    fit_ensemble: bool = True


@dataclass
class TrainResult:
    tenant_id: uuid.UUID
    industry: str
    run_name: str
    started_at: datetime
    completed_at: datetime | None = None
    panel_n_series: int = 0
    panel_n_obs: int = 0
    per_model_metrics: dict[str, list[BacktestMetrics]] = field(default_factory=dict)
    ensemble_weights: dict[str, float] = field(default_factory=dict)
    holdout_metrics: dict[str, BacktestMetrics] = field(default_factory=dict)
    artifact_path: str | None = None
    censoring_report: dict = field(default_factory=dict)


class TrainingPipeline:
    """Implements the 5-stage methodology:

    Stage 1 — DATA: load + feature engineering + intermittency classification.
    Stage 2 — PRE-TRAIN: load zero-shot foundation models, optionally fine-tune.
    Stage 3 — DOMAIN FIT: fit deep + GBT specialists per industry.
    Stage 4 — STACK: fit weighted ensemble on validation pinball loss.
    Stage 5 — VALIDATE: walk-forward backtest + final holdout report.
    """

    def __init__(self, settings: MLSettings | None = None) -> None:
        self.settings = settings or get_ml_settings()
        self.sales_loader = HistoricalSalesLoader(self.settings)
        self.signal_loader = ExternalSignalLoader(self.settings)
        mlflow.set_tracking_uri(self.settings.model_registry_uri)
        mlflow.set_experiment(self.settings.experiment_name)

    # ── Stage 1 ──
    def load_panel(self, cfg: TrainConfig) -> tuple[TimeSeriesPanel, pd.DataFrame]:
        log.info("stage1.load.start", tenant=str(cfg.tenant_id), industry=cfg.industry)
        panel = self.sales_loader.load(
            tenant_id=cfg.tenant_id,
            industry=cfg.industry,
            freq=cfg.freq,
        )
        static = self.sales_loader.load_skus_metadata(cfg.tenant_id, cfg.industry)
        # Promo feature engineering: promo_intensity = promo_flag * (1 + markdown_pct)
        # Models that accept covariates use this; others ignore the extra column.
        if hasattr(panel, "data") and isinstance(panel.data, pd.DataFrame):
            df = panel.data
            if "promo_flag" in df.columns and "markdown_pct" in df.columns:
                df["promo_intensity"] = (
                    df["promo_flag"].fillna(False).astype(float)
                    * (1 + df["markdown_pct"].fillna(0).clip(0, 1))
                )
            elif "promo_flag" in df.columns:
                df["promo_intensity"] = df["promo_flag"].fillna(False).astype(float)
            # Zero-fraction flag for ADIDA routing
            if "y" in df.columns:
                # Intermittency is a property of *true* demand, so classify on the
                # raw (pre-censoring) series before any unconstraining happens.
                zero_frac = df.groupby("unique_id")["y"].apply(lambda s: (s == 0).mean())
                df["is_intermittent"] = df["unique_id"].map(zero_frac > 0.5).fillna(False)
        log.info("stage1.load.done", n_series=panel.n_series, n_obs=panel.n_obs)
        return panel, static

    def correct_demand(self, panel: TimeSeriesPanel) -> tuple[TimeSeriesPanel, dict]:
        """Unconstrain censored (stockout) demand before training. No-ops when
        disabled or when there is nothing safe to correct."""
        if not self.settings.censoring_enabled or panel.n_obs == 0:
            return panel, {}
        result = correct_censored_demand(
            panel.data,
            availability_threshold=self.settings.censoring_availability_threshold,
            heuristic_when_missing=self.settings.censoring_heuristic_when_missing,
            local_window=self.settings.censoring_local_window,
            seasonal_period=self.settings.censoring_seasonal_period,
            min_history=self.settings.censoring_min_history,
        )
        corrected = TimeSeriesPanel(
            data=result.data,
            tenant_id=panel.tenant_id,
            industry=panel.industry,
            freq=panel.freq,
            start=panel.start,
            end=panel.end,
        )
        return corrected, result.report.as_dict()

    # ── Stage 2 ──
    def init_models(self, cfg: TrainConfig) -> list[BaseForecaster]:
        names = cfg.model_names or [s.name for s in stack_for(cfg.industry)]
        models: list[BaseForecaster] = []
        for n in names:
            spec: ModelSpec = registry_get(n)
            try:
                model = spec.factory(horizon=cfg.horizon_weeks, freq=cfg.freq)
                models.append(model)
                log.info("stage2.model.init", name=n, family=spec.family)
            except Exception as exc:
                log.error("stage2.model.init.failed", name=n, error=str(exc))
        return models

    # ── Stage 3 ──
    def fit_models(
        self,
        train: pd.DataFrame,
        models: list[BaseForecaster],
        static: pd.DataFrame | None,
    ) -> list[BaseForecaster]:
        fitted: list[BaseForecaster] = []
        for m in models:
            try:
                log.info("stage3.fit.start", model=m.name)
                m.fit(train, static_features=static)
                fitted.append(m)
                log.info("stage3.fit.done", model=m.name)
            except Exception as exc:
                log.error("stage3.fit.failed", model=m.name, error=str(exc))
        return fitted

    # ── Stage 4 ──
    def fit_ensemble(
        self,
        models: list[BaseForecaster],
        val_df: pd.DataFrame,
        horizon: int,
    ) -> tuple[StackedEnsemble, list[ForecastQuantiles]]:
        forecasts: list[ForecastQuantiles] = []
        for m in models:
            try:
                fc = m.predict(horizon=horizon)
                forecasts.append(fc)
            except Exception as exc:
                log.error("stage4.predict.failed", model=m.name, error=str(exc))
        if not forecasts:
            raise RuntimeError("Stage 4: no model produced forecasts; cannot fit ensemble.")
        ens = StackedEnsemble().fit(val_df, forecasts)
        return ens, forecasts

    # ── Stage 5 ──
    def backtest(
        self,
        panel: pd.DataFrame,
        models: list[BaseForecaster],
        cfg: TrainConfig,
    ) -> dict[str, list[BacktestMetrics]]:
        all_metrics: dict[str, list[BacktestMetrics]] = {}
        for m in models:
            try:
                metrics = walk_forward_backtest(
                    panel,
                    forecaster_factory=lambda mm=m: mm.__class__(
                        horizon=cfg.horizon_weeks, freq=cfg.freq
                    ),
                    horizon=cfg.horizon_weeks,
                    n_splits=cfg.n_cv_splits,
                    freq=cfg.freq,
                )
                all_metrics[m.name] = metrics
            except Exception as exc:
                log.error("stage5.backtest.failed", model=m.name, error=str(exc))
        return all_metrics

    # ── Orchestration ──
    def run(self, cfg: TrainConfig) -> TrainResult:
        result = TrainResult(
            tenant_id=cfg.tenant_id,
            industry=cfg.industry,
            run_name=f"{cfg.industry}-{datetime.now(tz=UTC).strftime('%Y%m%d-%H%M%S')}",
            started_at=datetime.now(tz=UTC),
        )

        with mlflow.start_run(run_name=result.run_name):
            mlflow.log_params({
                "tenant_id": str(cfg.tenant_id),
                "industry": cfg.industry,
                "horizon_weeks": cfg.horizon_weeks,
                "history_weeks": cfg.history_weeks,
                "freq": cfg.freq,
            })

            # Stage 1
            panel, static = self.load_panel(cfg)
            result.panel_n_series = panel.n_series
            result.panel_n_obs = panel.n_obs
            if panel.n_series == 0:
                log.warning("pipeline.no_data", tenant=str(cfg.tenant_id))
                result.completed_at = datetime.now(tz=UTC)
                return result

            # Stage 1b — unconstrain censored (stockout) demand
            panel, censoring_report = self.correct_demand(panel)
            result.censoring_report = censoring_report
            if censoring_report:
                mlflow.log_params({
                    "censoring_mode": censoring_report.get("detection_mode", "none"),
                })
                mlflow.log_metric(
                    "censoring.obs_imputed", censoring_report.get("n_obs_imputed", 0)
                )
                mlflow.log_metric(
                    "censoring.series_corrected",
                    censoring_report.get("n_series_corrected", 0),
                )
                mlflow.log_metric(
                    "censoring.units_added", censoring_report.get("units_added", 0.0)
                )

            df = panel.data.copy()
            df.attrs["industry"] = cfg.industry

            # Train / holdout
            train_df, holdout_df = holdout_split(df, horizon=cfg.horizon_weeks, freq=cfg.freq)
            train_df.attrs["industry"] = cfg.industry

            # Stage 2 — initialize
            models = self.init_models(cfg)

            # Stage 3 — fit
            fitted = self.fit_models(train_df, models, static)
            if not fitted:
                raise RuntimeError("No models fitted; aborting pipeline.")

            # Stage 4 — ensemble on validation = holdout window (or its first half)
            val_df = holdout_df.copy()
            ensemble, forecasts = self.fit_ensemble(fitted, val_df, cfg.horizon_weeks)
            result.ensemble_weights = ensemble.weights

            # Per-model holdout metrics
            for fc in forecasts:
                yt, aligned = align_truth(val_df, fc)
                if len(yt) == 0:
                    continue
                result.holdout_metrics[fc.model_name] = evaluate(yt, aligned)

            # Ensemble holdout
            ens_fc = ensemble.predict(forecasts)
            yt, ens_aligned = align_truth(val_df, ens_fc)
            if len(yt) > 0:
                result.holdout_metrics["ensemble"] = evaluate(yt, ens_aligned, model_name="ensemble")

            # Stage 5 — walk-forward backtest
            if cfg.n_cv_splits > 0:
                bt = self.backtest(train_df, fitted, cfg)
                result.per_model_metrics = bt

            # Log to MLflow
            for name, metric in result.holdout_metrics.items():
                mlflow.log_metric(f"holdout.{name}.wape", metric.wape)
                mlflow.log_metric(f"holdout.{name}.coverage_80", metric.coverage_80)
                mlflow.log_metric(f"holdout.{name}.pinball_p50", metric.pinball_p50)
            for name, w in result.ensemble_weights.items():
                mlflow.log_metric(f"ensemble.weight.{name}", w)

            # Persist
            artifact_dir = (
                self.settings.artifact_root
                / str(cfg.tenant_id)
                / cfg.industry
                / result.run_name
            )
            artifact_dir.mkdir(parents=True, exist_ok=True)
            for m in fitted:
                m.save(str(artifact_dir / f"{m.name}.joblib"))
            import joblib
            joblib.dump(ensemble, str(artifact_dir / "ensemble.joblib"))
            result.artifact_path = str(artifact_dir)
            mlflow.log_artifacts(str(artifact_dir))

            result.completed_at = datetime.now(tz=UTC)
            log.info(
                "pipeline.done",
                run=result.run_name,
                duration_s=(result.completed_at - result.started_at).total_seconds(),
            )
        return result
