"""Weather signal connector using Open-Meteo (free, no API key required).

Fetches 7-day temperature and precipitation forecasts for global and nationwide Indian
relevant locations, normalising deviations from seasonal baseline into [-1, +1] scores.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime
from typing import Any

import structlog

from app.services.external_signals.base import SignalConnector, SignalSample, clip

log = structlog.get_logger(__name__)

# Blended Industry → list of (label, lat, lon) locations including Nationwide India
INDUSTRY_LOCATIONS: dict[str, list[tuple[str, float, float]]] = {
    "fashion": [
        # Global Fashion capitals
        ("NYC", 40.71, -74.01),
        ("London", 51.51, -0.13),
        ("Milan", 45.46, 9.19),
        # India Fashion hubs (South, West, North, East)
        ("Bangalore", 12.97, 77.59),
        ("Mumbai", 19.08, 72.88),
        ("Delhi NCR", 28.61, 77.21),
        ("Kolkata", 22.57, 88.36),
    ],
    "electronics": [
        # Global tech hubs
        ("San Jose", 37.34, -121.89),
        ("Shenzhen", 22.54, 114.06),
        ("Seoul", 37.57, 126.98),
        # India Tech hubs
        ("Bangalore", 12.97, 77.59),
        ("Hyderabad", 17.39, 78.49),
        ("Chennai", 13.08, 80.27),
        ("Pune", 18.52, 73.85),
    ],
    "pharma": [
        # Global pharma hubs
        ("Boston", 42.36, -71.06),
        ("Basel", 47.56, 7.59),
        # India Pharma hubs
        ("Hyderabad", 17.39, 78.49),
        ("Mumbai", 19.08, 72.88),
        ("Ahmedabad", 23.02, 72.57),
        ("Siddipet", 18.10, 78.85),
    ],
    "agrocenter": [
        # Global agri hubs
        ("Iowa City", 41.66, -91.53),
        ("Sao Paulo", -23.55, -46.63),
        # India Agri hubs (covering various zones)
        ("Punjab", 31.15, 75.34),
        ("Siddipet", 18.10, 78.85),
        ("Lucknow", 26.85, 80.95),
        ("Bhopal", 23.25, 77.41),
        ("Patna", 25.59, 85.14),
    ],
}

# Blended Seasonal temperature baselines (°C) per month for each location key
SEASONAL_TEMP_BASELINE: dict[str, list[float]] = {
    # Global
    "NYC": [0, 2, 7, 13, 18, 23, 26, 25, 21, 15, 9, 2],
    "London": [5, 5, 8, 11, 14, 17, 19, 19, 16, 12, 8, 5],
    "Milan": [3, 5, 9, 14, 18, 22, 25, 24, 20, 14, 8, 4],
    "San Jose": [9, 11, 12, 14, 16, 19, 21, 21, 20, 17, 13, 9],
    "Shenzhen": [14, 15, 18, 22, 26, 28, 29, 29, 27, 24, 20, 15],
    "Seoul": [-3, 0, 5, 13, 18, 22, 25, 26, 21, 14, 6, -1],
    "Boston": [-1, 1, 5, 11, 17, 22, 25, 24, 20, 14, 8, 1],
    "Basel": [2, 3, 7, 12, 16, 19, 22, 21, 17, 12, 6, 3],
    "Iowa City": [-7, -5, 2, 10, 17, 22, 25, 24, 19, 12, 4, -4],
    "Sao Paulo": [23, 23, 23, 21, 19, 18, 17, 18, 19, 21, 22, 23],
    # India (Localized grid)
    "Bangalore": [21, 23, 26, 28, 27, 24, 23, 23, 23, 23, 22, 20],
    "Mumbai": [24, 25, 27, 29, 31, 29, 27, 27, 27, 29, 27, 25],
    "Delhi NCR": [14, 17, 22, 28, 33, 34, 31, 30, 29, 26, 20, 15],
    "Kolkata": [20, 23, 28, 31, 31, 30, 29, 29, 29, 28, 24, 20],
    "Hyderabad": [23, 25, 29, 32, 33, 29, 27, 26, 26, 26, 24, 22],
    "Chennai": [25, 26, 28, 31, 33, 33, 31, 30, 30, 29, 27, 25],
    "Pune": [21, 23, 27, 30, 31, 26, 24, 24, 24, 26, 23, 21],
    "Ahmedabad": [20, 23, 28, 32, 33, 31, 28, 27, 28, 29, 25, 21],
    "Siddipet": [22, 25, 29, 32, 33, 29, 27, 26, 26, 26, 23, 21],
    "Punjab": [13, 15, 21, 28, 33, 36, 35, 34, 33, 28, 21, 14],
    "Lucknow": [15, 18, 24, 30, 34, 34, 31, 30, 29, 27, 21, 16],
    "Bhopal": [18, 21, 26, 32, 35, 31, 26, 25, 26, 26, 22, 19],
    "Patna": [16, 19, 25, 31, 33, 32, 30, 30, 29, 27, 22, 17],
}

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


class WeatherConnector(SignalConnector):
    """Fetches weather forecasts from Open-Meteo and emits deviation signals."""

    name = "weather"

    async def fetch(self, industry: str) -> list[SignalSample]:
        locations = INDUSTRY_LOCATIONS.get(industry)
        if not locations:
            return []
        try:
            import httpx

            samples: list[SignalSample] = []
            async with httpx.AsyncClient(timeout=10.0) as client:
                for label, lat, lon in locations:
                    try:
                        resp = await client.get(
                            OPEN_METEO_URL,
                            params={
                                "latitude": lat,
                                "longitude": lon,
                                "daily": "temperature_2m_max,precipitation_sum",
                                "forecast_days": 7,
                                "timezone": "auto",
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        sample = self._parse(data, label, industry)
                        if sample:
                            samples.append(sample)
                    except Exception as exc:
                        log.warning("weather.location.failed", label=label, error=str(exc))
            return samples
        except ImportError:
            return []
        except Exception as exc:
            log.warning("weather.fetch.failed", industry=industry, error=str(exc))
            return []

    def _parse(self, data: dict[str, Any], label: str, industry: str) -> SignalSample | None:
        daily = data.get("daily", {})
        temps = daily.get("temperature_2m_max", [])
        precip = daily.get("precipitation_sum", [])
        if not temps:
            return None

        month = datetime.now(UTC).month - 1  # 0-indexed
        baseline = SEASONAL_TEMP_BASELINE.get(label, [20] * 12)[month]
        avg_temp = sum(temps) / len(temps)
        deviation = avg_temp - baseline

        # Normalise: ±10°C → ±1. Positive deviation = warmer than expected.
        temp_score = clip(math.tanh(deviation / 10))

        total_precip = sum(p for p in precip if p is not None)
        # Heavy rain/drought signal — high precip unusual for most industries
        precip_score = clip(-math.tanh((total_precip - 20) / 30))

        # Combined score (temp has higher weight for demand impact)
        score = clip(0.7 * temp_score + 0.3 * precip_score)

        return SignalSample(
            source="weather",
            kind="economic_indicator",
            series_key=f"weather:{label.lower().replace(' ', '_')}:temp_deviation",
            industry=industry,
            captured_at=datetime.now(UTC),
            raw_value=round(deviation, 2),
            normalized_score=round(score, 4),
            confidence=0.90,
            category_tags=["weather", "temperature", "precipitation"],
            region=label,
            payload={
                "avg_temp_7d": round(avg_temp, 1),
                "baseline_temp": baseline,
                "deviation_c": round(deviation, 2),
                "total_precip_mm": round(total_precip, 1),
            },
        )

    def _synthetic(self, label: str, industry: str) -> SignalSample:
        score = clip(random.gauss(0, 0.25))
        return SignalSample(
            source="weather",
            kind="economic_indicator",
            series_key=f"weather:{label.lower().replace(' ', '_')}:temp_deviation",
            industry=industry,
            captured_at=datetime.now(UTC),
            raw_value=None,
            normalized_score=round(score, 4),
            confidence=0.40,
            category_tags=["weather", "synthetic"],
            region=label,
            payload={"synthetic": True},
        )
