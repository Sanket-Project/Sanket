"""Aggregate raw external signals into a single trend score + volatility metric.

A "trend score" is a single number in [-1, +1]:
   +1 = strong tailwind  →  lift demand
   -1 = strong headwind  →  depress demand

A "signal volatility" is in [0, 1]:
    0 = sources all agree → tighten the band
    1 = sources disagree   → widen the band

The aggregation uses confidence-weighted means and a kind-weighted mix so that
hard economic data (FRED) and softer social buzz can be tuned independently
per industry.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class SignalRecord:
    """Minimal signal shape consumed by TrendScorer.

    Mirrors the `trend_signals` row, decoupled from SQLAlchemy so the scorer
    is usable from training scripts + the API path.
    """

    source: str
    kind: str
    series_key: str
    industry: str
    normalized_score: float  # [-1, +1]
    confidence: float  # [0, 1]
    captured_at: datetime
    category_tags: list[str] = field(default_factory=list)


# Signal kinds that represent *what is trending in the market* (products,
# styles, search/social momentum) — these headline the "Trending" panel.
PRODUCT_TREND_KINDS: frozenset[str] = frozenset(
    {"search_interest", "social_buzz", "news_sentiment"}
)
# Signal kinds that *modify* demand but aren't a product trend (weather, macro,
# commodity prices) — shown separately as "Demand factors".
DEMAND_FACTOR_KINDS: frozenset[str] = frozenset({"economic_indicator", "commodity_price"})


@dataclass(slots=True)
class TrendScore:
    score: float  # [-1, +1]
    volatility: float  # [0, 1]
    sample_count: int
    by_kind: dict[str, float]
    drivers: list[dict]  # top trending products (search/social/news)
    horizon_days: int
    demand_factors: list[dict] = field(default_factory=list)  # weather/macro context


# Per-industry kind weights — how much each signal *type* contributes
# to the overall trend score. Tunable per tenant via alert_rules in future.
DEFAULT_KIND_WEIGHTS: dict[str, dict[str, float]] = {
    # Fashion: visual + social signals dominate; trade press (BoF, Vogue, WWD)
    # now feeds news_sentiment — lifted from 0.05 to 0.15 to reflect real data.
    "fashion": {
        "social_buzz": 0.40,  # Reddit, Pinterest, TikTok, Instagram
        "search_interest": 0.25,  # Google Trends
        "news_sentiment": 0.20,  # RSS: BoF, Vogue, WWD, Hypebeast (was 0.05)
        "economic_indicator": 0.15,  # FRED (was 0.20)
    },
    # Electronics: trade press (Verge, TechCrunch) is now a real signal source.
    "electronics": {
        "search_interest": 0.35,  # Google Trends
        "economic_indicator": 0.30,  # FRED (was 0.35)
        "social_buzz": 0.20,  # Reddit, Pinterest, TikTok
        "news_sentiment": 0.15,  # RSS: Verge, TechCrunch, Ars Technica (was 0.10)
    },
    # Pharma: regulatory/clinical news is the dominant leading indicator;
    # RSS feeds from FiercePharma + STAT News are high-quality signals.
    "pharma": {
        "news_sentiment": 0.35,  # RSS: FiercePharma, STAT, Pharma-Tech (was 0.30)
        "economic_indicator": 0.35,  # FRED
        "search_interest": 0.20,  # Google Trends (was 0.25)
        "social_buzz": 0.10,  # Reddit
    },
}


class TrendScorer:
    def __init__(
        self,
        kind_weights: dict[str, dict[str, float]] | None = None,
        recency_half_life_days: float = 14.0,
    ):
        self.kind_weights = kind_weights or DEFAULT_KIND_WEIGHTS
        self.recency_half_life_days = recency_half_life_days

    def score(
        self,
        industry: str,
        signals: Iterable[SignalRecord],
        as_of: datetime | None = None,
        horizon_days: int = 90,
    ) -> TrendScore:
        sigs = [s for s in signals if s.industry == industry]
        if not sigs:
            return TrendScore(
                score=0.0,
                volatility=0.0,
                sample_count=0,
                by_kind={},
                drivers=[],
                horizon_days=horizon_days,
            )

        as_of = as_of or max(s.captured_at for s in sigs)
        kind_w = self.kind_weights.get(industry, {})

        # ── per-kind weighted aggregation ───────────────────────────────────
        kind_sum: dict[str, float] = {}
        kind_wt: dict[str, float] = {}
        kind_values: dict[str, list[float]] = {}
        contributions: list[tuple[float, SignalRecord, float]] = []

        for s in sigs:
            recency_w = self._recency_weight(s.captured_at, as_of)
            w = max(s.confidence, 0.0) * recency_w
            if w <= 0:
                continue
            kind_sum.setdefault(s.kind, 0.0)
            kind_wt.setdefault(s.kind, 0.0)
            kind_values.setdefault(s.kind, [])
            kind_sum[s.kind] += s.normalized_score * w
            kind_wt[s.kind] += w
            kind_values[s.kind].append(s.normalized_score)
            contributions.append((abs(s.normalized_score) * w, s, w))

        by_kind: dict[str, float] = {
            k: kind_sum[k] / kind_wt[k] for k in kind_sum if kind_wt[k] > 0
        }

        # ── industry-weighted blend across kinds ───────────────────────────
        total_w = sum(kind_w.get(k, 0.0) for k in by_kind) or 1.0
        score = sum(by_kind[k] * kind_w.get(k, 0.0) for k in by_kind) / total_w
        score = max(-1.0, min(1.0, score))

        # ── volatility = average within-kind stdev, normalized ──────────────
        volatility = self._volatility(kind_values)

        # ── drivers — split product trends from demand-modifying factors ────
        # Rank by absolute weighted contribution, but keep only the single
        # strongest record per series_key so the same signal can't appear
        # multiple times in the panel.
        contributions.sort(key=lambda t: t[0], reverse=True)

        def _top_by_series(kinds: frozenset[str], limit: int) -> list[dict]:
            seen: set[str] = set()
            out: list[dict] = []
            for _contrib, s, w in contributions:
                if s.kind not in kinds or s.series_key in seen:
                    continue
                # Exclude granular regional demand signals from the overall top drivers
                if s.series_key.startswith("trends:regional_demand:"):
                    continue
                seen.add(s.series_key)
                out.append(
                    {
                        "source": s.source,
                        "kind": s.kind,
                        "series_key": s.series_key,
                        "score": round(s.normalized_score, 4),
                        "weight": round(w, 4),
                        "captured_at": s.captured_at.isoformat(),
                    }
                )
                if len(out) >= limit:
                    break
            return out

        # "drivers" now means trending products (search/social/news); weather
        # and macro move to demand_factors so they inform but don't headline.
        drivers = _top_by_series(PRODUCT_TREND_KINDS, limit=6)
        demand_factors = _top_by_series(DEMAND_FACTOR_KINDS, limit=4)

        return TrendScore(
            score=round(score, 4),
            volatility=round(volatility, 4),
            sample_count=len(sigs),
            by_kind={k: round(v, 4) for k, v in by_kind.items()},
            drivers=drivers,
            horizon_days=horizon_days,
            demand_factors=demand_factors,
        )

    def _recency_weight(self, captured_at: datetime, as_of: datetime) -> float:
        if self.recency_half_life_days <= 0:
            return 1.0
        if captured_at.tzinfo is None or as_of.tzinfo is None:
            # naive comparison fallback
            delta = as_of.replace(tzinfo=None) - captured_at.replace(tzinfo=None)
        else:
            delta = as_of - captured_at
        # Fractional days so the naive and tz-aware paths decay identically.
        delta_days: float = abs(delta.total_seconds()) / 86400.0
        return 0.5 ** (delta_days / self.recency_half_life_days)

    def _volatility(self, kind_values: dict[str, list[float]]) -> float:
        """Average within-kind sample stdev, scaled into [0, 1]."""
        if not kind_values:
            return 0.0
        stdevs: list[float] = []
        for values in kind_values.values():
            if len(values) < 2:
                continue
            mean = sum(values) / len(values)
            var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
            stdevs.append(var**0.5)
        if not stdevs:
            return 0.0
        avg_std = sum(stdevs) / len(stdevs)
        # signal scores live in [-1, +1] so the max possible stdev is ~1.0
        return max(0.0, min(1.0, avg_std))
