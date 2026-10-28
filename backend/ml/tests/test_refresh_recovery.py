"""Persisted refresh retries read only the tenant's committed forecast."""

import uuid
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

from sanket_ml.inference.service import InferenceService


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class Engine:
    def __init__(self, run):
        self.run = run
        self.calls = []

    @contextmanager
    def begin(self):
        yield self

    def execute(self, sql, params):
        self.calls.append((str(sql), params))
        if "forecast_runs" in str(sql):
            return Result([self.run] if self.run else [])
        return Result([{
            "sku_id": uuid.UUID(int=1), "forecast_date": date(2026, 10, 26),
            "p10": Decimal("1.1"), "p50": Decimal("2.2"), "p90": Decimal("3.3"),
        }])


def test_recovery_reads_committed_rows_with_tenant_and_request_filters():
    tenant = uuid.uuid4()
    refresh_id = uuid.uuid4()
    run_id = uuid.uuid4()
    engine = Engine({"id": run_id, "model_stack": ["chronos_zero_shot"], "metrics": {
        "context_source": "database", "calendar": "W-MON-UTC", "omitted": [],
        "history_end": "2026-10-26", "first_forecast_week": "2026-10-26",
    }})
    service = object.__new__(InferenceService)
    service._engine = engine
    result = service.find_refresh(tenant, refresh_id)
    assert result["run_id"] == str(run_id)
    assert result["rows"][0]["p50"] == 2.2
    assert result["source"] == "chronos_zero_shot"
    run_query, params = engine.calls[1]
    assert "tenant_id" in run_query
    assert "refresh_id" in run_query
    assert "completed" in run_query
    assert params["tenant_id"] == str(tenant)
    assert params["refresh_id"] == str(refresh_id)
    assert "set_config" in engine.calls[0][0]
    assert engine.calls[0][1]["tenant_id"] == str(tenant)
    assert "tenant_id" in engine.calls[2][0]


def test_missing_refresh_does_not_load_any_results():
    service = object.__new__(InferenceService)
    service._engine = Engine(None)
    assert service.find_refresh(uuid.uuid4(), uuid.uuid4()) is None
    assert len(service._engine.calls) == 2
