"""ML /forecast contract: calendar, omissions and explicit backtests (F02, F08).

The model and the database are replaced with fakes; what is under test is the
API's routing and what it records — dates, the cutoff the model saw, and every
SKU it did not forecast.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

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
    active: set = set()
    guard_lock = threading.Lock()

    def __init__(self, settings):
        pass

    def persist_forecast(self, **kw):
        _FakeService.persisted.append(kw)
        return uuid.uuid4()

    @contextmanager
    def tenant_slot(self, tenant_id):
        from sanket_ml.inference.guard import TenantInferenceBusyError
        with self.guard_lock:
            if tenant_id in self.active:
                raise TenantInferenceBusyError()
            self.active.add(tenant_id)
        try:
            yield
        finally:
            self.active.remove(tenant_id)

    def find_refresh(self, tenant_id, refresh_id):
        return None


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


@pytest.mark.parametrize("path", ["/forecast", "/forecast/zero-shot"])
def test_persistence_failure_is_an_error_not_a_synthetic_run(client, monkeypatch, path):
    def fail(self, **kw):
        raise RuntimeError("database write failed")
    monkeypatch.setattr(_FakeService, "persist_forecast", fail)
    response = client.post(path, json=_body(force_zero_shot=True))
    assert response.status_code == 503
    assert "persist" in response.json()["detail"].lower()


def test_guard_spans_both_forecast_endpoints_through_persistence(client, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    original = _FakeService.persist_forecast
    def hold(self, **kw):
        entered.set()
        assert release.wait(5)
        return original(self, **kw)
    monkeypatch.setattr(_FakeService, "persist_forecast", hold)
    body = _body(force_zero_shot=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(client.post, "/forecast", json=body)
        try:
            assert entered.wait(5)
            second = client.post("/forecast/zero-shot", json=body)
            assert second.status_code == 409
        finally:
            release.set()
        assert first.result().status_code == 200


def test_refresh_id_is_saved_with_run_metadata(client):
    refresh_id = str(uuid.uuid4())
    result = client.post("/forecast", json=_body(force_zero_shot=True, refresh_id=refresh_id))
    assert result.status_code == 200
    assert _FakeService.persisted[0]["run_metadata"]["refresh_id"] == refresh_id


def test_completed_refresh_is_returned_without_recomputing(client, monkeypatch):
    response = client.post("/forecast", json=_body(force_zero_shot=True)).json()
    _FakeZeroShot.calls.clear()
    monkeypatch.setattr(_FakeService, "find_refresh", lambda *args: response)
    replay = client.post("/forecast", json=_body(force_zero_shot=True, refresh_id=str(uuid.uuid4())))
    assert replay.status_code == 200
    assert replay.json() == response
    assert _FakeZeroShot.calls == []


def test_cancelled_caller_cannot_release_its_compute_thread_lock(client, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    original = _FakeService.persist_forecast

    def hold(self, **kw):
        entered.set()
        assert release.wait(5)
        try:
            return original(self, **kw)
        finally:
            finished.set()

    monkeypatch.setattr(_FakeService, "persist_forecast", hold)
    body = _body(force_zero_shot=True)

    async def exercise():
        async with AsyncClient(transport=ASGITransport(app=client.app), base_url="http://test") as http:
            first = asyncio.create_task(http.post("/forecast", json=body))
            try:
                for _ in range(500):
                    if entered.is_set():
                        break
                    await asyncio.sleep(0.005)
                assert entered.is_set()
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first
                # The abandoned computation is still persisting and retains the
                # tenant lock even though its HTTP task has already gone away.
                second = await http.post("/forecast/zero-shot", json=body)
                assert second.status_code == 409
            finally:
                release.set()
                for _ in range(500):
                    if finished.is_set():
                        break
                    await asyncio.sleep(0.005)
                assert finished.is_set()

    asyncio.run(exercise())
