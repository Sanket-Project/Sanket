from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.enums import AlertSeverity, AlertStatus, IndustryCode


class AlertRuleOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    industry: IndustryCode
    rule_name: str
    enabled: bool
    warn_coverage_days: Decimal
    critical_coverage_days: Decimal
    trend_weight: Decimal
    p90_weight: Decimal
    inventory_weight: Decimal
    cooldown_minutes: int
    notify_webhook: bool
    notify_websocket: bool


class AlertRuleUpdate(BaseModel):
    enabled: bool | None = None
    warn_coverage_days: Decimal | None = Field(None, gt=0, le=365)
    critical_coverage_days: Decimal | None = Field(None, gt=0, le=365)
    trend_weight: Decimal | None = Field(None, ge=0, le=1)
    p90_weight: Decimal | None = Field(None, ge=0, le=1)
    inventory_weight: Decimal | None = Field(None, ge=0, le=1)
    cooldown_minutes: int | None = Field(None, ge=1, le=1440)
    notify_webhook: bool | None = None
    notify_websocket: bool | None = None

    @model_validator(mode="after")
    def check_weights_sum(self) -> AlertRuleUpdate:
        weights = [self.trend_weight, self.p90_weight, self.inventory_weight]
        provided = [w for w in weights if w is not None]
        if len(provided) == 3:
            total = sum(provided)
            if not (Decimal("0.99") <= total <= Decimal("1.01")):
                raise ValueError(f"weights must sum to 1.0 (got {total})")
        return self


class ShortageAlertOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    industry: IndustryCode
    sku_id: uuid.UUID | None
    rule_id: uuid.UUID | None
    severity: AlertSeverity
    status: AlertStatus
    risk_score: Decimal
    coverage_days: Decimal | None
    p10_demand: Decimal | None
    p50_demand: Decimal | None
    p90_demand: Decimal | None
    trend_score: Decimal | None
    drivers: list[dict[str, Any]]
    title: str
    message: str
    fired_at: datetime
    acknowledged_by: uuid.UUID | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    resolution_note: str | None


class AlertAcknowledge(BaseModel):
    resolution_note: str | None = Field(None, max_length=1000)
