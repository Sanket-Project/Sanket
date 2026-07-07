from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import IndustryCode, SignalType


class IndustryOut(BaseModel):
    model_config = {"from_attributes": True}

    code: IndustryCode
    display_name: str
    default_horizon_weeks: int
    granularity_dimensions: list[str]
    required_signal_types: list[SignalType]
    sku_attribute_schema: dict[str, Any]
    forecast_models: list[str]
    optimization_models: list[str]
    audit_level: str


class IndustryProfileOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    industry: IndustryCode
    custom_horizon_weeks: int | None
    custom_signal_types: list[SignalType]
    model_overrides: dict[str, Any]
    feature_flags: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class FocusProfileIn(BaseModel):
    """A tenant's focus watchlist — the narrowed area of interest within its
    archetype (e.g. a rice mill's ["rice", "paddy"] inside agrocenter)."""

    keywords: list[str] = Field(default_factory=list, max_length=50)
    categories: list[str] = Field(default_factory=list, max_length=50)


class IndustryProfileUpdate(BaseModel):
    """Partial update for the active industry's tenant profile. Omitted fields
    are left unchanged; pass an empty FocusProfileIn to clear the watchlist."""

    custom_horizon_weeks: int | None = Field(default=None, ge=1, le=52)
    custom_signal_types: list[SignalType] | None = None
    focus: FocusProfileIn | None = None


class IndustryActivateIn(BaseModel):
    """Set the tenant's primary/active industry (must be one it's licensed for)."""

    code: IndustryCode


class EffectiveIndustryConfigOut(BaseModel):
    """The archetype defaults merged with the tenant's profile overrides —
    what the dashboard/onboarding wizard reads back."""

    code: str
    display_name: str
    effective_horizon: int
    active_signal_types: list[str]
    focus: FocusProfileIn
    feature_flags: dict[str, Any]
