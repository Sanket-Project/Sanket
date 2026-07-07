from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ── Event type constants (keep in sync with WebhookEventType in models/webhook.py) ──
EVENT_FORECAST_PROGRESS = "forecast.run.progress"
EVENT_FORECAST_COMPLETED = "forecast.run.completed"
EVENT_FORECAST_FAILED = "forecast.run.failed"
EVENT_SIGNAL_VALIDATED = "signal.validated"
EVENT_BATCH_RELEASED = "pharma_batch.released"
EVENT_BATCH_RECALLED = "pharma_batch.recalled"
EVENT_USAGE_QUOTA = "usage.quota_warning"
EVENT_SALE_CREATED = "sale.created"


class RealtimeEvent(BaseModel):
    """Envelope for everything we push over WebSocket or webhooks."""

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    type: str
    tenant_id: uuid.UUID
    industry: str | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    data: dict[str, Any] = Field(default_factory=dict)

    def channel(self) -> str:
        """Redis pub/sub channel name for this event."""
        return f"sanket:tenant:{self.tenant_id}"

    def to_wire(self) -> dict[str, Any]:
        d = self.model_dump(mode="json")
        return d


class ForecastProgressData(BaseModel):
    run_id: uuid.UUID
    stage: Literal["data", "fit", "ensemble", "validate", "persist"]
    step: int
    total_steps: int
    message: str = ""


class SignalValidatedData(BaseModel):
    signal_id: uuid.UUID
    signal_type: str
    validator_user_id: uuid.UUID | None = None


class BatchReleasedData(BaseModel):
    batch_id: uuid.UUID
    lot_number: str
    released_by: uuid.UUID
    cold_chain_required: bool


class UsageQuotaData(BaseModel):
    meter: str
    used: float
    limit: float
    pct: float  # 0..1
    severity: Literal["warning", "exceeded"]


class SaleCreatedData(BaseModel):
    sale_id: uuid.UUID
    sku_id: uuid.UUID
    units_sold: int
    gross_revenue: float | None = None
    net_revenue: float | None = None
    channel: str = "unknown"
    sale_time: datetime
