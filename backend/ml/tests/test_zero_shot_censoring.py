from __future__ import annotations

import uuid

import numpy as np
import pandas as pd

from sanket_ml.data.loader import TimeSeriesPanel
from sanket_ml.inference.zero_shot import ZeroShotForecaster


def _panel(values, uid="SKU1", tenant=None):
    n = len(values)
    df = pd.DataFrame(
        {
            "unique_id": [uid] * n,
            "ds": pd.date_range("2023-01-02", periods=n, freq="W-MON"),
            "y": np.asarray(values, dtype="float64"),
        }
    )
    return TimeSeriesPanel(
        data=df,
        tenant_id=tenant or uuid.uuid4(),
        industry="fashion",
        freq="W",
        start=df["ds"].min(),
        end=df["ds"].max(),
    )


def test_zero_shot_context_is_unconstrained(monkeypatch):
    """The array handed to the foundation model must have the stockout zero
    lifted toward the run rate, not passed through as 0."""
    # Regular seller (~10/wk) with one suspicious zero at index 30 — no
    # availability column, so the heuristic path should catch it.
    y = [10.0] * 60
    y[30] = 0.0
    panel = _panel(y)

    fc = ZeroShotForecaster()
    monkeypatch.setattr(fc.loader, "load", lambda **kw: panel)

    captured: dict = {}

    def fake_chronos(context_arrays, horizon, num_samples):
        captured["ctx"] = context_arrays
        n = len(context_arrays)
        z = np.zeros((n, horizon))
        return z, z, z

    monkeypatch.setattr(fc, "_chronos_predict", fake_chronos)

    fc.forecast(tenant_id=panel.tenant_id, industry="fashion", horizon=4)

    arr = captured["ctx"]["SKU1"]
    # The censored week was lifted; no zero remains in the in-span context.
    assert arr[30] > 5.0
    assert not np.any(arr == 0.0)


def test_zero_shot_disabled_passes_raw_zero(monkeypatch):
    y = [10.0] * 60
    y[30] = 0.0
    panel = _panel(y)

    fc = ZeroShotForecaster()
    # settings is a cached singleton — restore via monkeypatch so we don't leak.
    monkeypatch.setattr(fc.settings, "censoring_enabled", False)
    monkeypatch.setattr(fc.loader, "load", lambda **kw: panel)

    captured: dict = {}

    def fake_chronos(context_arrays, horizon, num_samples):
        captured["ctx"] = context_arrays
        n = len(context_arrays)
        z = np.zeros((n, horizon))
        return z, z, z

    monkeypatch.setattr(fc, "_chronos_predict", fake_chronos)
    fc.forecast(tenant_id=panel.tenant_id, industry="fashion", horizon=4)

    # With correction off, the raw zero survives into the context.
    assert captured["ctx"]["SKU1"][30] == 0.0
