"""Censored-demand (lost-sales) correction.

A stockout produces a zero-sales period that does NOT mean demand was zero —
demand was *censored* by lack of availability. If a forecaster trains on the
raw series it learns "demand collapsed" and biases every future forecast (and
therefore every replenishment order) downward, which causes *more* stockouts.
This is the single most common source of systematic forecast bias in retail.

This module unconstrains demand before training:

  1. Identify censored periods.
       * Explicit path — an availability signal (fraction of the period the SKU
         was in stock) is present: a period is censored when availability falls
         below a threshold.
       * Heuristic path — no availability signal exists: only *regularly selling*
         series (smooth/erratic by Syntetos-Boylan ADI/CV²) have their in-span
         zeros treated as suspected stockouts. Intermittent / lumpy / all-zero
         series are left untouched, because for those a zero is genuine demand
         information, not a stockout.
  2. Impute the censored periods with an estimate of true demand built from the
     SKU's own in-stock observations (local rolling median × seasonal index),
     never reducing the observed value.
  3. Leave lifecycle zeros alone — leading zeros before a SKU's first sale
     (pre-launch / not-yet-assorted) and trailing zeros after its last sale
     (discontinued) are never imputed.

The correction is intentionally conservative: when in doubt it does nothing.
It no-ops cleanly on panels with no availability column and no regularly-selling
series, so it is always safe to call.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import structlog

from sanket_ml.data.features import add_intermittency_flags

log = structlog.get_logger(__name__)

# Demand classes (Syntetos-Boylan) whose in-span zeros we are willing to treat
# as suspected stockouts when no explicit availability signal is available.
# Intermittent / lumpy series legitimately sell in bursts, so their zeros carry
# real demand information and must not be imputed.
_HEURISTIC_ELIGIBLE_CLASSES = frozenset({"smooth", "erratic"})


@dataclass(frozen=True, slots=True)
class CensoringReport:
    """Summary of what the correction touched. Safe to log / persist as run
    metadata so the imputation is auditable."""
    n_series: int = 0
    n_series_corrected: int = 0
    n_obs: int = 0
    n_obs_imputed: int = 0
    detection_mode: str = "none"  # "explicit" | "heuristic" | "mixed" | "none"
    units_added: float = 0.0      # total demand restored (Σ imputed − observed)

    @property
    def imputed_fraction(self) -> float:
        return self.n_obs_imputed / self.n_obs if self.n_obs else 0.0

    def as_dict(self) -> dict:
        return {
            "n_series": self.n_series,
            "n_series_corrected": self.n_series_corrected,
            "n_obs": self.n_obs,
            "n_obs_imputed": self.n_obs_imputed,
            "imputed_fraction": round(self.imputed_fraction, 4),
            "detection_mode": self.detection_mode,
            "units_added": round(self.units_added, 2),
        }


@dataclass(frozen=True, slots=True)
class CensoringResult:
    data: pd.DataFrame          # corrected panel: `y` unconstrained in place
    report: CensoringReport


def _season_index(
    ds: pd.Series,
    y: np.ndarray,
    eligible: np.ndarray,
    *,
    seasonal_period: int,
) -> np.ndarray:
    """Multiplicative seasonal index per observation from in-stock demand.

    Returns an array the same length as `y`; entries default to 1.0 when there
    is not enough clean history to estimate seasonality robustly.
    """
    out = np.ones(len(y), dtype="float64")
    clean = eligible & (y > 0)
    # Need more than one full cycle of clean observations to trust seasonality.
    if clean.sum() < int(1.5 * seasonal_period):
        return out

    week = pd.to_datetime(ds).dt.isocalendar().week.to_numpy().astype("int64")
    global_mean = y[clean].mean()
    if global_mean <= 0:
        return out
    for w in np.unique(week):
        mask = clean & (week == w)
        if mask.sum() >= 2:
            out[week == w] = y[mask].mean() / global_mean
    # Guard against pathological factors from sparse weeks.
    return np.clip(out, 0.25, 4.0)


def _correct_series(
    g: pd.DataFrame,
    *,
    ds_col: str,
    target_col: str,
    availability_col: str | None,
    availability_threshold: float,
    heuristic_when_missing: bool,
    demand_class: str,
    local_window: int,
    seasonal_period: int,
    min_history: int,
) -> tuple[np.ndarray, np.ndarray, str]:
    """Return (corrected_y, is_censored_mask, mode) for one series."""
    g = g.sort_values(ds_col)
    y = g[target_col].to_numpy(dtype="float64")
    n = len(y)
    censored = np.zeros(n, dtype=bool)
    mode = "none"

    if n < min_history:
        return y, censored, mode

    # Active span: between the first and last positive sale. Outside this span
    # zeros are lifecycle (pre-launch / discontinued), never censoring.
    nz = np.flatnonzero(y > 0)
    if len(nz) == 0:
        return y, censored, mode  # all-zero series — nothing to unconstrain
    first, last = nz[0], nz[-1]
    in_span = np.zeros(n, dtype=bool)
    in_span[first : last + 1] = True

    # ── Detection ────────────────────────────────────────────────────────
    have_explicit = (
        availability_col is not None
        and availability_col in g.columns
        and not g[availability_col].isna().all()
    )
    if have_explicit:
        avail = g[availability_col].to_numpy(dtype="float64")
        # Unknown availability (NaN) is treated as in-stock so we never invent
        # stockouts from missing data.
        oos = np.where(np.isnan(avail), 1.0, avail) < availability_threshold
        censored = in_span & oos
        mode = "explicit"
    elif heuristic_when_missing and demand_class in _HEURISTIC_ELIGIBLE_CLASSES:
        # Regularly-selling item: an in-span zero is a suspected stockout.
        censored = in_span & (y <= 0)
        mode = "heuristic"

    if not censored.any():
        return y, censored, mode

    # ── Imputation ───────────────────────────────────────────────────────
    # Baseline expectation from clean (non-censored, in-span) observations.
    clean = in_span & ~censored
    clean_pos = clean & (y > 0)
    if clean_pos.sum() == 0:
        # No clean signal to learn true demand from — abstain.
        return y, np.zeros(n, dtype=bool), mode

    global_med = float(np.median(y[clean_pos]))

    # Local rolling median over clean observations (NaN-out censored points so
    # they don't drag the local estimate down), centered on each period.
    clean_series = pd.Series(np.where(clean_pos, y, np.nan))
    local = (
        clean_series.rolling(window=local_window, min_periods=2, center=True)
        .median()
        .to_numpy()
    )
    local = np.where(np.isnan(local), global_med, local)

    season = _season_index(g[ds_col], y, clean_pos, seasonal_period=seasonal_period)
    estimate = local * season

    corrected = y.copy()
    # Never reduce demand below what was actually observed in that period.
    corrected[censored] = np.maximum(estimate[censored], y[censored])
    return corrected, censored, mode


def correct_censored_demand(
    df: pd.DataFrame,
    *,
    id_col: str = "unique_id",
    ds_col: str = "ds",
    target_col: str = "y",
    availability_col: str | None = "in_stock_frac",
    availability_threshold: float = 0.5,
    heuristic_when_missing: bool = True,
    local_window: int = 8,
    seasonal_period: int = 52,
    min_history: int = 12,
    add_flags: bool = True,
) -> CensoringResult:
    """Unconstrain censored (stockout) demand in a long-format panel.

    The input panel must have ``[id_col, ds_col, target_col]``. If
    ``availability_col`` is present and not entirely null it drives detection;
    otherwise a conservative ADI/CV²-gated heuristic is used (controlled by
    ``heuristic_when_missing``).

    The returned DataFrame has ``target_col`` corrected in place. When
    ``add_flags`` is true it also gains:
      * ``{target_col}_raw``   — the original (censored) values
      * ``is_censored``        — 1 where demand was imputed, else 0

    Always safe to call: panels with no availability signal and no regularly
    selling series are returned unchanged (report.n_obs_imputed == 0).
    """
    if df.empty or not {id_col, ds_col, target_col}.issubset(df.columns):
        return CensoringResult(data=df, report=CensoringReport())

    out = df.copy()
    out[ds_col] = pd.to_datetime(out[ds_col])

    # Demand-class per series (single source of truth: features.add_intermittency_flags).
    need_heuristic = (
        heuristic_when_missing
        and (availability_col is None or availability_col not in out.columns
             or out[availability_col].isna().all())
    )
    class_by_uid: dict[str, str] = {}
    if need_heuristic:
        flagged = add_intermittency_flags(out, id_col=id_col, target_col=target_col)
        class_by_uid = (
            flagged.drop_duplicates(id_col).set_index(id_col)["demand_class"].to_dict()
        )

    # Reset index so positional scatter-back is unambiguous.
    out = out.reset_index(drop=True)
    raw = out[target_col].to_numpy(dtype="float64").copy()
    corrected_all = raw.copy()
    censored_all = np.zeros(len(out), dtype=bool)
    modes: set[str] = set()
    n_series_corrected = 0

    for uid, g in out.groupby(id_col, sort=False):
        corrected, censored, mode = _correct_series(
            g,
            ds_col=ds_col,
            target_col=target_col,
            availability_col=availability_col,
            availability_threshold=availability_threshold,
            heuristic_when_missing=heuristic_when_missing,
            demand_class=class_by_uid.get(str(uid), "smooth"),
            local_window=local_window,
            seasonal_period=seasonal_period,
            min_history=min_history,
        )
        # `corrected`/`censored` follow g's ds-sorted order; map back via g's index.
        order = g.sort_values(ds_col).index.to_numpy()
        corrected_all[order] = corrected
        censored_all[order] = censored
        if censored.any():
            n_series_corrected += 1
            if mode != "none":
                modes.add(mode)

    out[target_col] = corrected_all
    if add_flags:
        out[f"{target_col}_raw"] = raw
        out["is_censored"] = censored_all.astype("int8")

    detection_mode = (
        "mixed" if len(modes) > 1 else (next(iter(modes)) if modes else "none")
    )
    report = CensoringReport(
        n_series=int(out[id_col].nunique()),
        n_series_corrected=n_series_corrected,
        n_obs=len(out),
        n_obs_imputed=int(censored_all.sum()),
        detection_mode=detection_mode,
        units_added=float((corrected_all - raw)[censored_all].sum()),
    )
    log.info("censoring.done", **report.as_dict())
    return CensoringResult(data=out, report=report)
