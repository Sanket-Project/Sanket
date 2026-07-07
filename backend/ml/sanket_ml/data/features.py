from __future__ import annotations

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger(__name__)


def build_calendar_features(df: pd.DataFrame, ds_col: str = "ds") -> pd.DataFrame:
    """Add calendar features useful for nearly every retail forecast."""
    out = df.copy()
    s = pd.to_datetime(out[ds_col])
    out["year"] = s.dt.year.astype("int16")
    out["month"] = s.dt.month.astype("int8")
    out["week"] = s.dt.isocalendar().week.astype("int8")
    out["dow"] = s.dt.dayofweek.astype("int8")
    out["dom"] = s.dt.day.astype("int8")
    out["quarter"] = s.dt.quarter.astype("int8")
    out["is_month_start"] = s.dt.is_month_start.astype("int8")
    out["is_month_end"] = s.dt.is_month_end.astype("int8")
    out["is_quarter_end"] = s.dt.is_quarter_end.astype("int8")
    out["sin_woy"] = np.sin(2 * np.pi * out["week"] / 52).astype("float32")
    out["cos_woy"] = np.cos(2 * np.pi * out["week"] / 52).astype("float32")
    out["sin_moy"] = np.sin(2 * np.pi * out["month"] / 12).astype("float32")
    out["cos_moy"] = np.cos(2 * np.pi * out["month"] / 12).astype("float32")
    return out


def add_lag_features(
    df: pd.DataFrame,
    *,
    id_col: str = "unique_id",
    target_col: str = "y",
    lags: tuple[int, ...] = (1, 2, 3, 4, 8, 13, 26, 52),
) -> pd.DataFrame:
    out = df.copy().sort_values([id_col, "ds"])
    grp = out.groupby(id_col, sort=False)[target_col]
    for lag in lags:
        out[f"y_lag_{lag}"] = grp.shift(lag).astype("float32")
    return out


def add_rolling_features(
    df: pd.DataFrame,
    *,
    id_col: str = "unique_id",
    target_col: str = "y",
    windows: tuple[int, ...] = (4, 8, 13, 26, 52),
    shift: int = 1,
) -> pd.DataFrame:
    out = df.copy().sort_values([id_col, "ds"])
    base = out.groupby(id_col, sort=False)[target_col].shift(shift)
    for w in windows:
        roll = base.groupby(out[id_col], sort=False).rolling(w, min_periods=max(2, w // 2))
        out[f"y_roll_mean_{w}"] = roll.mean().reset_index(level=0, drop=True).astype("float32")
        out[f"y_roll_std_{w}"] = roll.std().reset_index(level=0, drop=True).astype("float32")
        out[f"y_roll_min_{w}"] = roll.min().reset_index(level=0, drop=True).astype("float32")
        out[f"y_roll_max_{w}"] = roll.max().reset_index(level=0, drop=True).astype("float32")
    return out


def add_ewm_features(
    df: pd.DataFrame,
    *,
    id_col: str = "unique_id",
    target_col: str = "y",
    alphas: tuple[float, ...] = (0.1, 0.3, 0.5),
    shift: int = 1,
) -> pd.DataFrame:
    out = df.copy().sort_values([id_col, "ds"])
    base = out.groupby(id_col, sort=False)[target_col].shift(shift)
    for a in alphas:
        out[f"y_ewm_{a}"] = (
            base.groupby(out[id_col], sort=False)
                .apply(lambda s, alpha_val=a: s.ewm(alpha=alpha_val, adjust=False).mean())
                .reset_index(level=0, drop=True)
                .astype("float32")
        )
    return out


def add_intermittency_flags(
    df: pd.DataFrame,
    *,
    id_col: str = "unique_id",
    target_col: str = "y",
) -> pd.DataFrame:
    """Per-series average inter-demand interval (ADI) and CV² of demand,
    which classify a series as smooth, intermittent, erratic, or lumpy
    (Syntetos & Boylan 2005). Used to route series to Croston vs. ML models."""
    out = df.copy()
    stats: list[dict] = []
    for uid, g in df.groupby(id_col, sort=False):
        y = g[target_col].to_numpy()
        nonzero = y > 0
        n = len(y)
        d = int(nonzero.sum())
        if d == 0:
            adi = float("inf")
            cv2 = 0.0
            cls = "all_zero"
        else:
            adi = n / d
            nz = y[nonzero]
            cv2 = float((nz.std() / nz.mean()) ** 2) if nz.mean() > 0 else 0.0
            if adi < 1.32 and cv2 < 0.49:
                cls = "smooth"
            elif adi >= 1.32 and cv2 < 0.49:
                cls = "intermittent"
            elif adi < 1.32 and cv2 >= 0.49:
                cls = "erratic"
            else:
                cls = "lumpy"
        stats.append({id_col: uid, "adi": adi, "cv2": cv2, "demand_class": cls})
    stats_df = pd.DataFrame(stats)
    return out.merge(stats_df, on=id_col, how="left")


def join_signals(
    panel: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    industry: str,
    decay_halflife_days: float = 14.0,
) -> pd.DataFrame:
    """Attach exogenous signal features to a panel by date with exponential decay
    so old signals fade out (avoids leakage of stale macro/regulatory news)."""
    if signals.empty:
        return panel

    out = panel.copy()
    out["ds"] = pd.to_datetime(out["ds"])
    signals = signals.copy()
    signals["ds"] = pd.to_datetime(signals["ds"])
    np.log(2) / decay_halflife_days

    pivot_pieces: list[pd.DataFrame] = []
    for stype, g in signals.groupby("signal_type"):
        g2 = g.sort_values("ds")
        # For each panel ds, compute weighted aggregate of signals occurring before
        # We use a merge_asof + ewm trick over the time axis.
        ts = (
            g2.groupby("ds")
              .agg(
                  value=("processed_value", "mean"),
                  sentiment=("sentiment_score", "mean"),
                  weight=("impact_weight", "mean"),
              )
              .reset_index()
        )
        ts["value"] = ts["value"].fillna(0.0)
        ts["sentiment"] = ts["sentiment"].fillna(0.0)
        ts["weight"] = ts["weight"].fillna(1.0)

        # Resample to daily, fill forward decayed
        daily_idx = pd.date_range(ts["ds"].min(), ts["ds"].max(), freq="D")
        ts = ts.set_index("ds").reindex(daily_idx).fillna(0.0)
        ts[f"sig_{stype}_value"] = (
            ts["value"].ewm(halflife=decay_halflife_days, adjust=False).mean().astype("float32")
        )
        ts[f"sig_{stype}_sentiment"] = (
            ts["sentiment"].ewm(halflife=decay_halflife_days, adjust=False).mean().astype("float32")
        )
        ts = ts[[f"sig_{stype}_value", f"sig_{stype}_sentiment"]].reset_index().rename(columns={"index": "ds"})
        pivot_pieces.append(ts)

    if not pivot_pieces:
        return out

    merged = pivot_pieces[0]
    for p in pivot_pieces[1:]:
        merged = merged.merge(p, on="ds", how="outer")
    merged = merged.sort_values("ds").fillna(0.0)

    out = pd.merge_asof(
        out.sort_values("ds"),
        merged.sort_values("ds"),
        on="ds",
        direction="backward",
    )
    sig_cols = [c for c in out.columns if c.startswith("sig_")]
    for c in sig_cols:
        out[c] = out[c].fillna(0.0).astype("float32")
    return out


def build_feature_matrix(
    panel: pd.DataFrame,
    signals: pd.DataFrame | None = None,
    *,
    industry: str = "fashion",
) -> pd.DataFrame:
    """End-to-end feature engineering for gradient-boosting forecasters."""
    df = build_calendar_features(panel)
    df = add_lag_features(df)
    df = add_rolling_features(df)
    df = add_ewm_features(df)
    df = add_intermittency_flags(df)
    if signals is not None and not signals.empty:
        df = join_signals(df, signals, industry=industry)
    return df.dropna(subset=["y_lag_1"]).reset_index(drop=True)
