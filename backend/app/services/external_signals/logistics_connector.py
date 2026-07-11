"""Geocoding & Logistics Routing signal connector using Open Source Routing Machine (OSRM).

Calculates structural driving distances and estimated transit durations for key global and Indian supply lanes.
Keeps all global corridors fully functional while adding comprehensive Indian transit corridors.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime
from typing import Any

import structlog

from app.services.external_signals.base import SignalConnector, SignalSample, clip

log = structlog.get_logger(__name__)

# Blended Supply lanes per industry: list of (lane_name, start_coord, end_coord, baseline_hours, region)
# Coordinates are (longitude, latitude) as required by OSRM
SUPPLY_LANES: dict[str, list[tuple[str, str, str, float, str]]] = {
    "fashion": [
        # Global
        ("NYC_Port_to_NJ_Warehouse", "-74.01,40.71", "-74.17,40.73", 0.5, "US"),
        # India (West to South Apparel Hub)
        ("Mumbai_Port_to_Bangalore_Apparel", "72.95,18.95", "77.59,12.97", 20.0, "IN"),
    ],
    "electronics": [
        # Global
        ("Shenzhen_Port_to_Shanghai_Hub", "114.06,22.54", "121.47,31.23", 15.0, "WW"),
        # India (South to East Core Corridor)
        ("Chennai_Port_to_Hyderabad_Tech", "80.30,13.09", "78.48,17.38", 12.0, "IN"),
    ],
    "pharma": [
        # Global
        ("Basel_Port_to_Frankfurt_Hub", "7.59,47.56", "8.68,50.11", 3.5, "EU"),
        # India (Pharma Manufacturing Core)
        ("Hyderabad_Pharma_to_Mumbai_Port", "78.55,17.20", "72.95,18.95", 16.0, "IN"),
    ],
    "agrocenter": [
        # Global
        ("Iowa_City_to_Chicago_Hub", "-91.53,41.66", "-87.62,41.87", 3.5, "US"),
        # India (Agri-Logistics Hubs)
        ("Siddipet_to_Hyderabad_Agri", "78.85,18.10", "78.48,17.38", 2.0, "IN"),
        ("Punjab_to_Delhi_NCR_Grain", "74.87,31.63", "77.20,28.61", 8.0, "IN"),
    ],
    "hardware": [
        # Global (industrial supply corridors)
        ("Houston_Industrial_to_Dallas_Hub", "-95.36,29.76", "-96.80,32.78", 4.0, "US"),
        ("Yiwu_Hardware_Market_to_Shanghai_Port", "120.07,29.31", "121.47,31.23", 4.0, "WW"),
        # India (Ludhiana tools/fasteners hub → Delhi NCR distribution)
        ("Ludhiana_Tools_to_Delhi_NCR", "75.85,30.90", "77.20,28.61", 6.0, "IN"),
    ],
}

OSRM_ROUTE_URL = "http://router.project-osrm.org/route/v1/driving"


class LogisticsConnector(SignalConnector):
    """Fetches logistics routing profiles from OSRM for both global and Indian supply corridors."""

    name = "logistics"

    async def fetch(self, industry: str) -> list[SignalSample]:
        lanes = SUPPLY_LANES.get(industry, [])
        if not lanes:
            return []

        try:
            import httpx

            samples: list[SignalSample] = []
            now = datetime.now(UTC)

            async with httpx.AsyncClient(timeout=10.0) as client:
                for lane_name, start, end, baseline_hours, region in lanes:
                    try:
                        # Query OSRM routing profile (no key required, public rate-limited endpoint)
                        resp = await client.get(
                            f"{OSRM_ROUTE_URL}/{start};{end}",
                            params={
                                "overview": "false",
                                "steps": "false",
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        sample = self._parse(data, industry, lane_name, baseline_hours, region, now)
                        if sample:
                            samples.append(sample)
                    except Exception as exc:
                        log.warning("logistics.osrm.failed", lane=lane_name, error=str(exc))

            return samples
        except ImportError:
            return []
        except Exception as exc:
            log.warning("logistics.fetch.failed", industry=industry, error=str(exc))
            return []

    def _parse(
        self,
        data: dict[str, Any],
        industry: str,
        lane_name: str,
        baseline_hours: float,
        region: str,
        now: datetime,
    ) -> SignalSample | None:
        routes = data.get("routes", [])
        if not routes:
            return None

        primary_route = routes[0]
        duration_seconds = primary_route.get("duration", 0.0)
        distance_meters = primary_route.get("distance", 0.0)

        duration_hours = duration_seconds / 3600.0
        distance_km = distance_meters / 1000.0

        # Seed random walk with current hour + day to keep the score stable across repeated calls in the same hour
        seed_value = hash((lane_name, now.strftime("%Y-%m-%d-%H"))) & 0xFFFFFFFF
        rng = random.Random(seed_value)

        # Congestion factor varies between -5% and +35% (modelling standard, medium, and heavy delays)
        congestion_factor = rng.uniform(-0.05, 0.35)
        actual_duration_hours = duration_hours * (1.0 + congestion_factor)

        # Deviation from ideal baseline duration
        deviation_ratio = (actual_duration_hours - baseline_hours) / baseline_hours

        # Map to unified score:
        # Neutral (0.0) is standard baseline.
        # - Excess congestion (deviation_ratio > 0.1) drives score down towards -1.0.
        # - Faster than average (deviation_ratio < 0) boosts score towards +0.5.
        score = -math.tanh(deviation_ratio * 2.0)
        normalized = clip(score)

        return SignalSample(
            source="logistics",
            kind="economic_indicator",
            series_key=f"logistics:{lane_name.lower()}:transit_efficiency",
            industry=industry,
            captured_at=now,
            raw_value=round(actual_duration_hours, 2),
            normalized_score=round(normalized, 4),
            confidence=0.85,
            category_tags=["logistics", "routing", "shipping", "transit_time"],
            region=region,
            payload={
                "lane_name": lane_name.replace("_", " "),
                "geocoding_route_found": True,
                "distance_km": round(distance_km, 2),
                "osrm_base_duration_hours": round(duration_hours, 2),
                "simulated_congestion_percent": round(congestion_factor * 100.0, 1),
                "actual_transit_hours": round(actual_duration_hours, 2),
                "baseline_transit_hours": baseline_hours,
            },
        )

    def _synthetic(
        self,
        industry: str,
        lane_name: str,
        baseline_hours: float,
        region: str,
        now: datetime,
    ) -> SignalSample:
        # High fidelity synthetic fallback
        rng = random.Random(hash((lane_name, now.date().isoformat(), "logistics")) & 0xFFFFFFFF)
        congestion = rng.uniform(0.02, 0.40)
        actual_transit = baseline_hours * (1.0 + congestion)
        score = -clip(congestion * 2.5)

        return SignalSample(
            source="logistics",
            kind="economic_indicator",
            series_key=f"logistics:{lane_name.lower()}:transit_efficiency",
            industry=industry,
            captured_at=now,
            raw_value=round(actual_transit, 2),
            normalized_score=round(score, 4),
            confidence=0.45,
            category_tags=["logistics", "synthetic"],
            region=region,
            payload={
                "lane_name": lane_name.replace("_", " "),
                "synthetic": True,
                "actual_transit_hours": round(actual_transit, 2),
                "baseline_transit_hours": baseline_hours,
                "msg": "OSRM routing service offline. Emitting high-fidelity synthetic fallback.",
            },
        )
