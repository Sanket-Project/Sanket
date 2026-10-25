"""One weekly calendar from history to forecast: Monday 00:00 UTC buckets (audit F02).

History is bucketed by ``date_trunc('week')`` (Mondays) but zero-shot used the
unanchored pandas ``W`` offset (Sundays), so a forecast made after the week of
Monday 24 Aug 2026 was dated Sunday 30 Aug and never matched the actuals of the
week starting Monday 31 Aug.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest

from sanket_ml.data.calendar import CALENDAR, current_week_start, week_start
from sanket_ml.data.loader import TimeSeriesPanel, _reindex_panel
from sanket_ml.inference.zero_shot import ZeroShotForecaster


def _panel(series: dict[str, list[float]], last_monday: str, **extra) -> TimeSeriesPanel:
    frames = []
    for uid, values in series.items():
        ds = pd.date_range(end=pd.Timestamp(last_monday), periods=len(values), freq="W-MON")
        frames.append(pd.DataFrame({"unique_id": uid, "ds": ds, "y": np.asarray(values, float)}))
    df = pd.concat(frames, ignore_index=True)
    return TimeSeriesPanel(
        data=df,
        tenant_id=uuid.uuid4(),
        industry="fashion",
        freq="W",
        start=df["ds"].min(),
        end=df["ds"].max(),
        **extra,
    )


def _forecaster(monkeypatch, panel: TimeSeriesPanel) -> ZeroShotForecaster:
    fc = ZeroShotForecaster()
    monkeypatch.setattr(fc.loader, "load", lambda **kw: panel)

    def fake_chronos(context_arrays, horizon, num_samples):
        z = np.ones((len(context_arrays), horizon))
        return z, z * 2, z * 3

    monkeypatch.setattr(fc, "_chronos_predict", fake_chronos)
    return fc


def test_week_helpers_use_monday_utc():
    assert CALENDAR == "W-MON-UTC"
    assert week_start(date(2026, 8, 30)) == date(2026, 8, 24)  # Sunday → its Monday
    assert week_start(date(2026, 8, 31)) == date(2026, 8, 31)
    assert current_week_start(datetime(2026, 10, 28, 15, tzinfo=UTC)) == date(2026, 10, 26)
    # 01:30 IST on Monday is still Sunday in UTC: the convention is UTC.
    ist_monday_early = datetime.fromisoformat("2026-08-31T01:30:00+05:30")
    assert current_week_start(ist_monday_early) == date(2026, 8, 24)


def test_future_dates_continue_the_monday_buckets(monkeypatch):
    panel = _panel({"A": [10.0] * 12}, last_monday="2026-08-24")
    res = _forecaster(monkeypatch, panel).forecast(
        tenant_id=panel.tenant_id, industry="fashion", horizon=3
    )

    dates = [pd.Timestamp(d).date().isoformat() for d in res.forecast.ds]
    assert dates == ["2026-08-31", "2026-09-07", "2026-09-14"]
    assert res.history_end == date(2026, 8, 31)
    assert res.first_forecast_week == date(2026, 8, 31)


def test_forecast_starts_after_the_panels_last_week_not_a_sparse_skus(monkeypatch):
    """A SKU whose sales stopped earlier is forecast from the same calendar."""
    panel = _panel({"A": [10.0] * 12}, last_monday="2026-08-24", last_week=pd.Timestamp("2026-08-24"))
    early = _panel({"B": [5.0] * 10}, last_monday="2026-08-03").data
    panel = TimeSeriesPanel(
        data=_reindex_panel(pd.concat([panel.data, early]), "W", end=pd.Timestamp("2026-08-24")),
        tenant_id=panel.tenant_id, industry="fashion", freq="W",
        start=panel.start, end=panel.end, last_week=pd.Timestamp("2026-08-24"),
    )
    res = _forecaster(monkeypatch, panel).forecast(
        tenant_id=panel.tenant_id, industry="fashion", horizon=1
    )

    by_sku = {u: pd.Timestamp(d).date().isoformat() for u, d in zip(res.forecast.unique_id, res.forecast.ds, strict=True)}
    assert by_sku == {"A": "2026-08-31", "B": "2026-08-31"}


def test_reindex_extends_short_series_to_the_panel_end_with_zero_weeks():
    df = pd.DataFrame(
        {
            "unique_id": ["B"] * 3,
            "ds": pd.to_datetime(["2026-08-03", "2026-08-10", "2026-08-17"]),
            "y": [5.0, 0.0, 4.0],
        }
    )
    out = _reindex_panel(df, "W", end=pd.Timestamp("2026-08-31"))

    assert [d.date().isoformat() for d in out["ds"]] == [
        "2026-08-03", "2026-08-10", "2026-08-17", "2026-08-24", "2026-08-31"
    ]
    assert out["y"].tolist() == [5.0, 0.0, 4.0, 0.0, 0.0]
    assert out["observed"].tolist() == [1, 1, 1, 0, 0]


def test_history_end_must_be_a_monday(monkeypatch):
    panel = _panel({"A": [10.0] * 12}, last_monday="2026-08-24")
    with pytest.raises(ValueError, match="Monday"):
        _forecaster(monkeypatch, panel).forecast(
            tenant_id=panel.tenant_id, industry="fashion", horizon=3, history_end=date(2026, 8, 30)
        )


def test_history_end_is_passed_to_the_loader_as_the_cutoff(monkeypatch):
    panel = _panel({"A": [10.0] * 12}, last_monday="2026-08-24")
    fc = _forecaster(monkeypatch, panel)
    seen: dict = {}

    def capture(**kw):
        seen.update(kw)
        return panel

    monkeypatch.setattr(fc.loader, "load", capture)
    fc.forecast(tenant_id=panel.tenant_id, industry="fashion", horizon=2, history_end=date(2026, 8, 31))

    assert seen["end"] == date(2026, 8, 31)
