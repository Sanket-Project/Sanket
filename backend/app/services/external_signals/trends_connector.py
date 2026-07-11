"""Google Trends connector — search-volume momentum per product category.

Uses `pytrends` (unofficial Google Trends client). No API key required, but
the endpoint is rate-limited and unstable so we fail soft: any error returns
synthetic samples and is logged.
"""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime

import structlog

from app.services.external_signals.base import (
    SignalConnector,
    SignalSample,
    z_to_score,
)

log = structlog.get_logger(__name__)


# Industry → list of (keyword, category_tags)
INDUSTRY_KEYWORDS: dict[str, list[tuple[str, list[str]]]] = {
    # Keyed to the tenant's actual catalog categories so "trending" reflects
    # products they stock (Tops / Bottoms / Footwear / Outerwear).
    "fashion": [
        ("oversized t-shirt", ["tops"]),
        ("slim fit jeans", ["bottoms"]),
        ("sneakers", ["footwear"]),
        ("cotton hoodie", ["outerwear"]),
        ("denim jacket", ["outerwear"]),
    ],
    "electronics": [
        ("oled tv", ["display", "tv"]),
        ("gaming laptop", ["computing", "gaming"]),
        ("wireless earbuds", ["audio", "accessory"]),
        ("smart home", ["iot", "home"]),
    ],
    "pharma": [
        ("flu vaccine", ["vaccine", "seasonal"]),
        ("vitamin d", ["supplement"]),
        ("allergy medicine", ["otc", "seasonal"]),
        ("cold medicine", ["otc", "seasonal"]),
    ],
    "agrocenter": [
        ("pesticide prices", ["pesticide", "input"]),
        ("fertilizer shortage", ["fertilizer", "commodity"]),
        ("animal feed cost", ["feed", "livestock"]),
        ("crop disease alert", ["plant_health", "seasonal"]),
    ],
    "hardware": [
        ("cordless drill", ["power_tool", "tool"]),
        ("circular saw", ["power_tool", "tool"]),
        ("pvc pipe", ["plumbing", "material"]),
        ("safety helmet", ["safety_gear"]),
    ],
}


class GoogleTrendsConnector(SignalConnector):
    name = "google_trends"

    def __init__(self, timeout_s: float = 12.0, hl: str = "en-US", tz: int = 360):
        self.timeout_s = timeout_s
        self.hl = hl
        self.tz = tz

    async def fetch(self, industry: str) -> list[SignalSample]:
        keywords = INDUSTRY_KEYWORDS.get(industry, [])
        if not keywords:
            return []
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._fetch_sync, industry, keywords),
                timeout=self.timeout_s,
            )
        except Exception as exc:
            log.warning("google_trends.fetch.failed", industry=industry, error=str(exc))
            return []

    def _fetch_sync(
        self,
        industry: str,
        keywords: list[tuple[str, list[str]]],
    ) -> list[SignalSample]:
        try:
            from pytrends.request import TrendReq
        except ImportError:
            log.info("google_trends.pytrends.missing — emitting synthetic")
            return []

        pytrend = TrendReq(hl=self.hl, tz=self.tz, timeout=(4, 8))
        out: list[SignalSample] = []
        now = datetime.now(UTC)

        # Trend lookups must be done in small batches (Google limits to 5 kw / call)
        for batch_start in range(0, len(keywords), 5):
            batch = keywords[batch_start : batch_start + 5]
            kw_list = [kw for kw, _tags in batch]
            try:
                pytrend.build_payload(kw_list=kw_list, timeframe="today 3-m", geo="")
                df = pytrend.interest_over_time()
            except Exception as exc:
                log.warning("google_trends.batch.failed", kw=kw_list, error=str(exc))
                continue
            if df is None or df.empty:
                continue

            for kw, tags in batch:
                if kw not in df.columns:
                    continue
                series = df[kw].astype(float).tolist()
                if len(series) < 8:
                    continue
                latest = series[-1]
                baseline = series[-13:-1] if len(series) >= 13 else series[:-1]
                mean = sum(baseline) / len(baseline)
                var = sum((x - mean) ** 2 for x in baseline) / max(len(baseline) - 1, 1)
                std = var**0.5 or 1e-6
                z = (latest - mean) / std
                score = z_to_score(z, scale=2.0)
                out.append(
                    SignalSample(
                        source="google_trends",
                        kind="search_interest",
                        series_key=f"google:{kw.replace(' ', '_')}",
                        industry=industry,
                        captured_at=now,
                        raw_value=latest,
                        normalized_score=score,
                        confidence=0.75,
                        category_tags=tags,
                        region="WW",
                        payload={
                            "keyword": kw,
                            "z_score": round(z, 4),
                            "baseline_mean": round(mean, 4),
                            "window_n": len(series),
                        },
                    )
                )
        if not out:
            return []
        return out

    def _synthetic(
        self,
        industry: str,
        keywords: list[tuple[str, list[str]]],
    ) -> list[SignalSample]:
        now = datetime.now(UTC)
        rng = random.Random(hash((industry, now.date().isoformat())) & 0xFFFFFFFF)
        out: list[SignalSample] = []
        for kw, tags in keywords:
            z = rng.gauss(0, 1.1)
            out.append(
                SignalSample(
                    source="google_trends",
                    kind="search_interest",
                    series_key=f"google:{kw.replace(' ', '_')}",
                    industry=industry,
                    captured_at=now,
                    raw_value=None,
                    normalized_score=z_to_score(z, scale=2.0),
                    confidence=0.35,
                    category_tags=tags,
                    region="WW",
                    payload={"synthetic": True, "keyword": kw, "z_score": round(z, 4)},
                )
            )
        return out
