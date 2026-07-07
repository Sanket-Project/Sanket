from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import structlog

from sanket_ml.data.splits import apply_split, walk_forward_splits
from sanket_ml.models.base import BaseForecaster, ForecastQuantiles
from sanket_ml.models.ensemble import pinball_loss

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class BacktestMetrics:
    model_name: str
    fold: int
    mape: float
    smape: float
    wape: float
    rmse: float
    pinball_p10: float
    pinball_p50: float
    pinball_p90: float
    coverage_80: float  # fraction of y in [p10, p90]
    n_obs: int
    # Mean Absolute Scaled Error — scale-free, comparable across SKUs and the
    # canonical way to compare against a naive baseline (MASE < 1 ⇒ the model
    # beats the seasonal-naive reference on this slice). Defaulted so existing
    # positional construction (e.g. the empty-result path) keeps working.
    mase: float = 0.0


def _mase(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    season_length: int,
    naive_scale: float | None = None,
) -> float:
    """MASE = MAE(forecast) / scale, where scale is the in-sample seasonal-naive
    MAE when supplied (canonical), else the seasonal-difference MAE of the truth
    (pooled fallback). Returns 0.0 when undefined."""
    yt = np.asarray(y_true, dtype="float64")
    yp = np.asarray(y_pred, dtype="float64")
    if yt.size == 0:
        return 0.0
    mae = float(np.mean(np.abs(yt - yp)))
    if naive_scale is not None and naive_scale > 1e-9:
        return mae / naive_scale
    # Seasonal-naive scale = mean |y_t - y_{t-s}| (a LAG-s difference, not the
    # s-th order derivative — np.diff(n=s) would be the latter and is wrong).
    s = season_length if yt.size > season_length else 1
    diffs = np.abs(yt[s:] - yt[:-s]) if yt.size > s else np.abs(np.diff(yt))
    denom = float(np.mean(diffs)) if diffs.size else 0.0
    return mae / denom if denom > 1e-9 else 0.0


def _safe_div(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    out = np.zeros_like(num, dtype="float64")
    mask = den != 0
    out[mask] = num[mask] / den[mask]
    return out


def evaluate(
    y_true: np.ndarray,
    fc: ForecastQuantiles,
    *,
    model_name: str | None = None,
    fold: int = 0,
    season_length: int = 52,
    naive_scale: float | None = None,
) -> BacktestMetrics:
    yt = np.asarray(y_true, dtype="float64")
    p50 = np.asarray(fc.p50, dtype="float64")
    p10 = np.asarray(fc.p10, dtype="float64")
    p90 = np.asarray(fc.p90, dtype="float64")
    n = len(yt)
    if n == 0:
        return BacktestMetrics(model_name or fc.model_name, fold, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    abs_err = np.abs(yt - p50)
    mape = float(np.mean(_safe_div(abs_err, np.maximum(np.abs(yt), 1e-9))) * 100)
    smape = float(np.mean(_safe_div(2 * abs_err, np.abs(yt) + np.abs(p50) + 1e-9)) * 100)
    wape = float(abs_err.sum() / max(np.abs(yt).sum(), 1e-9) * 100)
    rmse = float(np.sqrt(np.mean((yt - p50) ** 2)))
    coverage = float(np.mean((yt >= p10) & (yt <= p90)))

    return BacktestMetrics(
        model_name=model_name or fc.model_name,
        fold=fold,
        mape=mape,
        smape=smape,
        wape=wape,
        rmse=rmse,
        pinball_p10=pinball_loss(yt, p10, 0.1),
        pinball_p50=pinball_loss(yt, p50, 0.5),
        pinball_p90=pinball_loss(yt, p90, 0.9),
        coverage_80=coverage,
        n_obs=n,
        mase=_mase(yt, p50, season_length=season_length, naive_scale=naive_scale),
    )


def align_truth(val_df: pd.DataFrame, fc: ForecastQuantiles) -> tuple[np.ndarray, ForecastQuantiles]:
    val_df = val_df.copy()
    val_df["ds"] = pd.to_datetime(val_df["ds"])
    val_df["unique_id"] = val_df["unique_id"].astype(str)
    keys_truth = list(zip(val_df["unique_id"], val_df["ds"]))
    keys_fc = list(zip(fc.unique_id, [pd.Timestamp(d) for d in fc.ds]))
    lookup_fc = {k: i for i, k in enumerate(keys_fc)}

    matched_truth: list[float] = []
    idx_fc: list[int] = []
    for k, y in zip(keys_truth, val_df["y"].tolist()):
        if k in lookup_fc:
            matched_truth.append(float(y))
            idx_fc.append(lookup_fc[k])
    if not idx_fc:
        return np.empty(0), fc
    yt = np.asarray(matched_truth)
    aligned = ForecastQuantiles(
        unique_id=[fc.unique_id[i] for i in idx_fc],
        ds=[pd.Timestamp(fc.ds[i]) for i in idx_fc],
        p10=fc.p10[idx_fc],
        p50=fc.p50[idx_fc],
        p90=fc.p90[idx_fc],
        model_name=fc.model_name,
    )
    return yt, aligned


def walk_forward_backtest(
    panel: pd.DataFrame,
    forecaster_factory,
    *,
    horizon: int,
    n_splits: int = 5,
    freq: str = "W",
    static_features: pd.DataFrame | None = None,
) -> list[BacktestMetrics]:
    results: list[BacktestMetrics] = []
    splits = list(walk_forward_splits(panel, horizon=horizon, n_splits=n_splits, freq=freq))
    log.info("backtest.start", n_splits=len(splits))
    for split in splits:
        train, val = apply_split(panel, split)
        if train.empty or val.empty:
            continue
        model: BaseForecaster = forecaster_factory()
        model.fit(train, static_features=static_features)
        fc = model.predict(horizon=horizon)
        yt, fc_aligned = align_truth(val, fc)
        metrics = evaluate(yt, fc_aligned, fold=split.fold)
        results.append(metrics)
        log.info(
            "backtest.fold.done",
            fold=split.fold,
            model=metrics.model_name,
            wape=round(metrics.wape, 2),
            coverage_80=round(metrics.coverage_80, 3),
        )
    return results


def summarize(results: list[BacktestMetrics]) -> pd.DataFrame:
    rows = [
        {
            "model": r.model_name,
            "fold": r.fold,
            "mape": r.mape,
            "smape": r.smape,
            "wape": r.wape,
            "rmse": r.rmse,
            "mase": r.mase,
            "pinball_p10": r.pinball_p10,
            "pinball_p50": r.pinball_p50,
            "pinball_p90": r.pinball_p90,
            "coverage_80": r.coverage_80,
            "n_obs": r.n_obs,
        }
        for r in results
    ]
    return pd.DataFrame(rows)


def scoreboard(
    results: list[BacktestMetrics],
    *,
    baseline_model: str = "seasonal_naive",
) -> pd.DataFrame:
    """Aggregate per-model metrics across folds and score each model against the
    naive baseline — the headline "is this model actually worth its complexity?"
    table.

    Columns added beyond the mean metrics:
      * ``skill_vs_naive`` = baseline WAPE / model WAPE. >1 means the model beats
        the baseline; 1.5 means it cuts error by a third relative to naive.
      * ``beats_naive``    = model WAPE strictly below the baseline's.

    ``baseline_model`` must be present in ``results`` (include a naive forecaster
    in the run). If it's absent, skill columns are NaN/False but the table still
    renders so you notice the baseline is missing.
    """
    df = summarize(results)
    if df.empty:
        return df
    agg = (
        df.groupby("model", as_index=False)
        .agg(
            wape=("wape", "mean"),
            mape=("mape", "mean"),
            mase=("mase", "mean"),
            rmse=("rmse", "mean"),
            pinball_p50=("pinball_p50", "mean"),
            coverage_80=("coverage_80", "mean"),
            folds=("fold", "nunique"),
        )
    )
    base = agg.loc[agg["model"] == baseline_model, "wape"]
    base_wape = float(base.iloc[0]) if len(base) else float("nan")
    agg["skill_vs_naive"] = base_wape / agg["wape"]
    agg["beats_naive"] = agg["wape"] < base_wape
    return agg.sort_values("wape").reset_index(drop=True)
