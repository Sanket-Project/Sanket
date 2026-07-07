"""Unit tests for FdaConnector, LogisticsConnector, and RegionalDemandConnector with blended Global & Nationwide Indian support."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.external_signals.fda_connector import FdaConnector
from app.services.external_signals.logistics_connector import LogisticsConnector
from app.services.external_signals.regional_demand_connector import RegionalDemandConnector


@pytest.mark.asyncio
async def test_fda_connector_non_pharma_ignored():
    """Verify that regulatory signals are only gathered for the pharma industry."""
    connector = FdaConnector()
    samples = await connector.fetch("fashion")
    assert samples == []

    samples = await connector.fetch("electronics")
    assert samples == []


@pytest.mark.asyncio
async def test_fda_connector_success_parsing():
    """Verify openFDA recalls are fetched and the risk index is calculated correctly.

    The connector emits a single real FDA (US) sample. Synthetic Indian CDSCO
    data (previously produced by a seeded RNG in ``_fetch_cdsco``) is not emitted
    under the real-data-only policy, so it is intentionally not asserted here.
    """
    mock_response = {
        "results": [
            {"classification": "Class I", "recalling_firm": "PharmaCorp", "state": "NY"},
            {"classification": "Class II", "recalling_firm": "BioMeds", "state": "CA"},
            {"classification": "Class II", "recalling_firm": "PharmaCorp", "state": "TX"},
        ]
    }

    connector = FdaConnector()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response
        mock_client.get.return_value = mock_resp

        samples = await connector.fetch("pharma")

        # Exactly one real FDA (US) sample — the synthetic CDSCO fallback was
        # removed under the real-data-only policy.
        assert len(samples) == 1
        
        # Verify FDA Sample
        fda_sample = next(s for s in samples if s.region == "US")
        assert fda_sample.source == "fda"
        assert fda_sample.kind == "news_sentiment"
        assert fda_sample.series_key == "fda:drug_recalls:risk_index"
        assert fda_sample.raw_value == 3.0
        # Score: 0.8 - (0.25 * 1 + 0.10 * 2) = 0.35
        assert fda_sample.normalized_score == 0.35
        
        # NOTE: synthetic Indian CDSCO data (_fetch_cdsco) is intentionally not
        # emitted by fetch() under the real-data-only policy, so it is not asserted.


@pytest.mark.asyncio
async def test_logistics_connector_blended_lanes():
    """Verify that LogisticsConnector gathers both global and Indian routing lanes per sector."""
    connector = LogisticsConnector()
    
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "routes": [{"duration": 3600.0, "distance": 50000.0}]
        }
        mock_client.get.return_value = mock_resp

        # Test fashion industry (which contains NYC to NJ and Mumbai to Bangalore)
        samples = await connector.fetch("fashion")
        
        assert len(samples) == 2
        nyc_lane = next(s for s in samples if s.region == "US")
        mumbai_lane = next(s for s in samples if s.region == "IN")
        
        assert "NYC" in nyc_lane.payload["lane_name"]
        assert "Mumbai" in mumbai_lane.payload["lane_name"]
        assert nyc_lane.payload["distance_km"] == 50.0
        assert mumbai_lane.payload["distance_km"] == 50.0


@pytest.mark.asyncio
async def test_regional_demand_connector_tier_classification():
    """Verify that RegionalDemandConnector classifies Indian cities and districts into correct tiers."""
    connector = RegionalDemandConnector()
    
    assert connector._classify_tier("bangalore") == "tier1"
    assert connector._classify_tier("mumbai") == "tier1"
    assert connector._classify_tier("jaipur") == "tier2"
    assert connector._classify_tier("lucknow") == "tier2"
    assert connector._classify_tier("siddipet") == "tier3"
    assert connector._classify_tier("amritsar") == "tier3"


@pytest.mark.asyncio
async def test_regional_demand_connector_fetch():
    """Verify that RegionalDemandConnector fetches and packages city-level Google Trends search signals."""
    import pandas as pd
    connector = RegionalDemandConnector()
    
    # Mock pytrends TrendReq to return stable test data and prevent external network 429s
    with patch("pytrends.request.TrendReq") as mock_trend_req_cls:
        mock_trend_req = MagicMock()
        mock_trend_req_cls.return_value = mock_trend_req
        
        # Mock dataframe representing interest by region/city
        mock_df = pd.DataFrame({
            "sneakers": [90, 80, 70, 0, 0],
            "printed t-shirts": [88, 78, 68, 0, 0],
            "jeans": [94, 84, 74, 0, 0],
            "pesticides": [86, 76, 66, 0, 0],
            "urea fertilizer": [92, 82, 72, 0, 0],
            "tractors": [79, 69, 59, 0, 0],
        }, index=["bangalore", "jaipur", "siddipet", "mumbai", "delhi"])
        
        mock_trend_req.interest_by_region.return_value = mock_df
        
        # Test fashion (sneakers, printed t-shirts, jeans)
        samples = await connector.fetch("fashion")
        
        # We expect samples covering the mocked rows
        assert len(samples) > 5
        
        # Verify we can find a Tier 1 sneakers sample
        bangalore_sample = next(
            s for s in samples 
            if "Tier1" in s.region and s.payload["product"] == "sneakers"
        )
        assert bangalore_sample.source == "google_trends"
        assert bangalore_sample.kind == "search_interest"
        assert bangalore_sample.payload["tier"] == "TIER1"
        assert bangalore_sample.payload["relative_search_interest"] > 0
        
        # Verify we can find a Tier 3 pesticides sample
        agro_samples = await connector.fetch("agrocenter")
        siddipet_sample = next(
            s for s in agro_samples
            if "Tier3" in s.region and s.payload["product"] == "pesticides"
        )
        assert siddipet_sample.source == "google_trends"
        assert siddipet_sample.payload["tier"] == "TIER3"
        assert siddipet_sample.payload["relative_search_interest"] > 0

