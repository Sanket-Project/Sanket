"""Competitor price signal connector.

In live mode (SERPAPI_KEY set): queries Google Shopping for category baskets
per industry and computes a price index vs. baseline.
In demo/offline mode: emits a seeded random walk so dashboards stay populated.

Score interpretation:
  +1 = competitors significantly cheaper than baseline (you are expensive)
  -1 = competitors significantly more expensive (you are cheap / strong margin)
"""

from __future__ import annotations

import hashlib
import math
import random
from datetime import UTC, datetime
from typing import Any

import structlog

from app.services.external_signals.base import SignalConnector, SignalSample, clip

log = structlog.get_logger(__name__)

# Industry → list of (search_term, category_tags, baseline_price_usd)
INDUSTRY_BASKETS: dict[str, list[tuple[str, list[str], float]]] = {
    "fashion": [
        ("men's running shoes", ["footwear", "performance"], 85.0),
        ("women's winter jacket", ["outerwear", "seasonal"], 120.0),
        ("denim jeans", ["bottoms", "staple"], 60.0),
    ],
    "electronics": [
        ("wireless earbuds", ["audio", "accessory"], 95.0),
        ("gaming laptop 15 inch", ["computing", "gaming"], 1100.0),
        ("smart home hub", ["iot", "home"], 75.0),
    ],
    "pharma": [
        ("vitamin d3 supplement", ["supplement", "otc"], 18.0),
        ("allergy relief tablets", ["otc", "seasonal"], 14.0),
        ("cold flu medicine", ["otc", "seasonal"], 12.0),
    ],
    "agrocenter": [
        ("npk fertilizer 50kg", ["fertilizer", "input"], 45.0),
        ("herbicide concentrate", ["pesticide", "input"], 38.0),
        ("poultry feed 25kg", ["feed", "livestock"], 22.0),
    ],
}

SERPAPI_URL = "https://serpapi.com/search.json"


class CompetitorPriceConnector(SignalConnector):
    """Fetches competitor prices via SerpAPI (Google Shopping) or synthetic fallback."""

    name = "competitor_price"

    def __init__(self) -> None:
        import os

        self._api_key: str | None = os.environ.get("SERPAPI_KEY")

    async def fetch(self, industry: str) -> list[SignalSample]:
        basket = INDUSTRY_BASKETS.get(industry)
        if not basket:
            return []
        if self._api_key:
            return await self._fetch_live(industry, basket)
        return []

    async def _fetch_live(
        self,
        industry: str,
        basket: list[tuple[str, list[str], float]],
    ) -> list[SignalSample]:
        samples: list[SignalSample] = []
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as client:
                for term, tags, baseline in basket:
                    try:
                        resp = await client.get(
                            SERPAPI_URL,
                            params={
                                "engine": "google_shopping",
                                "q": term,
                                "api_key": self._api_key,
                                "num": 10,
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        sample = self._parse_serpapi(data, term, tags, baseline, industry)
                        if sample:
                            samples.append(sample)
                    except Exception as exc:
                        log.warning("competitor_price.item.failed", term=term, error=str(exc))
        except Exception as exc:
            log.warning("competitor_price.live.failed", industry=industry, error=str(exc))
            return []
        return samples

    def _parse_serpapi(
        self,
        data: dict[str, Any],
        term: str,
        tags: list[str],
        baseline: float,
        industry: str,
    ) -> SignalSample | None:
        results = data.get("shopping_results", [])
        if not results:
            return None
        prices = []
        for r in results[:8]:
            raw = r.get("price", "")
            cleaned = raw.replace("$", "").replace(",", "").strip()
            try:
                prices.append(float(cleaned))
            except ValueError:
                pass
        if not prices:
            return None
        avg_price = sum(prices) / len(prices)
        # Positive score = competitors cheaper = pricing pressure on you
        pct_diff = (baseline - avg_price) / baseline
        score = clip(math.tanh(pct_diff * 3))
        return SignalSample(
            source="competitor_price",
            kind="commodity_price",
            series_key=f"competitor:{industry}:{term.replace(' ', '_')[:30]}",
            industry=industry,
            captured_at=datetime.now(UTC),
            raw_value=round(avg_price, 2),
            normalized_score=round(score, 4),
            confidence=0.80,
            category_tags=["competitor_price"] + tags,
            payload={
                "search_term": term,
                "avg_competitor_price": round(avg_price, 2),
                "baseline_price": baseline,
                "pct_diff": round(pct_diff * 100, 1),
                "n_results": len(prices),
            },
        )

    def _fetch_synthetic(
        self,
        industry: str,
        basket: list[tuple[str, list[str], float]],
    ) -> list[SignalSample]:
        return [self._synthetic_item(t, tags, b, industry) for t, tags, b in basket]

    def _synthetic_item(
        self,
        term: str,
        tags: list[str],
        baseline: float,
        industry: str,
    ) -> SignalSample:
        # Seeded so the same term always starts from the same point (stable demo).
        # MD5 here is a fast, stable hash used purely to derive a deterministic RNG
        # seed for synthetic demo data — it is not used for any security or integrity
        # purpose, so usedforsecurity=False is set explicitly (CWE-327 N/A).
        digest = hashlib.md5(f"{industry}:{term}".encode(), usedforsecurity=False).hexdigest()
        seed = int(digest, 16) % (2**32)
        rng = random.Random(seed + int(datetime.now(UTC).timestamp() / 3600))
        score = clip(rng.gauss(0, 0.3))
        return SignalSample(
            source="competitor_price",
            kind="commodity_price",
            series_key=f"competitor:{industry}:{term.replace(' ', '_')[:30]}",
            industry=industry,
            captured_at=datetime.now(UTC),
            raw_value=None,
            normalized_score=round(score, 4),
            confidence=0.35,
            category_tags=["competitor_price", "synthetic"] + tags,
            payload={"synthetic": True, "search_term": term, "baseline_price": baseline},
        )
