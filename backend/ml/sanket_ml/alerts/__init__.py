"""Cross-industry shortage alert engine.

Computes shortage risk by combining:
  • Current inventory position (on_hand / safety_stock)
  • Probabilistic demand (P10/P50/P90 from the hybrid forecaster)
  • External trend momentum (TrendScore)

Industry-specific defaults live in `alert_rules.DEFAULT_RULES`.
"""
from __future__ import annotations

from sanket_ml.alerts.alert_publisher import AlertPublisher
from sanket_ml.alerts.alert_rules import DEFAULT_RULES, AlertRule
from sanket_ml.alerts.shortage_detector import (
    InventoryPosition,
    ShortageAlert,
    ShortageDetector,
)

__all__ = [
    "AlertPublisher",
    "AlertRule",
    "DEFAULT_RULES",
    "InventoryPosition",
    "ShortageAlert",
    "ShortageDetector",
]
