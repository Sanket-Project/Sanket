from __future__ import annotations

import uuid
from datetime import datetime
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


class HybridForecastOut(BaseModel):
    industry: IndustryCode
    horizon_weeks: int
    generated_at: datetime
    trend: TrendScoreOut
    explanation: dict[str, float]
    scenarios: dict[str, ScenarioOut]
    series: list[HybridForecastSeriesOut]
    alerts_generated: int = 0
    data_source: str = Field(
        default="trained",
        description=(
            "Source of the baseline. One of: 'trained' (real ML artifact), "
            "'zero_shot' (Chronos fallback), 'synthetic' (ML API unreachable)."
        ),
    )


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
