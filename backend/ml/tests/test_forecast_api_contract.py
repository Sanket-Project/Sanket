"""ML /forecast contract: calendar, omissions and explicit backtests (F02, F08).

The model and the database are replaced with fakes; what is under test is the
API's routing and what it records — dates, the cutoff the model saw, and every
SKU it did not forecast.
"""

from __future__ import annotations

import uuid
from datetime import date

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from sanket_ml.config import MLSettings
from sanket_ml.inference import api as api_module
from sanket_ml.inference.zero_shot import ZeroShotResult
from sanket_ml.models.base import ForecastQuantiles


class _FakeZeroShot:
    calls: list[dict] = []

    def __init__(self, settings):
        pass

    def forecast(self, **kw):
        _FakeZeroShot.calls.append(kw)
        ds = list(pd.date_range("2026-08-31", periods=kw["horizon"], freq="W-MON"))
        p = np.ones(len(ds), dtype="float32")
        return ZeroShotResult(
            forecast=ForecastQuantiles(
                unique_id=["A"] * len(ds), ds=ds, p10=p, p50=p * 2, p90=p * 3,
                model_name="chronos_zero_shot",
            ),
            source_model="chronos_zero_shot",
            context_source="database",
            n_series=1,
            used_observations=12,
            history_end=date(2026, 8, 31),
            first_forecast_week=date(2026, 8, 31),
            omitted=[{"sku_id": "C", "reason": "no_sales_history", "observations": 0}],
        )


class _FakeService:
    persisted: list[dict] = []

    def __init__(self, settings):
        pass

    def persist_forecast(self, **kw):
        _FakeService.persisted.append(kw)
        return uuid.uuid4()


@pytest.fixture
def client(monkeypatch):
    _FakeZeroShot.calls.clear()
    _FakeService.persisted.clear()
    settings = MLSettings(require_auth=False, chronos_preload_on_startup=False)
    monkeypatch.setattr(api_module, "get_ml_settings", lambda: settings)
    monkeypatch.setattr(api_module, "ZeroShotForecaster", _FakeZeroShot)
    monkeypatch.setattr(api_module, "InferenceService", _FakeService)
    return TestClient(api_module.create_app())


def _body(**extra):
    return {"tenant_id": str(uuid.uuid4()), "industry": "fashion", "horizon": 2, **extra}


def test_response_carries_calendar_cutoff_and_omissions(client):
    r = client.post("/forecast", json=_body(force_zero_shot=True))

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["calendar"] == "W-MON-UTC"
    assert body["history_end"] == "2026-08-31"
    assert body["first_forecast_week"] == "2026-08-31"
    assert [row["forecast_date"] for row in body["rows"]] == ["2026-08-31", "2026-09-07"]
    assert body["omitted"] == [{"sku_id": "C", "reason": "no_sales_history", "observations": 0}]


def test_persisted_run_records_what_the_model_saw(client):
    client.post("/forecast", json=_body(force_zero_shot=True))

    meta = _FakeService.persisted[0]["run_metadata"]
    assert meta["calendar"] == "W-MON-UTC"
    assert meta["history_end"] == "2026-08-31"
    assert meta["mode"] == "zero_shot"
    assert meta["omitted_count"] == 1


def test_history_end_runs_an_explicit_backtest(client):
    r = client.post("/forecast", json=_body(history_end="2026-08-31"))

    assert r.status_code == 200, r.text
    assert _FakeZeroShot.calls[0]["history_end"] == date(2026, 8, 31)
    assert _FakeService.persisted[0]["run_metadata"]["mode"] == "backtest"


def test_history_end_that_is_not_a_monday_is_rejected(client):
    r = client.post("/forecast", json=_body(history_end="2026-08-30"))
    assert r.status_code == 422
