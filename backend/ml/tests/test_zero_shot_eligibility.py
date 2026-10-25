"""Every active SKU that gets no forecast is listed with the reason (audit F08).

Zero-shot means "no tenant-trained model", not "no history": the path needs
eight weekly observations. A never-sold SKU used to disappear from the response
silently; now it is reported as not forecast, and why.
"""

from __future__ import annotations

import uuid

import numpy as np
import pandas as pd
import pytest

from sanket_ml.data.loader import TimeSeriesPanel
from sanket_ml.inference.zero_shot import ZeroShotForecaster


def _panel(series, *, counts, active, last_monday="2026-08-24"):
    frames = []
    for uid, values in series.items():
        ds = pd.date_range(end=pd.Timestamp(last_monday), periods=len(values), freq="W-MON")
        frames.append(pd.DataFrame({"unique_id": uid, "ds": ds, "y": np.asarray(values, float)}))
    df = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame({"unique_id": [], "ds": pd.to_datetime([]), "y": []})
    )
    return TimeSeriesPanel(
        data=df,
        tenant_id=uuid.uuid4(),
        industry="fashion",
        freq="W",
        start=pd.Timestamp("2025-01-06"),
        end=pd.Timestamp(last_monday),
        observation_counts=counts,
        active_sku_ids=tuple(active),
        last_week=pd.Timestamp(last_monday) if frames else None,
    )


def _forecaster(monkeypatch, panel, *, max_series=None):
    fc = ZeroShotForecaster()
    monkeypatch.setattr(fc.loader, "load", lambda **kw: panel)
    if max_series is not None:
        monkeypatch.setattr(fc.settings, "zero_shot_max_series", max_series)

    def fake_chronos(context_arrays, horizon, num_samples):
        z = np.ones((len(context_arrays), horizon))
        return z, z, z

    monkeypatch.setattr(fc, "_chronos_predict", fake_chronos)
    return fc


def test_unsold_short_and_capped_skus_are_reported_not_dropped(monkeypatch):
    panel = _panel(
        {"A": [20.0] * 10, "D": [5.0] * 9},
        counts={"A": 10, "B": 3, "D": 9},
        active=["A", "B", "C", "D"],
    )
    res = _forecaster(monkeypatch, panel, max_series=1).forecast(
        tenant_id=panel.tenant_id, industry="fashion", horizon=2
    )

    assert set(res.forecast.unique_id) == {"A"}
    assert {o["sku_id"]: (o["reason"], o["observations"]) for o in res.omitted} == {
        "B": ("insufficient_history", 3),
        "C": ("no_sales_history", 0),
        "D": ("series_cap", 9),
    }


def test_no_eligible_sku_explains_why(monkeypatch):
    panel = _panel({}, counts={"B": 3}, active=["B", "C"])
    with pytest.raises(ValueError, match=r"1 active SKU\(s\) have no sales.*1 have fewer than 8"):
        _forecaster(monkeypatch, panel).forecast(
            tenant_id=panel.tenant_id, industry="fashion", horizon=2
        )
