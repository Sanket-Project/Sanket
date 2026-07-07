"""FRED (Federal Reserve Economic Data) connector.

Pulls monthly economic indicators relevant to each SANKET industry:
- CPIAUCSL : Consumer Price Index (all urban consumers)
- PPIACO   : Producer Price Index (commodities)
- UNRATE   : Unemployment rate
- UMCSENT  : Consumer sentiment (University of Michigan)
- PCE      : Personal consumption expenditures

API: https://api.stlouisfed.org/fred/series/observations
Free tier: 120 req/min, requires API key (FRED_API_KEY env var).
If no API key is configured we emit a synthetic random-walk so downstream
fusion still has data in dev/demo.
"""

from __future__ import annotations

import os
import random
import statistics
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from app.services.external_signals.base import (
    SignalConnector,
    SignalSample,
    z_to_score,
)

log = structlog.get_logger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Industry → list of (series_id, weight, category_tags)
INDUSTRY_SERIES: dict[str, list[tuple[str, float, list[str]]]] = {
    "fashion": [
        ("UMCSENT", 1.0, ["consumer_sentiment"]),
        ("PCE", 0.8, ["consumption"]),
        ("UNRATE", -0.6, ["labor"]),
    ],
    "electronics": [
        ("PPIACO", -0.9, ["producer_price"]),
        ("UMCSENT", 0.7, ["consumer_sentiment"]),
        ("INDPRO", 0.8, ["industrial_production"]),
    ],
    "pharma": [
        ("CPIMEDSL", -0.7, ["medical_cpi"]),
        ("UNRATE", -0.4, ["labor"]),
        ("CPIAUCSL", -0.5, ["inflation"]),
    ],
    "agrocenter": [
        ("WPU01", -0.8, ["farm_products", "commodity"]),  # PPI: Farm Products
        ("PPIACO", -0.6, ["commodity_price"]),  # PPI: All Commodities
        ("UMCSENT", 0.5, ["consumer_sentiment"]),  # Rural demand proxy
    ],
}


class FredConnector(SignalConnector):
    name = "fred"

    def __init__(self, api_key: str | None = None, timeout_s: float = 8.0):
        self.api_key = api_key or os.environ.get("FRED_API_KEY")
        self.timeout_s = timeout_s

    async def fetch(self, industry: str) -> list[SignalSample]:
        series = INDUSTRY_SERIES.get(industry, [])
        if not series:
            return []
        if not self.api_key:
            return []

        out: list[SignalSample] = []
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            for series_id, weight, tags in series:
                try:
                    sample = await self._fetch_one(client, industry, series_id, weight, tags)
                    if sample:
                        out.append(sample)
                except Exception as exc:
                    log.warning("fred.fetch.failed", series=series_id, error=str(exc))
        return out

    async def _fetch_one(
        self,
        client: httpx.AsyncClient,
        industry: str,
        series_id: str,
        weight: float,
        tags: list[str],
    ) -> SignalSample | None:
        # Last 24 monthly observations gives us enough history for z-score
        params: dict[str, Any] = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 24,
        }
        r = await client.get(FRED_BASE, params=params)
        r.raise_for_status()
        obs = r.json().get("observations", [])
        values: list[float] = []
        for o in obs:
            v = o.get("value")
            if v in (None, "."):
                continue
            try:
                values.append(float(v))
            except (TypeError, ValueError):
                continue
        if len(values) < 4:
            return None

        latest = values[0]
        baseline = values[1:13] if len(values) >= 13 else values[1:]
        mean = statistics.mean(baseline)
        stdev = statistics.pstdev(baseline) or 1e-6
        z = (latest - mean) / stdev
        score = z_to_score(z * weight)  # apply directional weight

        captured = datetime.fromisoformat(obs[0]["date"]).replace(tzinfo=UTC)

        return SignalSample(
            source="fred",
            kind="economic_indicator",
            series_key=series_id,
            industry=industry,
            captured_at=captured,
            raw_value=latest,
            normalized_score=score,
            confidence=0.9,
            category_tags=tags,
            region="US",
            payload={
                "z_score": round(z, 4),
                "baseline_mean": round(mean, 4),
                "weight": weight,
                "history_n": len(values),
            },
        )

    def _synthetic(
        self,
        industry: str,
        series: list[tuple[str, float, list[str]]],
    ) -> list[SignalSample]:
        """When FRED_API_KEY is absent, fabricate plausible signals so the
        platform stays demoable. Real deployments must set FRED_API_KEY."""
        now = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        rng = random.Random(hash((industry, now.isoformat())) & 0xFFFFFFFF)
        out: list[SignalSample] = []
        for series_id, weight, tags in series:
            score = z_to_score(rng.gauss(0, 1) * weight)
            out.append(
                SignalSample(
                    source="fred",
                    kind="economic_indicator",
                    series_key=series_id,
                    industry=industry,
                    captured_at=now,
                    raw_value=None,
                    normalized_score=score,
                    confidence=0.4,
                    category_tags=tags,
                    region="US",
                    payload={"synthetic": True, "weight": weight},
                )
            )
        return out
