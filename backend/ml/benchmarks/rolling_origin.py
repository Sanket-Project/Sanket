"""Frozen-cutoff diagnostic on labelled synthetic fashion data; never client accuracy.

Run from backend/ml: python -m benchmarks.rolling_origin --out <directory>
Models receive training rows only. Routing is frozen before the test fold is scored.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

SEED = 25102026
VALIDATION = ["2026-04-13", "2026-05-11", "2026-06-08", "2026-07-06"]
TEST = "2026-08-31"


@dataclass
class Fold:
    cutoff: pd.Timestamp
    train: pd.DataFrame
    test: pd.DataFrame
    omitted: dict[str, str]

    def __post_init__(self):
        assert self.train.empty or self.train.ds.max() < self.cutoff, "training leakage"
        assert self.test.empty or self.cutoff <= self.test.ds.min(), "test leakage"


@dataclass
class Model:
    predict: Callable[[pd.DataFrame, int], pd.DataFrame]
    min_history: int = 8


def load_fixture(training_csv, heldout_csv) -> pd.DataFrame:
    raw = pd.concat([pd.read_csv(training_csv), pd.read_csv(heldout_csv)], ignore_index=True)
    raw["unique_id"] = raw["sku"].astype(str)
    dates = pd.to_datetime(raw["date"], utc=True).dt.tz_localize(None)
    raw["ds"] = dates.dt.normalize() - pd.to_timedelta(dates.dt.dayofweek, unit="d")
    raw["y"] = pd.to_numeric(raw["quantity"], errors="raise")
    if not np.isfinite(raw.y).all() or (raw.y < 0).any():
        raise ValueError("sales must be finite and nonnegative")
    weekly = raw.groupby(["unique_id", "ds"], as_index=False).y.sum()
    pieces = []
    for uid, group in weekly.groupby("unique_id"):
        weeks = pd.date_range(group.ds.min(), weekly.ds.max(), freq="W-MON")
        values = group.set_index("ds").y.reindex(weeks, fill_value=0)
        pieces.append(pd.DataFrame({"unique_id": uid, "ds": weeks, "y": values.to_numpy()}))
    return pd.concat(pieces, ignore_index=True)


def folds(panel, cutoffs, horizon) -> list[Fold]:
    if horizon < 1 or panel.duplicated(["unique_id", "ds"]).any():
        raise ValueError("positive horizon and unique SKU-weeks required")
    if not (panel.ds.dt.dayofweek == 0).all():
        raise ValueError("panel dates must be Monday")
    if not np.isfinite(panel.y.to_numpy(dtype=float)).all() or (panel.y < 0).any():
        raise ValueError("actuals must be finite and nonnegative")
    result = []
    for value in cutoffs:
        cutoff = pd.Timestamp(value)
        if cutoff.dayofweek != 0:
            raise ValueError("cutoff must be Monday")
        train = panel[panel.ds < cutoff].copy()
        counts = train.groupby("unique_id").size()
        omitted = {str(uid): "insufficient_history" for uid in panel.unique_id.unique() if counts.get(uid, 0) < 8}
        train = train[~train.unique_id.isin(omitted)]
        test = panel[(panel.ds >= cutoff) & (panel.ds < cutoff + pd.Timedelta(weeks=horizon))].copy()
        result.append(Fold(cutoff, train, test, omitted))
    return result


def score(rows: pd.DataFrame) -> dict:
    actual = rows.y.to_numpy(dtype=float)
    prediction = rows.p50.to_numpy(dtype=float)
    denominator = float(np.abs(actual).sum())
    return {
        "points": len(rows),
        "wape": float(np.abs(prediction - actual).sum() / denominator * 100) if denominator else None,
        "bias_pct": float((prediction - actual).sum() / denominator * 100) if denominator else None,
        "coverage_p10_p90": float(((rows.y >= rows.p10) & (rows.y <= rows.p90)).mean() * 100)
        if len(rows) and {"p10", "p90"} <= set(rows) and rows[["p10", "p90"]].notna().all().all() else None,
    }


def _run(fold: Fold, model: Model, horizon: int):
    counts = fold.train.groupby("unique_id").size()
    eligible = counts[counts >= model.min_history].index
    train = fold.train[fold.train.unique_id.isin(eligible)].copy()
    omitted = dict(fold.omitted)
    omitted.update({str(uid): f"requires_{model.min_history}_weeks" for uid in counts.index if uid not in eligible})
    if train.empty:
        return pd.DataFrame(columns=["unique_id", "ds", "y", "p50"]), omitted
    forecast = model.predict(train, horizon)
    expected = fold.test[fold.test.unique_id.isin(eligible)]
    key = ["unique_id", "ds"]
    grid = {(uid, ds) for uid in eligible for ds in pd.date_range(fold.cutoff, periods=horizon, freq="W-MON")}
    if set(map(tuple, expected[key].to_numpy())) != grid:
        raise ValueError("test data must contain a complete horizon grid")
    if forecast.duplicated(key).any() or set(map(tuple, forecast[key].to_numpy())) != set(map(tuple, expected[key].to_numpy())):
        raise ValueError("forecast dates must match complete test SKU-weeks exactly")
    columns = [c for c in ("p10", "p50", "p90") if c in forecast]
    if not np.isfinite(forecast[columns].to_numpy(dtype=float)).all():
        raise ValueError("predictions must be finite")
    joined = expected.merge(forecast, on=key, validate="one_to_one")
    return joined, omitted


def _summary(rows, omitted):
    return {**score(rows), "skus": int(rows.unique_id.nunique()), "omitted": omitted,
            "per_sku": {str(uid): score(group) for uid, group in rows.groupby("unique_id")}}


def evaluate(panel, models: dict[str, Model], val_cutoffs, test_cutoff, horizon) -> dict:
    test_cutoff = pd.Timestamp(test_cutoff)
    if not val_cutoffs or any(pd.Timestamp(c) + pd.Timedelta(weeks=horizon) > test_cutoff for c in val_cutoffs):
        raise ValueError("validation windows must not overlap the test fold")
    validation = folds(panel, val_cutoffs, horizon)
    test_fold = folds(panel, [test_cutoff], horizon)[0]
    val_rows, reports = {}, {}
    for name, model in models.items():
        scored = [_run(fold, model, horizon) for fold in validation]
        for fold, (rows, _) in zip(validation, scored):
            rows["fold"] = str(fold.cutoff.date())
        val_rows[name] = pd.concat([r for r, _ in scored], ignore_index=True)
        reports[name] = {"validation": _summary(val_rows[name], {}),
                         "folds": [{"cutoff": str(fold.cutoff.date()), **_summary(rows, omitted)}
                                   for fold, (rows, omitted) in zip(validation, scored)]}

    # Freeze routing from validation only. A candidate must cover ALL validation
    # points for that SKU, so an easy subset cannot win through selective omission.
    reference = val_rows["chronos"]
    per_sku = {}
    for uid, group in reference.groupby("unique_id"):
        candidates = {}
        for name, rows in val_rows.items():
            sample = rows[rows.unique_id == uid]
            keys = ["unique_id", "ds", "fold"]
            if set(map(tuple, sample[keys].to_numpy())) == set(map(tuple, group[keys].to_numpy())) and score(sample)["wape"] is not None:
                candidates[name] = score(sample)["wape"]
        per_sku[str(uid)] = min(candidates, key=candidates.get) if candidates else "chronos"
    # Cohorts/rule use history before the earliest validation cutoff, never heldout.
    first = validation[0].train
    cohorts = {str(uid): ("intermittent" if (g.y == 0).mean() > .5 else "regular") for uid, g in first.groupby("unique_id")}
    intermittent = {uid: "adida" if cohort == "intermittent" and "adida" in models else "chronos" for uid, cohort in cohorts.items()}

    def route(rows_by_model, mapping):
        baseline = rows_by_model["chronos"]
        parts = [rows_by_model[mapping.get(str(uid), "chronos")][rows_by_model[mapping.get(str(uid), "chronos")].unique_id == uid]
                 for uid in baseline.unique_id.unique()]
        routed = pd.concat(parts, ignore_index=True) if parts else baseline.iloc[:0]
        keys = ["unique_id", "ds"] + (["fold"] if "fold" in baseline else [])
        if set(map(tuple, routed[keys].to_numpy())) != set(map(tuple, baseline[keys].to_numpy())):
            raise ValueError("routing must score the same SKU-weeks as Chronos")
        return routed

    rules = {"per_sku": per_sku, "intermittency": intermittent}
    rule_scores = {name: score(route(val_rows, mapping)) for name, mapping in rules.items()}
    chosen = min(rules, key=lambda name: rule_scores[name]["wape"] if rule_scores[name]["wape"] is not None else float("inf"))
    # Only now execute the untouched test fold.
    test_rows = {}
    for name, model in models.items():
        rows, omitted = _run(test_fold, model, horizon)
        test_rows[name] = rows
        reports[name]["test"] = _summary(rows, omitted)
        for uid in rows.unique_id.unique():
            cohorts.setdefault(str(uid), "new_since_validation")
        reports[name]["test"]["per_cohort"] = {cohort: score(rows[rows.unique_id.isin([uid for uid, c in cohorts.items() if c == cohort])]) for cohort in sorted(set(cohorts.values()))}
        values = [f["wape"] for f in reports[name]["folds"] if f["wape"] is not None]
        reports[name]["validation_spread"] = {"min_wape": min(values) if values else None, "max_wape": max(values) if values else None}
    routed_test = score(route(test_rows, rules[chosen]))
    val_score = rule_scores[chosen]["wape"]
    baseline_val = score(reference)["wape"]
    baseline_test = score(test_rows["chronos"])["wape"]
    eligible = all(v is not None for v in (val_score, baseline_val, baseline_test, routed_test["wape"])) and val_score < baseline_val and routed_test["wape"] < baseline_test
    return {"synthetic_only": True, "calendar": "W-MON-UTC", "seed": SEED,
            "validation_cutoffs": [str(pd.Timestamp(c).date()) for c in val_cutoffs], "test_cutoff": str(test_cutoff.date()), "horizon": horizon,
            "models": reports, "cohorts": cohorts,
            "routing": {"per_sku": per_sku, "rules": rules, "selected_rule": chosen, "validation_rules": rule_scores,
                        "validation": rule_scores[chosen], "test": routed_test, "eligible_for_production": bool(eligible)}}


def chronos_training(train, settings):
    """Apply production preprocessing to the training window only."""
    if not settings.censoring_enabled:
        return train
    from sanket_ml.data.censoring import correct_censored_demand
    return correct_censored_demand(
        train,
        availability_threshold=settings.censoring_availability_threshold,
        heuristic_when_missing=settings.censoring_heuristic_when_missing,
        local_window=settings.censoring_local_window,
        seasonal_period=settings.censoring_seasonal_period,
        min_history=settings.censoring_min_history,
    ).data


def real_models(settings):
    import torch
    from sanket_ml.inference.zero_shot import get_chronos_pipeline
    from sanket_ml.models.adida import ADIDAForecaster
    from statsforecast.models import CrostonSBA

    def adapter(method):
        def predict(train, horizon):
            pieces = []
            if method == "chronos":
                train = chronos_training(train, settings)
            groups = list(train.sort_values("ds").groupby("unique_id", sort=True))
            quantiles = None
            if method == "chronos":
                torch.manual_seed(SEED)
                pipeline = get_chronos_pipeline(settings)
                contexts = [torch.tensor(g.y.to_numpy()[-settings.zero_shot_default_context_weeks:], dtype=torch.float32) for _, g in groups]
                with torch.inference_mode():
                    samples = pipeline.predict(contexts, prediction_length=horizon, num_samples=settings.zero_shot_num_samples)
                quantiles = np.quantile(samples.cpu().numpy(), [.1, .5, .9], axis=1)
            for i, (uid, group) in enumerate(groups):
                y = group.y.to_numpy(dtype=float)
                dates = pd.date_range(group.ds.max() + pd.Timedelta(weeks=1), periods=horizon, freq="W-MON")
                frame = pd.DataFrame({"unique_id": uid, "ds": dates})
                if method == "chronos":
                    for j, column in enumerate(("p10", "p50", "p90")):
                        frame[column] = np.clip(quantiles[j, i], 0, None)
                elif method == "last_value":
                    frame["p50"] = y[-1]
                elif method == "ma4":
                    frame["p50"] = y[-4:].mean()
                elif method == "seasonal_naive52":
                    frame["p50"] = y[-52:][np.arange(horizon) % 52]
                elif method == "croston_sba":
                    frame["p50"] = CrostonSBA().forecast(y=y, h=horizon)["mean"]
                elif method == "adida":
                    prediction = ADIDAForecaster(horizon=horizon).forecast(str(uid), pd.Series(y))
                    for column in ("p10", "p50", "p90"):
                        frame[column] = getattr(prediction, column)
                pieces.append(frame)
            return pd.concat(pieces, ignore_index=True)
        return predict
    return {name: Model(adapter(name), 52 if name == "seasonal_naive52" else 8)
            for name in ("chronos", "last_value", "ma4", "seasonal_naive52", "croston_sba", "adida")}


def main():
    from sanket_ml.config import MLSettings
    import torch
    import platform
    from importlib.metadata import version
    from sanket_ml.inference.zero_shot import get_chronos_pipeline
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[3]
    fixture = root / "docs/audit/2026-10-25-fashion-readiness"
    parser.add_argument("--training", type=Path, default=fixture / "synthetic-training-sales.csv")
    parser.add_argument("--heldout", type=Path, default=fixture / "synthetic-heldout-sales.csv")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    settings = MLSettings(device="cpu", zero_shot_num_samples=100)
    torch.set_num_threads(settings.torch_num_threads)
    result = evaluate(load_fixture(args.training, args.heldout), real_models(settings), VALIDATION, TEST, 8)
    pipeline = get_chronos_pipeline(settings)
    revision = getattr(pipeline.model.model.config, "_commit_hash", None)
    if not revision:
        raise RuntimeError("Cannot identify immutable Chronos model revision")
    result["execution"] = {"device": "cpu", "model": settings.chronos_repo, "model_revision": revision,
                           "versions": {name: version(name) for name in ("numpy", "pandas", "torch", "chronos-forecasting", "statsforecast", "transformers")},
                           "python": platform.python_version(),
                           "censoring": {key: value for key, value in settings.model_dump().items() if key.startswith("censoring_")},
                           "num_samples": settings.zero_shot_num_samples,
                           "context_weeks": settings.zero_shot_default_context_weeks,
                           "fixtures": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.training, args.heldout)}}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    lines = ["# Rolling-origin fashion evaluation", "", "Synthetic diagnostic only; does not establish Swecha accuracy.", "",
             f"CPU · {settings.chronos_repo} · 100 samples · seed {SEED} · Monday UTC · 8-week horizon.", "",
             "| Model | Validation WAPE % | Test WAPE % | Test bias % | Interval coverage % | Test points |", "| --- | --- | --- | --- | --- | --- |"]
    for name, report in result["models"].items():
        test = report["test"]
        lines.append(f"| {name} | {report['validation']['wape']} | {test['wape']} | {test['bias_pct']} | {test['coverage_p10_p90']} | {test['points']} |")
    lines.extend(["", "Routing was selected from validation only; test evaluated once after freezing the rule.",
                  f"Selected rule: {result['routing']['selected_rule']}. Production gate: {result['routing']['eligible_for_production']}.",
                  "", "Full per-SKU, cohort, omission, spread and fixture hashes are in results.json.",
                  "Point-only baselines have no interval coverage; ADIDA intervals are the repository's approximate Poisson intervals."])
    (args.out / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"models": {k: v['test']['wape'] for k, v in result['models'].items()}, "routing": result['routing']}, indent=2))


if __name__ == "__main__":
    main()
