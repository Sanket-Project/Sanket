"""Planning calendar & rules.

Persisted in ``Tenant.settings["planning"]`` (JSONB — no dedicated table). Set
during onboarding's calendar step and editable later from settings.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PlanningCalendar(BaseModel):
    fiscal_year_start_month: int = Field(1, ge=1, le=12)
    period: Literal["weekly", "monthly"] = "weekly"
    week_start: Literal["monday", "sunday"] = "monday"
    horizon_weeks: int = Field(13, ge=1, le=104)


class PlanningRules(BaseModel):
    min_history_weeks: int = Field(8, ge=0, le=520)
    default_service_level: float = Field(0.95, ge=0.50, le=0.999)
    review_cadence: Literal["weekly", "biweekly", "monthly"] = "weekly"


class PlanningConfig(BaseModel):
    calendar: PlanningCalendar = Field(default_factory=PlanningCalendar)
    rules: PlanningRules = Field(default_factory=PlanningRules)


class PlanningConfigUpdate(BaseModel):
    """Partial update — omitted sections are left unchanged."""

    calendar: PlanningCalendar | None = None
    rules: PlanningRules | None = None


def load_planning_config(settings: dict[str, Any] | None) -> PlanningConfig:
    if not settings or "planning" not in settings:
        return PlanningConfig()
    try:
        return PlanningConfig.model_validate(settings["planning"])
    except Exception:  # noqa: BLE001
        return PlanningConfig()
