"""Per-industry alert thresholds + composite weighting.

These defaults are conservative — tenants can override via `alert_rules` table.

Coverage thresholds (days of inventory at current demand rate):
  • Retail/Fashion: warn at 14 days, critical at 7 days
  • Electronics:    warn at 10 days, critical at 5 days
  • Pharma:         warn at 30 days, critical at 14 days (long lead times)

Risk weighting (sum to 1.0):
  • inventory_weight — how much "low coverage" drives the risk score
  • p90_weight       — how much demand uncertainty matters
  • trend_weight     — how much external momentum factors in
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AlertRule:
    industry: str
    warn_coverage_days: float
    critical_coverage_days: float
    inventory_weight: float = 0.30
    p90_weight: float = 0.40
    trend_weight: float = 0.30
    cooldown_minutes: int = 60
    enabled: bool = True

    def validate(self) -> None:
        total = self.inventory_weight + self.p90_weight + self.trend_weight
        if not (0.99 <= total <= 1.01):
            raise ValueError(
                f"weights must sum to 1.0 (got {total:.4f}) for industry={self.industry}"
            )
        if self.critical_coverage_days >= self.warn_coverage_days:
            raise ValueError(
                "critical_coverage_days must be < warn_coverage_days"
            )


DEFAULT_RULES: dict[str, AlertRule] = {
    "fashion": AlertRule(
        industry="fashion",
        warn_coverage_days=14.0,
        critical_coverage_days=7.0,
        inventory_weight=0.25,
        p90_weight=0.40,
        trend_weight=0.35,  # fashion is most trend-sensitive
        cooldown_minutes=60,
    ),
    "electronics": AlertRule(
        industry="electronics",
        warn_coverage_days=10.0,
        critical_coverage_days=5.0,
        inventory_weight=0.35,
        p90_weight=0.40,
        trend_weight=0.25,
        cooldown_minutes=45,
    ),
    "pharma": AlertRule(
        industry="pharma",
        warn_coverage_days=30.0,
        critical_coverage_days=14.0,
        inventory_weight=0.40,  # inventory dominates due to GxP/cold-chain constraints
        p90_weight=0.40,
        trend_weight=0.20,
        cooldown_minutes=120,
    ),
}


for _r in DEFAULT_RULES.values():
    _r.validate()
