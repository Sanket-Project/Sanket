from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pandas as pd
import structlog
from sqlalchemy import create_engine, text

from sanket_ml.config import MLSettings, get_ml_settings
from sanket_ml.data.loader import HistoricalSalesLoader
from sanket_ml.models.base import BaseForecaster, ForecastQuantiles
from sanket_ml.models.ensemble import StackedEnsemble

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class InferenceResult:
    tenant_id: uuid.UUID
    industry: str
    run_id: uuid.UUID
    forecast: ForecastQuantiles


class InferenceService:
    """Loads a trained ensemble + per-model artifacts for a tenant/industry
    and writes forecasts to the forecast_results table."""

    def __init__(self, settings: MLSettings | None = None) -> None:
        self.settings = settings or get_ml_settings()
        self.loader = HistoricalSalesLoader(self.settings)
        self._engine = create_engine(self.settings.database_url, pool_pre_ping=True)

    def load_artifacts(self, artifact_dir: Path) -> tuple[list[BaseForecaster], StackedEnsemble]:
        models: list[BaseForecaster] = []
        ensemble_path = artifact_dir / "ensemble.joblib"
        if not ensemble_path.exists():
            raise FileNotFoundError(f"ensemble.joblib not found in {artifact_dir}")
        ensemble: StackedEnsemble = joblib.load(ensemble_path)
        for p in artifact_dir.glob("*.joblib"):
            if p.name == "ensemble.joblib":
                continue
            m = BaseForecaster.load(str(p))
            models.append(m)
        return models, ensemble

    def forecast(
        self,
        tenant_id: uuid.UUID,
        industry: str,
        artifact_dir: Path,
        horizon: int,
    ) -> InferenceResult:
        log.info("inference.start", tenant=str(tenant_id), industry=industry, horizon=horizon)
        models, ensemble = self.load_artifacts(artifact_dir)
        forecasts = [m.predict(horizon=horizon) for m in models]
        combined = ensemble.predict(forecasts)
        run_id = self._persist(tenant_id, industry, combined, horizon, models)
        log.info("inference.done", run_id=str(run_id), n_predictions=len(combined.unique_id))
        return InferenceResult(
            tenant_id=tenant_id,
            industry=industry,
            run_id=run_id,
            forecast=combined,
        )

    def _persist(
        self,
        tenant_id: uuid.UUID,
        industry: str,
        fc: ForecastQuantiles,
        horizon: int,
        models: Iterable[BaseForecaster],
    ) -> uuid.UUID:
        return self.persist_forecast(
            tenant_id=tenant_id,
            industry=industry,
            fc=fc,
            horizon=horizon,
            model_stack=[m.name for m in models],
        )

    def persist_forecast(
        self,
        *,
        tenant_id: uuid.UUID,
        industry: str,
        fc: ForecastQuantiles,
        horizon: int,
        model_stack: list[str],
        run_metadata: dict | None = None,
    ) -> uuid.UUID:
        """Persist any ForecastQuantiles to forecast_runs + forecast_results.

        Public entry point so zero-shot, stacked-ensemble, and ad-hoc
        forecasts all share the same audit trail and RLS-scoped write path.
        """
        import json
        run_id = uuid.uuid4()
        meta_json = json.dumps(run_metadata or {})
        with self._engine.begin() as conn:
            conn.execute(text("SET LOCAL app.current_tenant_id = :tid"), {"tid": str(tenant_id)})
            conn.execute(
                text(
                    """
                    INSERT INTO forecast_runs (
                        id, tenant_id, industry, model_stack, horizon_weeks,
                        granularity, status, started_at, completed_at, metrics
                    ) VALUES (
                        :id, :tenant_id, CAST(:industry AS industry_code), :model_stack, :horizon,
                        'weekly', 'completed', :started_at, :completed_at, CAST(:metrics AS jsonb)
                    )
                    """
                ),
                {
                    "id": str(run_id),
                    "tenant_id": str(tenant_id),
                    "industry": industry,
                    "model_stack": model_stack,
                    "horizon": horizon,
                    "started_at": datetime.now(tz=UTC),
                    "completed_at": datetime.now(tz=UTC),
                    "metrics": meta_json,
                },
            )
            df = fc.to_frame()
            df["tenant_id"] = str(tenant_id)
            df["run_id"] = str(run_id)
            df["forecast_date"] = pd.to_datetime(df["ds"]).dt.date
            df["created_at"] = datetime.now(tz=UTC)
            df_out = df[[
                "tenant_id", "run_id", "unique_id", "forecast_date",
                "p10", "p50", "p90", "model_name", "created_at",
            ]].rename(columns={"unique_id": "sku_id"})
            df_out.to_sql(
                "forecast_results",
                conn,
                if_exists="append",
                index=False,
                method="multi",
                chunksize=1000,
            )
        return run_id
