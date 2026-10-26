"""Missing, insufficient, stale and failed signal evidence are told apart (F05).

The Trends page showed "High (100%) agreement" from zero samples because an
empty score defaults to volatility 0. The API now says what evidence exists,
and agreement (volatility) is only reported when there is enough of it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.external_signals.base import SignalSample
from app.services.external_signals.signal_pipeline import SignalIngestionPipeline
from app.services.signal_evidence import MIN_SAMPLES, signal_evidence

NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)


def _evidence(captured: list[datetime], sources=None, last_run=None):
    return signal_evidence(
        captured_at=captured,
        sources=sources or ["google_trends"] * len(captured),
        industry="fashion",
        now=NOW,
        lookback_hours=168,
        last_run=last_run,
    )


def test_no_samples_is_unavailable_not_agreement():
    ev = _evidence([])
    assert ev["status"] == "unavailable"
    assert ev["sample_count"] == 0
    assert ev["agreement_reportable"] is False


def test_a_failed_ingest_is_named():
    last_run = {"finished_at": NOW.isoformat(),
                "industries": {"fashion": {"samples": 12, "persisted": 0,
                                           "error": "no partition of relation trend_signals"}}}
    ev = _evidence([], last_run=last_run)
    assert ev["status"] == "unavailable"
    assert "no partition" in ev["message"]
    assert ev["last_ingest"]["error"] == "no partition of relation trend_signals"


def test_too_few_samples_is_insufficient():
    ev = _evidence([NOW - timedelta(hours=1)] * (MIN_SAMPLES - 1))
    assert ev["status"] == "insufficient"
    assert ev["agreement_reportable"] is False


def test_old_samples_are_stale():
    ev = _evidence([NOW - timedelta(hours=72)] * 5)
    assert ev["status"] == "stale"
    assert ev["agreement_reportable"] is False


def test_enough_fresh_samples_are_available():
    ev = _evidence([NOW - timedelta(hours=2)] * 4, sources=["fred", "fred", "reddit", "google_trends"])
    assert ev["status"] == "available"
    assert ev["source_count"] == 3
    assert ev["agreement_reportable"] is True


@pytest.mark.asyncio
async def test_pipeline_records_a_persist_failure_per_industry(monkeypatch):
    class _OneSample:
        name = "google_trends"

        async def fetch(self, industry):
            return [SignalSample(source="google_trends", kind="search_interest",
                                 series_key="t:x", industry=industry, captured_at=NOW,
                                 raw_value=None, normalized_score=0.1)]

    pipeline = SignalIngestionPipeline(db=None, connectors=[_OneSample()])

    async def failing_persist(samples):
        raise RuntimeError("no partition of relation trend_signals found for row")

    monkeypatch.setattr(pipeline, "_persist", failing_persist)
    await pipeline.run_once()

    fashion = pipeline.last_run["industries"]["fashion"]
    assert fashion["samples"] == 1
    assert fashion["persisted"] == 0
    assert "no partition" in fashion["error"]
    # One industry failing does not stop the others from being attempted.
    assert set(pipeline.last_run["industries"]) >= {"fashion", "pharma", "hardware"}


async def test_score_endpoint_reports_evidence_and_withholds_volatility(client, signed_in_workspace):
    _, headers = await signed_in_workspace("hardware")

    r = await client.get("/api/v1/trends/score", headers=headers)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["evidence"]["status"] in {"unavailable", "insufficient", "stale", "available"}
    if body["evidence"]["status"] != "available":
        assert body["volatility"] is None


def test_hybrid_trend_withholds_agreement_without_evidence():
    """The Hybrid page showed 'They mostly agree' from a zero-sample trend."""
    from types import SimpleNamespace

    from app.models.enums import IndustryCode
    from app.services.hybrid_forecast import _trend_out

    empty = SimpleNamespace(score=0.0, volatility=0.0, sample_count=0, by_kind={}, drivers=[],
                            demand_factors=[], horizon_days=90)
    out = _trend_out(empty, IndustryCode.fashion, records=[], now=NOW)

    assert out.volatility is None
    assert out.evidence["status"] == "unavailable"
    assert out.evidence["agreement_reportable"] is False
