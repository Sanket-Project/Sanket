from __future__ import annotations

import numpy as np


def mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    yt = np.asarray(y_true, dtype="float64")
    yp = np.asarray(y_pred, dtype="float64")
    mask = np.abs(yt) > 1e-9
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs((yt[mask] - yp[mask]) / yt[mask])) * 100)


def smape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    yt = np.asarray(y_true, dtype="float64")
    yp = np.asarray(y_pred, dtype="float64")
    denom = np.abs(yt) + np.abs(yp) + 1e-9
    return float(np.mean(2 * np.abs(yt - yp) / denom) * 100)


def wape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    yt = np.asarray(y_true, dtype="float64")
    yp = np.asarray(y_pred, dtype="float64")
    return float(np.abs(yt - yp).sum() / max(np.abs(yt).sum(), 1e-9) * 100)


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    yt = np.asarray(y_true, dtype="float64")
    yp = np.asarray(y_pred, dtype="float64")
    return float(np.sqrt(np.mean((yt - yp) ** 2)))


def mase(y_true: np.ndarray, y_pred: np.ndarray, seasonality: int = 52) -> float:
    """Mean Absolute Scaled Error — scale-free, comparable across SKUs.

    Scale is the seasonal-naive MAE = mean |y_t - y_{t-s}| (a LAG-s difference).
    Note: ``np.diff(yt, n=s)`` is the s-th order difference (derivative), NOT the
    lag-s seasonal difference — using it here would be a silent bug.
    """
    yt = np.asarray(y_true, dtype="float64")
    yp = np.asarray(y_pred, dtype="float64")
    s = seasonality if yt.size > seasonality else 1
    naive_diff = np.abs(yt[s:] - yt[:-s]) if yt.size > s else np.abs(np.diff(yt))
    denom = np.mean(naive_diff) if len(naive_diff) > 0 else 1e-9
    return float(np.mean(np.abs(yt - yp)) / max(denom, 1e-9))


def pinball(y_true: np.ndarray, y_pred: np.ndarray, q: float) -> float:
    yt = np.asarray(y_true, dtype="float64")
    yp = np.asarray(y_pred, dtype="float64")
    diff = yt - yp
    return float(np.mean(np.maximum(q * diff, (q - 1) * diff)))


def coverage(y_true: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    yt = np.asarray(y_true, dtype="float64")
    return float(np.mean((yt >= lo) & (yt <= hi)))
