"""Forecast confidence scoring.

A p10/p50/p90 band already carries uncertainty, but nobody buys stock off a
percentile. Planners ask one question — *can I trust this number?* — and the
honest answer depends on things the band alone does not show: how much history
the model actually saw, how recent it is, how spiky the demand is, and how the
model scored against actuals last time.

This module turns those into a single 0–100 score with a band and, crucially,
the **reasons** behind it. A low score is not a failure to hide; it is the most
valuable output the system can produce ("52% — 9 weeks of history, demand is
intermittent"), because it tells the user what to fix.

The scorer is a pure function over :class:`ConfidenceFeatures` so it can be unit
tested without a database, and so the same rules apply whether the caller is the
decision engine, the API, or a WhatsApp digest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ConfidenceBand = Literal["high", "moderate", "low", "insufficient"]

# Weeks of history below which we refuse to claim the forecast is trustworthy at
# all. Two full seasons of weekly data is the point where seasonal models stop
# guessing; 12 weeks is the floor where a level+trend fit is even defined.
MIN_WEEKS_FOR_ANY_CONFIDENCE = 12
WEEKS_FOR_FULL_HISTORY_CREDIT = 104


@dataclass(frozen=True, slots=True)
class ConfidenceFeatures:
    """Everything the score is derived from. All fields optional but the more
    that are supplied the less the scorer has to be conservative."""

    #: Distinct weeks that contain at least one sales record for this series.
    history_weeks: int
    #: Fraction of those weeks with zero units sold — intermittency.
    zero_weeks_ratio: float = 0.0
    #: Days since the most recent sales record. Stale data ages out confidence.
    days_since_last_sale: int | None = None
    #: Mean relative interval width across the horizon: (p90 − p10) / max(p50, 1).
    relative_interval_width: float | None = None
    #: Coefficient of variation of historical weekly demand.
    demand_cv: float | None = None
    #: Backtest WAPE (0–1+) from the most recent scored run, if any.
    backtest_wape: float | None = None
    #: Number of distinct models that agreed in the ensemble (fusion breadth).
    models_in_ensemble: int = 1
    #: Whether the forecast came from a zero-shot foundation model with no
    #: tenant-specific training. Useful, but worth an explicit haircut.
    zero_shot: bool = False


@dataclass(frozen=True, slots=True)
class ConfidenceScore:
    score: int  # 0–100
    band: ConfidenceBand
    reasons: list[str] = field(default_factory=list)
    #: Machine-readable deductions, `{"code": ..., "points": -12, "detail": ...}`.
    deductions: list[dict] = field(default_factory=list)

    @property
    def is_actionable(self) -> bool:
        """Whether a recommendation built on this forecast should auto-surface."""
        return self.band in ("high", "moderate")


def _band(score: int, history_weeks: int) -> ConfidenceBand:
    if history_weeks < MIN_WEEKS_FOR_ANY_CONFIDENCE:
        return "insufficient"
    if score >= 80:
        return "high"
    if score >= 60:
        return "moderate"
    return "low"


def score_confidence(f: ConfidenceFeatures) -> ConfidenceScore:
    """Score a forecast 0–100 and explain every point lost.

    Starts from 100 and deducts against each known weakness. Deductions are
    additive and clamped, rather than multiplicative, so the explanation stays
    readable: "100 − 20 (short history) − 15 (intermittent) = 65".
    """
    deductions: list[dict] = []
    reasons: list[str] = []

    def deduct(code: str, points: int, detail: str) -> None:
        if points <= 0:
            return
        deductions.append({"code": code, "points": -points, "detail": detail})
        reasons.append(detail)

    # ── History depth ────────────────────────────────────────────────────────
    weeks = max(0, int(f.history_weeks))
    if weeks < MIN_WEEKS_FOR_ANY_CONFIDENCE:
        deduct(
            "insufficient_history",
            60,
            f"Only {weeks} week{'s' if weeks != 1 else ''} of sales history "
            f"({MIN_WEEKS_FOR_ANY_CONFIDENCE} is the minimum for a fitted forecast)",
        )
    elif weeks < WEEKS_FOR_FULL_HISTORY_CREDIT:
        # Linear ramp: 12 weeks → −30, 104 weeks → 0.
        span = WEEKS_FOR_FULL_HISTORY_CREDIT - MIN_WEEKS_FOR_ANY_CONFIDENCE
        points = round(30 * (1 - (weeks - MIN_WEEKS_FOR_ANY_CONFIDENCE) / span))
        deduct(
            "short_history",
            points,
            f"{weeks} weeks of history — seasonal patterns need ~104 to be learned reliably",
        )

    # ── Intermittency ────────────────────────────────────────────────────────
    zeros = max(0.0, min(1.0, float(f.zero_weeks_ratio)))
    if zeros >= 0.6:
        deduct(
            "highly_intermittent",
            22,
            f"{zeros:.0%} of weeks had no sales — demand is sporadic, not a smooth series",
        )
    elif zeros >= 0.3:
        deduct("intermittent", 12, f"{zeros:.0%} of weeks had no sales")

    # ── Staleness ────────────────────────────────────────────────────────────
    if f.days_since_last_sale is not None:
        stale = int(f.days_since_last_sale)
        if stale > 90:
            deduct("stale_data", 25, f"No sales recorded for {stale} days — the feed may be broken")
        elif stale > 30:
            deduct("aging_data", 12, f"Most recent sale is {stale} days old")

    # ── Prediction interval width ────────────────────────────────────────────
    if f.relative_interval_width is not None:
        width = max(0.0, float(f.relative_interval_width))
        if width > 1.5:
            deduct(
                "wide_interval",
                20,
                f"The p10–p90 range spans {width:.0%} of the median — the model is unsure",
            )
        elif width > 0.9:
            deduct("moderate_interval", 10, f"p10–p90 range is {width:.0%} of the median")

    # ── Volatility ───────────────────────────────────────────────────────────
    if f.demand_cv is not None and f.demand_cv > 1.0:
        deduct(
            "volatile_demand",
            10,
            f"Week-to-week demand varies by {f.demand_cv:.1f}× its own mean",
        )

    # ── Measured accuracy beats every proxy above ────────────────────────────
    if f.backtest_wape is not None:
        wape = max(0.0, float(f.backtest_wape))
        if wape > 0.5:
            deduct("poor_backtest", 25, f"Last backtest was {wape:.0%} off actuals")
        elif wape > 0.3:
            deduct("fair_backtest", 12, f"Last backtest was {wape:.0%} off actuals")
        else:
            reasons.append(f"Backtested at {wape:.0%} error against actuals")

    # ── Model provenance ─────────────────────────────────────────────────────
    if f.zero_shot:
        deduct(
            "zero_shot",
            8,
            "Forecast came from a zero-shot model — no tenant-specific training yet",
        )
    if f.models_in_ensemble >= 3:
        reasons.append(f"{f.models_in_ensemble} models agreed in the ensemble")

    total_deduction = sum(-d["points"] for d in deductions)
    score = max(0, min(100, 100 - total_deduction))

    if not deductions:
        reasons.insert(0, "Long, dense, recent history with a tight prediction interval")

    return ConfidenceScore(
        score=score,
        band=_band(score, weeks),
        reasons=reasons,
        deductions=deductions,
    )


def features_from_series(
    *,
    weekly_units: list[float],
    days_since_last_sale: int | None = None,
    p10_sum: float | None = None,
    p50_sum: float | None = None,
    p90_sum: float | None = None,
    backtest_wape: float | None = None,
    models_in_ensemble: int = 1,
    zero_shot: bool = False,
) -> ConfidenceFeatures:
    """Derive :class:`ConfidenceFeatures` from a weekly demand series.

    ``weekly_units`` must already be bucketed to one value per calendar week,
    including explicit zeros for weeks with no sales — the zero ratio is the
    whole point and cannot be recovered from a sparse list.
    """
    n = len(weekly_units)
    zeros = sum(1 for v in weekly_units if v <= 0)
    mean = (sum(weekly_units) / n) if n else 0.0
    if n > 1 and mean > 0:
        variance = sum((v - mean) ** 2 for v in weekly_units) / (n - 1)
        cv: float | None = (variance**0.5) / mean
    else:
        cv = None

    width: float | None = None
    if p10_sum is not None and p90_sum is not None and p50_sum:
        width = (p90_sum - p10_sum) / max(abs(p50_sum), 1.0)

    return ConfidenceFeatures(
        history_weeks=n,
        zero_weeks_ratio=(zeros / n) if n else 1.0,
        days_since_last_sale=days_since_last_sale,
        relative_interval_width=width,
        demand_cv=cv,
        backtest_wape=backtest_wape,
        models_in_ensemble=models_in_ensemble,
        zero_shot=zero_shot,
    )
