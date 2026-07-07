from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import structlog
from scipy.stats import entropy, ks_2samp, wasserstein_distance

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DriftReport:
    feature: str
    psi: float
    kl_divergence: float
    ks_statistic: float
    ks_p_value: float
    wasserstein: float
    drifted: bool
    severity: str  # "ok" | "warning" | "critical"


def _bin_with_baseline(reference: np.ndarray, current: np.ndarray, bins: int = 20) -> tuple[np.ndarray, np.ndarray]:
    edges = np.quantile(reference, np.linspace(0, 1, bins + 1))
    edges = np.unique(edges)
    if len(edges) < 3:
        edges = np.linspace(reference.min(), reference.max() + 1e-9, bins + 1)
    ref_hist, _ = np.histogram(reference, bins=edges)
    cur_hist, _ = np.histogram(current, bins=edges)
    ref_p = ref_hist / max(ref_hist.sum(), 1)
    cur_p = cur_hist / max(cur_hist.sum(), 1)
    eps = 1e-6
    ref_p = np.clip(ref_p, eps, None)
    cur_p = np.clip(cur_p, eps, None)
    return ref_p, cur_p


def population_stability_index(reference: np.ndarray, current: np.ndarray, bins: int = 20) -> float:
    """PSI: classical drift metric used in credit risk; >0.2 typically alarming."""
    ref_p, cur_p = _bin_with_baseline(reference, current, bins)
    return float(np.sum((cur_p - ref_p) * np.log(cur_p / ref_p)))


def kl_divergence(reference: np.ndarray, current: np.ndarray, bins: int = 20) -> float:
    ref_p, cur_p = _bin_with_baseline(reference, current, bins)
    return float(entropy(cur_p, ref_p))


def feature_drift_report(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    *,
    features: list[str] | None = None,
    psi_warning: float = 0.1,
    psi_critical: float = 0.25,
) -> list[DriftReport]:
    features = features or [
        c for c in reference.columns
        if c in current.columns and pd.api.types.is_numeric_dtype(reference[c])
    ]
    reports: list[DriftReport] = []
    for f in features:
        r = reference[f].dropna().to_numpy()
        c = current[f].dropna().to_numpy()
        if len(r) < 10 or len(c) < 10:
            continue
        psi = population_stability_index(r, c)
        kl = kl_divergence(r, c)
        ks_stat, ks_p = ks_2samp(r, c)
        wd = wasserstein_distance(r, c)
        severity = "ok"
        if psi >= psi_critical:
            severity = "critical"
        elif psi >= psi_warning:
            severity = "warning"
        reports.append(
            DriftReport(
                feature=f,
                psi=psi,
                kl_divergence=kl,
                ks_statistic=float(ks_stat),
                ks_p_value=float(ks_p),
                wasserstein=float(wd),
                drifted=severity != "ok",
                severity=severity,
            )
        )
    return sorted(reports, key=lambda r: -r.psi)


def prediction_drift(
    reference_predictions: np.ndarray,
    current_predictions: np.ndarray,
    threshold: float = 0.2,
) -> tuple[float, bool]:
    psi = population_stability_index(reference_predictions, current_predictions)
    return psi, psi >= threshold
