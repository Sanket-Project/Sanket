from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import IndustryCode, TrendSignalKind, TrendSignalSource


class TrendSignalOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID | None
    industry: IndustryCode
    source: TrendSignalSource
    kind: TrendSignalKind
    series_key: str
    category_tags: list[str]
    sku_tags: list[str]
    region: str | None
    raw_value: Decimal | None
    normalized_score: Decimal
    confidence: Decimal
    captured_at: datetime
    payload: dict[str, Any]


class TrendScoreOut(BaseModel):
    industry: IndustryCode
    score: float = Field(..., ge=-1.0, le=1.0, description="Aggregate trend score")
    volatility: float = Field(..., ge=0.0, le=1.0, description="Source disagreement")
    sample_count: int
    by_kind: dict[str, float]
    drivers: list[dict[str, Any]]
    demand_factors: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Weather/macro signals that modify demand but aren't product trends",
    )
    horizon_days: int
    as_of: datetime


class HybridForecastRequest(BaseModel):
    sku_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    # None = inherit the effective horizon (industry archetype default, or the
    # tenant's IndustryProfile.custom_horizon_weeks override). Resolved in the
    # router before the run row is created so downstream always sees a concrete int.
    horizon_weeks: int | None = Field(default=None, ge=1, le=52)
    include_alerts: bool = True
    inventory_overrides: dict[str, dict] = Field(default_factory=dict)


class ScenarioOut(BaseModel):
    name: str
    label: str
    horizon_total: float
    weekly_path: list[float]
    narrative: str
    drivers: list[dict[str, Any]]


class HybridForecastSeriesOut(BaseModel):
    sku_id: str
    sku_code: str | None = None
    ds: list[str]
    p10: list[float]
    p50: list[float]
    p90: list[float]
    baseline_p50: list[float]


class ForecastExplanationDriverOut(BaseModel):
    source: str
    kind: str
    series_key: str
    contribution_pct: float = Field(
        description="Additive contribution to the median forecast change; 0.03 means +3%."
    )
    signal_score: float = Field(default=0.0, ge=-1.0, le=1.0)


class ForecastExplanationOut(BaseModel):
    median_shift_pct: float
    band_change_pct: float
    baseline_band_mean: float
    adjusted_band_mean: float
    drivers: list[ForecastExplanationDriverOut] = Field(default_factory=list)


class HybridForecastOut(BaseModel):
    industry: IndustryCode
    horizon_weeks: int
    generated_at: datetime
    trend: TrendScoreOut
    explanation: ForecastExplanationOut
    scenarios: dict[str, ScenarioOut]
    series: list[HybridForecastSeriesOut]
    alerts_generated: int = 0
    data_source: str = Field(
        default="trained",
        description=(
            "Source of the baseline, as reported by the ML service: 'trained' (a "
            "tenant-trained artifact) or 'chronos_zero_shot' / 'timesfm_zero_shot'. "
            "There is no synthetic baseline: if the ML service is unavailable the run fails."
        ),
    )
    #: Weekly calendar of the series dates and where the baseline's history ended.
    calendar: str | None = None
    history_end: date | None = None
    #: Active SKUs the baseline did not forecast, with the reason.
    omitted: list[dict] = Field(default_factory=list)


class HybridRunAccepted(BaseModel):
    """202 response when an async hybrid forecast run is enqueued."""

    run_id: uuid.UUID
    status: str = "pending"


class HybridRunStatus(BaseModel):
    """Poll target for an async hybrid forecast run."""

    run_id: uuid.UUID
    status: str = Field(description="pending | running | completed | failed")
    horizon_weeks: int
    industry: IndustryCode
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    result: HybridForecastOut | None = None
