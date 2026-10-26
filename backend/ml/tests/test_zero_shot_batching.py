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
