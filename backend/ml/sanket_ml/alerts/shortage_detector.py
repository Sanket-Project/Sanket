"""Compute shortage alerts from inventory + hybrid forecast + trend score.

The detector takes pure-Python inputs (so it works in unit tests and ML
pipelines alike) and returns `ShortageAlert` objects. Persisting them to
the DB and emitting realtime/webhook fan-out is the caller's job — see
`AlertPublisher`.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from sanket_ml.alerts.alert_rules import DEFAULT_RULES, AlertRule
from sanket_ml.fusion.trend_scorer import TrendScore


@dataclass(slots=True)
class InventoryPosition:
    sku_id: str
    sku_code: str
    on_hand_units: float
    inbound_units: float = 0.0            # PO units arriving within lead time
    safety_stock_units: float = 0.0
    lead_time_days: float = 14.0
    name: str | None = None


@dataclass(slots=True)
class ShortageAlert:
    sku_id: str
    sku_code: str
    industry: str
    severity: str                    # 'info' | 'warning' | 'critical'
    risk_score: float                # [0, 1]
    coverage_days: float
    p10_demand: float
    p50_demand: float
    p90_demand: float
    trend_score: float
    title: str
    message: str
    drivers: list[dict] = field(default_factory=list)
    fired_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "sku_id": self.sku_id,
            "sku_code": self.sku_code,
            "industry": self.industry,
            "severity": self.severity,
            "risk_score": round(self.risk_score, 4),
            "coverage_days": round(self.coverage_days, 2),
            "p10_demand": round(self.p10_demand, 2),
            "p50_demand": round(self.p50_demand, 2),
            "p90_demand": round(self.p90_demand, 2),
            "trend_score": round(self.trend_score, 4),
            "title": self.title,
            "message": self.message,
            "drivers": self.drivers,
            "fired_at": self.fired_at.isoformat(),
        }


class ShortageDetector:
    def __init__(self, rule: AlertRule | None = None):
        self._explicit_rule = rule

    def rule_for(self, industry: str) -> AlertRule:
        if self._explicit_rule:
            return self._explicit_rule
        return DEFAULT_RULES.get(industry, DEFAULT_RULES["electronics"])

    def evaluate(
        self,
        industry: str,
        inventory: InventoryPosition,
        p10_demand: float,
        p50_demand: float,
        p90_demand: float,
        trend: TrendScore,
        horizon_days: int = 30,
    ) -> ShortageAlert | None:
        """Return a ShortageAlert if risk crosses the warn threshold, else None.

        Demand values are *daily* (units/day). Coverage = effective_supply / p50.
        """
        rule = self.rule_for(industry)
        if not rule.enabled:
            return None

        effective_supply = max(inventory.on_hand_units + inventory.inbound_units, 0.0)
        # Avoid div-by-zero when demand is intermittent
        daily_p50 = max(p50_demand, 1e-6)
        coverage_days = effective_supply / daily_p50

        # ── 3-factor risk score (each in [0,1], weighted) ───────────────────
        # 1. Inventory factor: 1.0 when coverage = 0, 0.0 when coverage ≥ warn × 1.5
        warn_ref = rule.warn_coverage_days
        inv_factor = max(0.0, min(1.0, 1.0 - coverage_days / (warn_ref * 1.5)))

        # 2. P90 demand factor: how much upper-band exceeds supply
        upper_demand = p90_demand * horizon_days
        if effective_supply > 0:
            p90_factor = max(0.0, min(1.0, (upper_demand - effective_supply) / max(upper_demand, 1.0)))
        else:
            p90_factor = 1.0

        # 3. Trend factor: positive trend in demand is BAD for shortage risk
        # because demand is rising. We map (-1, +1) → (0, 1).
        trend_factor = max(0.0, min(1.0, (trend.score + 1.0) / 2.0))

        risk_score = (
            rule.inventory_weight * inv_factor
            + rule.p90_weight * p90_factor
            + rule.trend_weight * trend_factor
        )

        severity = self._severity_from(rule, coverage_days, risk_score)
        if severity == "info":
            return None  # below WARN threshold — skip

        title, message = self._compose_message(
            inventory=inventory,
            industry=industry,
            severity=severity,
            coverage_days=coverage_days,
            p90_demand=p90_demand,
            trend=trend,
            horizon_days=horizon_days,
        )

        return ShortageAlert(
            sku_id=inventory.sku_id,
            sku_code=inventory.sku_code,
            industry=industry,
            severity=severity,
            risk_score=risk_score,
            coverage_days=coverage_days,
            p10_demand=p10_demand,
            p50_demand=p50_demand,
            p90_demand=p90_demand,
            trend_score=trend.score,
            title=title,
            message=message,
            drivers=self._top_drivers(trend, inv_factor, p90_factor, trend_factor),
        )

    @staticmethod
    def _severity_from(
        rule: AlertRule,
        coverage_days: float,
        risk_score: float,
    ) -> str:
        if coverage_days <= rule.critical_coverage_days or risk_score >= 0.75:
            return "critical"
        if coverage_days <= rule.warn_coverage_days or risk_score >= 0.50:
            return "warning"
        return "info"

    @staticmethod
    def _compose_message(
        inventory: InventoryPosition,
        industry: str,
        severity: str,
        coverage_days: float,
        p90_demand: float,
        trend: TrendScore,
        horizon_days: int,
    ) -> tuple[str, str]:
        sev_word = "CRITICAL" if severity == "critical" else "WARNING"
        title = f"{sev_word}: {inventory.sku_code} — {coverage_days:.1f} days of cover"

        # Reference the strongest driver if there is one
        driver_clause = ""
        if trend.drivers:
            top = trend.drivers[0]
            direction = "tailwind" if top["score"] > 0 else "headwind"
            driver_clause = (
                f" Top external {direction}: {top['source']}/{top['series_key']} "
                f"({top['score']:+.2f})."
            )

        msg = (
            f"{industry.capitalize()} SKU {inventory.sku_code} has "
            f"{inventory.on_hand_units:.0f} on hand "
            f"(+{inventory.inbound_units:.0f} inbound) vs. "
            f"P90 daily demand {p90_demand:.1f} units. "
            f"At the upper-band rate, supply runs out in "
            f"{coverage_days * (p90_demand / max(p90_demand, 1e-6)):.1f} days."
            f"{driver_clause}"
        )
        return title, msg

    @staticmethod
    def _top_drivers(
        trend: TrendScore,
        inv_factor: float,
        p90_factor: float,
        trend_factor: float,
    ) -> list[dict]:
        out: list[dict] = [
            {
                "factor": "inventory_coverage",
                "contribution": round(inv_factor, 4),
                "interpretation": "low" if inv_factor > 0.5 else "ok",
            },
            {
                "factor": "p90_demand_pressure",
                "contribution": round(p90_factor, 4),
                "interpretation": "upper-band exceeds supply" if p90_factor > 0.3 else "manageable",
            },
            {
                "factor": "external_trend",
                "contribution": round(trend_factor, 4),
                "interpretation": "rising demand signals" if trend_factor > 0.55 else "neutral/falling signals",
            },
        ]
        out.extend(trend.drivers[:3])
        return out

    def scan_portfolio(
        self,
        industry: str,
        positions: Iterable[InventoryPosition],
        per_sku_demand: dict[str, tuple[float, float, float]],
        trend: TrendScore,
        horizon_days: int = 30,
    ) -> list[ShortageAlert]:
        """Convenience: evaluate every SKU in `positions` against per-SKU demand."""
        alerts: list[ShortageAlert] = []
        for pos in positions:
            demand = per_sku_demand.get(pos.sku_id) or per_sku_demand.get(pos.sku_code)
            if demand is None:
                continue
            p10, p50, p90 = demand
            alert = self.evaluate(
                industry=industry,
                inventory=pos,
                p10_demand=p10,
                p50_demand=p50,
                p90_demand=p90,
                trend=trend,
                horizon_days=horizon_days,
            )
            if alert:
                alerts.append(alert)
        return alerts
