"""Wrap an adjusted ForecastQuantiles into named scenarios for the UI.

Scenarios use the existing P10/P50/P90 as anchors:
    Pessimistic ← P10
    Base        ← P50
    Optimistic  ← P90

Each scenario carries a plain-English narrative referencing the strongest
trend drivers, so the dashboard can show *why* the band is where it is.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from sanket_ml.fusion.trend_scorer import TrendScore
from sanket_ml.models.base import ForecastQuantiles


@dataclass(slots=True)
class Scenario:
    name: str                     # "pessimistic" | "base" | "optimistic"
    label: str                    # display label
    horizon_total: float          # sum of demand over horizon (the scenario's headline number)
    weekly_path: list[float]      # demand per week
    narrative: str
    drivers: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class ScenarioEngine:
    @staticmethod
    def build(
        adjusted: ForecastQuantiles,
        trend: TrendScore,
        industry: str,
    ) -> dict[str, Scenario]:
        # Aggregate across all series to give a portfolio-level scenario
        # (per-SKU breakdown stays in the per-series quantile output).
        n_series = max(len(set(adjusted.unique_id)), 1)
        per_step_p10 = np.array(adjusted.p10).reshape(n_series, -1).sum(axis=0)
        per_step_p50 = np.array(adjusted.p50).reshape(n_series, -1).sum(axis=0)
        per_step_p90 = np.array(adjusted.p90).reshape(n_series, -1).sum(axis=0)

        pessimistic = Scenario(
            name="pessimistic",
            label="Worst case",
            horizon_total=float(per_step_p10.sum()),
            weekly_path=[float(x) for x in per_step_p10],
            narrative=ScenarioEngine._narrate_pessimistic(trend, industry),
            drivers=ScenarioEngine._negative_drivers(trend.drivers),
        )
        base = Scenario(
            name="base",
            label="Most likely",
            horizon_total=float(per_step_p50.sum()),
            weekly_path=[float(x) for x in per_step_p50],
            narrative=ScenarioEngine._narrate_base(trend, industry),
            drivers=trend.drivers[:4],
        )
        optimistic = Scenario(
            name="optimistic",
            label="Best case",
            horizon_total=float(per_step_p90.sum()),
            weekly_path=[float(x) for x in per_step_p90],
            narrative=ScenarioEngine._narrate_optimistic(trend, industry),
            drivers=ScenarioEngine._positive_drivers(trend.drivers),
        )
        return {
            "pessimistic": pessimistic,
            "base": base,
            "optimistic": optimistic,
        }

    # ── narratives (plain language for non-technical users) ──────────────────
    @staticmethod
    def _narrate_base(trend: TrendScore, industry: str) -> str:
        if -0.05 <= trend.score <= 0.05:
            return (
                "Right now the market isn't pushing demand up or down, so we expect "
                "sales to follow your usual pattern. This is the number to plan around."
            )
        if trend.score > 0:
            strength = "a little stronger" if trend.score < 0.3 else "much stronger"
            return (
                f"Demand looks {strength} than usual, so we've nudged the forecast up. "
                "This is our best single guess — the number to plan around."
            )
        strength = "a little softer" if trend.score > -0.3 else "much softer"
        return (
            f"Demand looks {strength} than usual, so we've eased the forecast down. "
            "This is our best single guess — the number to plan around."
        )

    @staticmethod
    def _narrate_pessimistic(trend: TrendScore, industry: str) -> str:
        neg = [d for d in trend.drivers if d["score"] < 0]
        if not neg:
            return (
                "Our cautious estimate if sales come in slow. Nothing major is dragging "
                "demand down right now — this just allows for normal ups and downs. "
                "Plan near here if you want to avoid over-buying."
            )
        top = neg[0]
        return (
            f"Our cautious estimate if sales come in slow. The biggest thing pulling "
            f"demand down right now is {ScenarioEngine._friendly(top)}. "
            "Plan near here if you want to avoid over-buying."
        )

    @staticmethod
    def _narrate_optimistic(trend: TrendScore, industry: str) -> str:
        pos = [d for d in trend.drivers if d["score"] > 0]
        if not pos:
            return (
                "Our upside estimate if things go well. Nothing is strongly boosting "
                "demand right now — this just allows for normal upside. "
                "Keep a little extra stock if you want to catch a good month."
            )
        top = pos[0]
        return (
            f"Our upside estimate if the good momentum holds. The biggest boost right "
            f"now is {ScenarioEngine._friendly(top)}. "
            "Make sure you have enough stock to catch the upside."
        )

    # Turn a raw driver (e.g. reddit:r/streetwear) into "Streetwear (Reddit)".
    @staticmethod
    def _friendly(driver: dict) -> str:
        key = str(driver.get("series_key", "")).lower()
        known = {
            "reddit:r/femalefashionadvice": "women's fashion chat",
            "reddit:r/malefashionadvice": "men's fashion chat",
            "reddit:r/streetwear": "streetwear interest",
            "reddit:r/sneakers": "sneaker interest",
        }
        if key in known:
            name = known[key]
        else:
            name = (
                key.split(":")[-1].replace("r/", "").replace("_", " ").replace("-", " ")
            ) or "market interest"
        source = (
            "Reddit" if key.startswith("reddit:")
            else "Google searches" if key.startswith("google:")
            else "Pinterest" if key.startswith("pinterest:")
            else "TikTok" if key.startswith("tiktok:")
            else "the news" if key.startswith("rss:") or "news" in key
            else "shoppers"
        )
        return f"{name} ({source})"

    @staticmethod
    def _negative_drivers(drivers: list[dict]) -> list[dict]:
        return [d for d in drivers if d["score"] < 0][:4]

    @staticmethod
    def _positive_drivers(drivers: list[dict]) -> list[dict]:
        return [d for d in drivers if d["score"] > 0][:4]
