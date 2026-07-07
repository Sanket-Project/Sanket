from __future__ import annotations

import pandas as pd

from sanket_ml.data.features import (
    add_intermittency_flags,
    add_lag_features,
    add_rolling_features,
    build_calendar_features,
    build_feature_matrix,
)


def test_calendar_features_attach_expected_columns(synthetic_panel: pd.DataFrame) -> None:
    out = build_calendar_features(synthetic_panel)
    for col in ("year", "month", "week", "dow", "sin_woy", "cos_woy"):
        assert col in out.columns
    assert out["sin_woy"].between(-1, 1).all()


def test_lag_features_preserve_row_count(synthetic_panel: pd.DataFrame) -> None:
    out = add_lag_features(synthetic_panel, lags=(1, 2, 4))
    assert len(out) == len(synthetic_panel)
    assert out["y_lag_1"].isna().sum() == synthetic_panel["unique_id"].nunique()


def test_rolling_features_no_leakage(synthetic_panel: pd.DataFrame) -> None:
    out = add_rolling_features(synthetic_panel, windows=(4,), shift=1)
    # First row of each series must be NaN (no past observations available)
    firsts = out.groupby("unique_id").head(1)
    assert firsts["y_roll_mean_4"].isna().all()


def test_intermittency_classification_handles_zeros() -> None:
    df = pd.DataFrame(
        {
            "unique_id": ["A"] * 10 + ["B"] * 10,
            "ds": pd.date_range("2024-01-01", periods=10, freq="W").tolist() * 2,
            "y": [10] * 10 + [0, 0, 5, 0, 0, 0, 0, 8, 0, 0],
        }
    )
    out = add_intermittency_flags(df)
    classes = out.drop_duplicates("unique_id").set_index("unique_id")["demand_class"].to_dict()
    assert classes["A"] == "smooth"
    assert classes["B"] in ("intermittent", "lumpy")


def test_build_feature_matrix_end_to_end(synthetic_panel: pd.DataFrame) -> None:
    out = build_feature_matrix(synthetic_panel)
    assert "demand_class" in out.columns
    # Should have dropped early NaN rows from y_lag_1
    assert out["y_lag_1"].notna().all()
