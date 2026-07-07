from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sanket_ml.data.censoring import correct_censored_demand


def _series(values, start="2023-01-02", freq="W-MON", uid="A", **extra):
    n = len(values)
    df = pd.DataFrame(
        {
            "unique_id": [uid] * n,
            "ds": pd.date_range(start, periods=n, freq=freq),
            "y": np.asarray(values, dtype="float64"),
        }
    )
    for k, v in extra.items():
        df[k] = v
    return df


# ── Explicit availability path ─────────────────────────────────────────────

def test_explicit_oos_period_is_imputed_upward():
    # Steady demand ~10/wk; weeks 20-21 sold 0 because out of stock.
    y = [10.0] * 30
    y[20] = 0.0
    y[21] = 0.0
    avail = [1.0] * 30
    avail[20] = 0.0
    avail[21] = 0.0
    df = _series(y, in_stock_frac=avail)

    res = correct_censored_demand(df)
    out = res.data.sort_values("ds").reset_index(drop=True)

    assert res.report.detection_mode == "explicit"
    assert res.report.n_obs_imputed == 2
    # The two zero weeks are lifted to ~the in-stock run rate.
    assert out.loc[20, "y"] == pytest.approx(10.0, abs=1e-6)
    assert out.loc[21, "y"] == pytest.approx(10.0, abs=1e-6)
    assert out.loc[20, "is_censored"] == 1
    # An in-stock week is untouched.
    assert out.loc[5, "is_censored"] == 0
    assert out.loc[5, "y"] == 10.0
    # Raw values are preserved for audit.
    assert out.loc[20, "y_raw"] == 0.0
    assert res.report.units_added == pytest.approx(20.0, abs=1e-6)


def test_unknown_availability_is_treated_as_in_stock():
    # NaN availability must never be read as a stockout.
    y = [10.0] * 20
    avail = [np.nan] * 20
    df = _series(y, in_stock_frac=avail)
    res = correct_censored_demand(df)
    # All-NaN availability => no explicit signal => heuristic. But there are no
    # zeros, so nothing is imputed regardless.
    assert res.report.n_obs_imputed == 0


def test_observed_value_is_never_reduced():
    # OOS for part of a week but still sold 8 units; estimate (~10) would apply,
    # but if estimate were below observed we must keep observed.
    y = [3.0] * 30  # low steady demand
    y[15] = 8.0     # spike during a partial stockout week
    avail = [1.0] * 30
    avail[15] = 0.2  # mostly OOS
    df = _series(y, in_stock_frac=avail)
    res = correct_censored_demand(df)
    out = res.data.sort_values("ds").reset_index(drop=True)
    # Estimate from neighbours ~3, but observed 8 → keep 8 (never reduce).
    assert out.loc[15, "y"] == pytest.approx(8.0, abs=1e-6)


# ── Heuristic path (no availability column) ─────────────────────────────────

def test_heuristic_imputes_zero_for_regular_seller():
    rng = np.random.default_rng(0)
    y = (10 + rng.normal(0, 1, 60)).clip(min=1).tolist()  # smooth, always sells
    y[30] = 0.0  # suspicious zero — no stockout flag available
    df = _series(y)  # no in_stock_frac column at all

    res = correct_censored_demand(df)
    out = res.data.sort_values("ds").reset_index(drop=True)

    assert res.report.detection_mode == "heuristic"
    assert out.loc[30, "is_censored"] == 1
    assert out.loc[30, "y"] > 5.0  # lifted toward the ~10 run rate


def test_heuristic_leaves_intermittent_series_alone():
    # Lumpy/intermittent demand: lots of genuine zeros. Must NOT be imputed.
    y = [0, 0, 0, 5, 0, 0, 0, 0, 8, 0, 0, 0, 0, 0, 6, 0, 0, 0, 0, 0,
         0, 7, 0, 0, 0, 0, 0, 9, 0, 0]
    df = _series(y)
    res = correct_censored_demand(df)
    assert res.report.n_obs_imputed == 0
    np.testing.assert_array_equal(
        res.data.sort_values("ds")["y"].to_numpy(),
        np.asarray(y, dtype="float64"),
    )


def test_heuristic_can_be_disabled():
    y = [10.0] * 40
    y[20] = 0.0
    df = _series(y)
    res = correct_censored_demand(df, heuristic_when_missing=False)
    assert res.report.n_obs_imputed == 0


# ── Lifecycle / edge cases ──────────────────────────────────────────────────

def test_leading_and_trailing_zeros_are_not_imputed():
    # Pre-launch zeros (lead) and discontinued zeros (trail) are lifecycle, not
    # censoring, and must be left untouched even for a regular seller.
    y = [0.0, 0.0, 0.0] + [10.0] * 20 + [0.0, 0.0, 0.0]
    df = _series(y)
    res = correct_censored_demand(df)
    out = res.data.sort_values("ds").reset_index(drop=True)
    assert out.loc[0, "y"] == 0.0
    assert out.loc[1, "y"] == 0.0
    assert out.iloc[-1]["y"] == 0.0
    assert res.report.n_obs_imputed == 0


def test_all_zero_series_untouched():
    df = _series([0.0] * 20)
    res = correct_censored_demand(df)
    assert res.report.n_obs_imputed == 0


def test_short_series_skipped():
    df = _series([10.0, 0.0, 10.0, 10.0])  # below default min_history=12
    res = correct_censored_demand(df)
    assert res.report.n_obs_imputed == 0


def test_empty_and_missing_columns_noop():
    assert correct_censored_demand(pd.DataFrame()).report.n_obs == 0
    bad = pd.DataFrame({"foo": [1, 2, 3]})
    out = correct_censored_demand(bad)
    assert out.report.n_obs == 0
    assert out.data is bad


def test_multi_series_mixed_modes_and_isolation():
    # Series A: regular seller with a heuristic zero. Series B: pure intermittent.
    a = _series([10.0] * 20 + [0.0] + [10.0] * 9, uid="A")
    b = _series([0, 0, 6, 0, 0, 0, 9, 0, 0, 0, 0, 5, 0, 0, 0, 0, 0, 7, 0, 0,
                 0, 0, 8, 0, 0, 0, 0, 0, 4, 0], uid="B")
    df = pd.concat([a, b], ignore_index=True)
    res = correct_censored_demand(df)
    out = res.data
    # B is untouched; only A's single zero is imputed.
    assert res.report.n_series_corrected == 1
    assert res.report.n_obs_imputed == 1
    b_out = out[out["unique_id"] == "B"].sort_values("ds")["y"].to_numpy()
    np.testing.assert_array_equal(b_out, b["y"].to_numpy())
