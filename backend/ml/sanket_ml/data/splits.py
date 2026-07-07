from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True, slots=True)
class TimeSplit:
    train_end: pd.Timestamp
    val_start: pd.Timestamp
    val_end: pd.Timestamp
    fold: int


def walk_forward_splits(
    df: pd.DataFrame,
    *,
    ds_col: str = "ds",
    horizon: int = 26,
    n_splits: int = 5,
    gap: int = 0,
    freq: str = "W",
) -> Iterator[TimeSplit]:
    """Walk-forward (expanding-window) cross-validation splits.

    Each fold: train on [start, t], validate on (t+gap, t+gap+horizon].
    """
    if df.empty:
        return
    ts = pd.to_datetime(df[ds_col])
    dates = pd.date_range(ts.min(), ts.max(), freq=freq)
    n = len(dates)
    needed = horizon * n_splits + gap + 4
    if n < needed:
        # Reduce splits to what we can support
        n_splits = max(1, (n - gap - 4) // horizon)

    for k in range(n_splits, 0, -1):
        val_end_idx = n - (n_splits - k) * horizon
        val_end_idx = min(val_end_idx, n - 1)
        val_start_idx = val_end_idx - horizon + 1
        train_end_idx = val_start_idx - gap - 1
        if train_end_idx <= 0:
            continue
        yield TimeSplit(
            train_end=dates[train_end_idx],
            val_start=dates[val_start_idx],
            val_end=dates[val_end_idx],
            fold=k,
        )


def apply_split(
    df: pd.DataFrame, split: TimeSplit, ds_col: str = "ds"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ts = pd.to_datetime(df[ds_col])
    train = df[ts <= split.train_end].copy()
    val = df[(ts >= split.val_start) & (ts <= split.val_end)].copy()
    return train, val


def holdout_split(
    df: pd.DataFrame, horizon: int, ds_col: str = "ds", freq: str = "W"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Last `horizon` periods become the holdout test set."""
    ts = pd.to_datetime(df[ds_col])
    cutoff = ts.max() - pd.tseries.frequencies.to_offset(freq) * horizon
    train = df[ts <= cutoff].copy()
    test = df[ts > cutoff].copy()
    return train, test
