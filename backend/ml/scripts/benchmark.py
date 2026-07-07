"""Benchmark every registered model on a single tenant's data.

Usage: python -m scripts.benchmark <tenant_id> <industry>
"""

from __future__ import annotations

import sys
import uuid

import pandas as pd
import structlog

from sanket_ml.data.loader import HistoricalSalesLoader
from sanket_ml.data.splits import holdout_split
from sanket_ml.registry import get as registry_get
from sanket_ml.registry import list_all
from sanket_ml.training.backtest import align_truth, evaluate

log = structlog.get_logger(__name__)


def main(tenant_id: str, industry: str, horizon: int = 26) -> int:
    loader = HistoricalSalesLoader()
    panel = loader.load(uuid.UUID(tenant_id), industry, freq="W")
    if panel.n_series == 0:
        log.error("benchmark.no_data", tenant=tenant_id)
        return 1

    df = panel.data
    train, holdout = holdout_split(df, horizon=horizon, freq="W")

    results: list[dict] = []
    for name in list_all():
        spec = registry_get(name)
        try:
            log.info("benchmark.model.start", model=name)
            model = spec.factory(horizon=horizon, freq="W")
            model.fit(train)
            fc = model.predict(horizon=horizon)
            yt, aligned = align_truth(holdout, fc)
            if len(yt) == 0:
                continue
            m = evaluate(yt, aligned, model_name=name)
            results.append(m.__dict__ if hasattr(m, "__dict__") else dict(m._asdict()))
            log.info("benchmark.model.done", model=name, wape=m.wape, coverage=m.coverage_80)
        except Exception as exc:
            log.error("benchmark.model.failed", model=name, error=str(exc))

    df_out = pd.DataFrame(results).sort_values("wape")
    print(df_out.to_string(index=False))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m scripts.benchmark <tenant_id> <industry> [horizon]")
        sys.exit(2)
    h = int(sys.argv[3]) if len(sys.argv) > 3 else 26
    raise SystemExit(main(sys.argv[1], sys.argv[2], h))
