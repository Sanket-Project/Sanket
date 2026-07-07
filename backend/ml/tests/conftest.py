import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def synthetic_panel() -> pd.DataFrame:
    """A 3-series weekly panel with seasonal demand + noise."""
    rng = np.random.default_rng(42)
    weeks = pd.date_range("2024-01-01", periods=104, freq="W")
    pieces = []
    for i, sku in enumerate(["SKU-A", "SKU-B", "SKU-C"]):
        base = 100 + i * 50
        seasonal = 30 * np.sin(2 * np.pi * np.arange(104) / 52)
        noise = rng.normal(0, 8, size=104)
        y = np.clip(base + seasonal + noise, 0, None)
        pieces.append(pd.DataFrame({"unique_id": sku, "ds": weeks, "y": y}))
    return pd.concat(pieces, ignore_index=True)
