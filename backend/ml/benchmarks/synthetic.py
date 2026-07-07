"""Synthetic but realistic weekly demand panels for offline benchmarking.

Generates a mix of the demand archetypes SANKET actually serves, so the
benchmark exercises the cases where models genuinely differ:

  * smooth_seasonal — strong annual seasonality + mild trend (fashion-like).
  * trending        — level shift / growth with weak seasonality (electronics).
  * intermittent    — many zero weeks with occasional demand (spare parts / pharma).
  * promo_spiky     — baseline plus sharp promo weeks (hardware/retail).

Deterministic given ``seed`` so benchmark runs are reproducible.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_PROFILES = ("smooth_seasonal", "trending", "intermittent", "promo_spiky")


def make_demand_panel(
    *,
    n_series: int = 40,
    weeks: int = 156,
    season: int = 52,
    seed: int = 7,
    start: str = "2023-01-01",
) -> pd.DataFrame:
    """Return a long-format panel with columns [unique_id, ds, y] (weekly).

    Dates use pandas ``freq="W"`` (Sunday-anchored) to match the production
    loader and the backtest harness, so forecast timestamps align with truth.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start=start, periods=weeks, freq="W")
    t = np.arange(weeks)
    rows: list[pd.DataFrame] = []

    for i in range(n_series):
        profile = _PROFILES[i % len(_PROFILES)]
        level = float(rng.uniform(40, 400))
        seasonal_amp = rng.uniform(0.15, 0.55)
        phase = rng.uniform(0, 2 * np.pi)
        seasonal = 1.0 + seasonal_amp * np.sin(2 * np.pi * t / season + phase)

        if profile == "smooth_seasonal":
            trend = 1.0 + rng.uniform(-0.1, 0.25) * (t / weeks)
            mean = level * seasonal * trend
            y = rng.normal(mean, 0.08 * mean)
        elif profile == "trending":
            trend = 1.0 + rng.uniform(0.2, 0.9) * (t / weeks)
            mean = level * (0.6 + 0.4 * seasonal) * trend
            y = rng.normal(mean, 0.10 * mean)
        elif profile == "intermittent":
            p_demand = rng.uniform(0.2, 0.5)
            occurs = rng.random(weeks) < p_demand
            size = rng.gamma(shape=2.0, scale=level / 6, size=weeks)
            y = np.where(occurs, size, 0.0)
        else:  # promo_spiky
            mean = level * (0.7 + 0.3 * seasonal)
            y = rng.normal(mean, 0.07 * mean)
            promo = rng.random(weeks) < 0.08
            y = y + promo * rng.uniform(1.5, 3.5) * level

        y = np.clip(np.round(y), 0, None)
        rows.append(
            pd.DataFrame(
                {
                    "unique_id": f"{profile}_{i:03d}",
                    "ds": dates,
                    "y": y.astype("float64"),
                }
            )
        )

    return pd.concat(rows, ignore_index=True)
