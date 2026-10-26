import numpy as np
import pandas as pd
import pytest

from benchmarks.rolling_origin import Fold, Model, evaluate, folds, load_fixture, score


def panel(weeks=24):
    return pd.DataFrame({"unique_id": "A", "ds": pd.date_range("2026-01-05", periods=weeks, freq="W-MON"), "y": 10.0})


def constant(value):
    def predict(train, horizon):
        pieces = []
        for uid, group in train.groupby("unique_id"):
            pieces.append(pd.DataFrame({"unique_id": uid, "ds": pd.date_range(group.ds.max() + pd.Timedelta(weeks=1), periods=horizon, freq="W-MON"), "p50": value}))
        return pd.concat(pieces, ignore_index=True)
    return Model(predict)


def test_fold_rejects_leakage_and_non_monday():
    p = panel()
    with pytest.raises(AssertionError, match="leakage"):
        Fold(pd.Timestamp("2026-03-02"), p.iloc[:10], p.iloc[8:10], {})
    with pytest.raises(ValueError, match="Monday"):
        folds(p, ["2026-03-03"], 2)
    fold = folds(p, ["2026-03-02"], 2)[0]
    assert fold.train.ds.max() < fold.cutoff == fold.test.ds.min()
    assert (fold.test.ds.dt.dayofweek == 0).all()


def test_fixture_aggregates_and_preserves_missing_weeks_as_zeros(tmp_path):
    a, b = tmp_path / "train.csv", tmp_path / "test.csv"
    a.write_text("sku,date,quantity\nA,2026-01-05,3\nA,2026-01-06,2\n")
    b.write_text("sku,date,quantity\nA,2026-01-19,4\n")
    result = load_fixture(a, b)
    assert result.y.tolist() == [5, 0, 4]
    assert result.ds.dt.dayofweek.tolist() == [0, 0, 0]


def test_hand_computed_metrics_and_zero_denominator():
    result = score(pd.DataFrame({"y": [10, 30], "p50": [12, 24], "p10": [9, 20], "p90": [15, 28]}))
    assert result["wape"] == 20
    assert result["bias_pct"] == -10
    assert result["coverage_p10_p90"] == 50
    assert result["points"] == 2
    assert score(pd.DataFrame({"y": [0], "p50": [2]}))["wape"] is None


def test_omitted_coverage_counts_short_series():
    p = panel()
    short = p.iloc[7:].assign(unique_id="NEW")
    f = folds(pd.concat([p, short]), ["2026-03-02"], 2)[0]
    assert f.omitted == {"NEW": "insufficient_history"}
    assert f.train.unique_id.unique().tolist() == ["A"]


def test_routing_cannot_select_a_test_only_winner():
    p = panel()
    p.loc[p.ds >= "2026-05-25", "y"] = 30
    result = evaluate(p, {"chronos": constant(10), "test_only_winner": constant(30)}, ["2026-03-02", "2026-04-06"], "2026-05-25", 2)
    assert result["routing"]["per_sku"]["A"] == "chronos"
    assert result["routing"]["test"]["wape"] > 0
    assert not result["routing"]["eligible_for_production"]


def test_validation_cannot_overlap_test_and_predictions_must_match_dates():
    with pytest.raises(ValueError, match="overlap"):
        evaluate(panel(), {"chronos": constant(10)}, ["2026-05-18"], "2026-05-25", 2)
    bad = Model(lambda train, horizon: constant(10).predict(train, horizon).assign(ds=pd.Timestamp("2026-01-05")))
    with pytest.raises(ValueError, match="forecast dates"):
        evaluate(panel(), {"chronos": bad}, ["2026-03-02"], "2026-05-25", 2)


def test_nonfinite_predictions_are_rejected():
    with pytest.raises(ValueError, match="finite"):
        evaluate(panel(), {"chronos": constant(np.nan)}, ["2026-03-02"], "2026-05-25", 2)


def test_routing_scores_new_test_skus_on_the_same_denominator():
    p = panel().assign(y=22.)
    p.loc[p.ds >= "2026-05-25", "y"] = 15
    new = p[p.ds >= "2026-03-30"].assign(unique_id="NEW", y=100.)
    result = evaluate(pd.concat([p, new]), {"chronos": constant(10), "candidate": constant(22)},
                      ["2026-03-02", "2026-04-06"], "2026-05-25", 2)
    assert result["routing"]["test"]["points"] == 4
    assert not result["routing"]["eligible_for_production"]
    assert "new_since_validation" in result["models"]["chronos"]["test"]["per_cohort"]


def test_chronos_preprocesses_training_only_like_production(monkeypatch):
    from types import SimpleNamespace
    from benchmarks.rolling_origin import chronos_training
    from sanket_ml.config import MLSettings
    import sanket_ml.data.censoring as censoring
    seen = []
    def correct(data, **kwargs):
        seen.append((data.copy(), kwargs))
        return SimpleNamespace(data=data.assign(y=99))
    monkeypatch.setattr(censoring, "correct_censored_demand", correct)
    train = panel().iloc[:8]
    assert chronos_training(train, MLSettings()).y.eq(99).all()
    assert seen[0][0].ds.max() == train.ds.max()
    assert seen[0][1]["min_history"] == 12
    assert chronos_training(train, MLSettings(censoring_enabled=False)).equals(train)


def test_incomplete_test_horizon_and_nonfinite_actuals_fail_closed():
    with pytest.raises(ValueError, match="complete horizon"):
        evaluate(panel(22), {"chronos": constant(10)}, ["2026-03-02"], "2026-06-01", 2)
    with pytest.raises(ValueError, match="finite"):
        folds(panel().assign(y=np.nan), ["2026-03-02"], 2)
