"""External market signal ingestion subsystem.

Pulls live signals from FRED (economic), Google Trends (search), Reddit (social).
Normalizes everything to a [-1, +1] momentum score and persists to `trend_signals`.
"""

from __future__ import annotations

from app.services.external_signals.signal_pipeline import (
    SignalIngestionPipeline,
    SignalSample,
)

__all__ = ["SignalIngestionPipeline", "SignalSample"]
