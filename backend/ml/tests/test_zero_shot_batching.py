"""Chronos is called in bounded batches, and results keep series order."""
from __future__ import annotations

import numpy as np
import torch

from sanket_ml.config import MLSettings
from sanket_ml.inference import zero_shot


class _FakePipeline:
    def __init__(self):
        self.batch_sizes: list[int] = []

    def predict(self, ctx, prediction_length, num_samples):
        self.batch_sizes.append(len(ctx))
        # Each series forecasts its own last value, so order is checkable.
        last = torch.tensor([float(c[-1]) for c in ctx])
        return last.view(-1, 1, 1).repeat(1, num_samples, prediction_length)


def test_chronos_predict_batches_and_preserves_order(monkeypatch):
    fake = _FakePipeline()
    monkeypatch.setattr(zero_shot, "get_chronos_pipeline", lambda settings=None: fake)
    settings = MLSettings(zero_shot_batch_size=4)
    fc = zero_shot.ZeroShotForecaster(settings)
    arrays = {f"s{i}": np.array([0.0, float(i)], dtype=np.float32) for i in range(10)}

    p10, p50, p90 = fc._chronos_predict(arrays, horizon=3, num_samples=5)

    assert fake.batch_sizes == [4, 4, 2]
    assert p50.shape == (10, 3)
    assert [float(p50[i, 0]) for i in range(10)] == [float(i) for i in range(10)]


def test_default_series_cap_fits_a_multi_branch_tenant():
    assert MLSettings().zero_shot_max_series >= 30000


def test_batches_are_bounded_by_sample_paths_not_just_series(monkeypatch):
    """Chronos decodes series x num_samples sequences at once. 209 SKUs x 20 samples
    crashed the CPU service (access violation); 32 x 20 ran in 3.2 GB. The batch must
    shrink as num_samples grows so one prediction call stays within the path budget."""
    fake = _FakePipeline()
    monkeypatch.setattr(zero_shot, "get_chronos_pipeline", lambda settings=None: fake)
    settings = MLSettings(zero_shot_batch_size=256, zero_shot_max_sample_paths=40)
    fc = zero_shot.ZeroShotForecaster(settings)
    arrays = {f"s{i}": np.array([0.0, float(i)], dtype=np.float32) for i in range(10)}

    fc._chronos_predict(arrays, horizon=3, num_samples=10)

    assert fake.batch_sizes == [4, 4, 2]


def test_a_single_series_still_runs_when_samples_exceed_the_budget(monkeypatch):
    fake = _FakePipeline()
    monkeypatch.setattr(zero_shot, "get_chronos_pipeline", lambda settings=None: fake)
    settings = MLSettings(zero_shot_max_sample_paths=5)
    fc = zero_shot.ZeroShotForecaster(settings)
    arrays = {f"s{i}": np.array([0.0, float(i)], dtype=np.float32) for i in range(3)}

    fc._chronos_predict(arrays, horizon=2, num_samples=50)

    assert fake.batch_sizes == [1, 1, 1]


def test_default_path_budget_matches_the_measured_safe_load():
    assert MLSettings().zero_shot_max_sample_paths <= 640


def test_sample_tensors_are_reduced_before_accumulating_the_catalogue(monkeypatch):
    """Batching compute alone must not retain N × samples × horizon samples.

    At 25k SKUs and 500 samples the unbounded concatenate plus quantile working
    copies exceed a CPU machine's memory even though each predict call fits.
    Only per-batch quantiles may survive into the catalogue accumulation.
    """
    fake = _FakePipeline()
    predict = fake.predict

    def varying_samples(ctx, prediction_length, num_samples):
        return predict(ctx, prediction_length, num_samples) + torch.arange(num_samples).view(1, -1, 1)

    monkeypatch.setattr(fake, "predict", varying_samples)
    monkeypatch.setattr(zero_shot, "get_chronos_pipeline", lambda settings=None: fake)
    quantile = np.quantile
    shapes = []

    def bounded_quantile(values, q, axis):
        shapes.append(values.shape)
        assert values.shape[0] <= 4, "sample tensors accumulated across prediction batches"
        return quantile(values, q, axis=axis)

    monkeypatch.setattr(zero_shot.np, "quantile", bounded_quantile)
    settings = MLSettings(zero_shot_batch_size=4, zero_shot_max_sample_paths=40)
    forecaster = zero_shot.ZeroShotForecaster(settings)
    arrays = {f"s{i}": np.array([0.0, float(i)], dtype=np.float32) for i in range(10)}

    p10, p50, p90 = forecaster._chronos_predict(arrays, horizon=3, num_samples=10)

    assert shapes
    np.testing.assert_allclose(p10[:, 0], np.arange(10) + 0.9)
    np.testing.assert_allclose(p50[:, 0], np.arange(10) + 4.5)
    np.testing.assert_allclose(p90[:, 0], np.arange(10) + 8.1)
    assert p10.shape == p50.shape == p90.shape == (10, 3)
