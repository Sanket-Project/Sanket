"""Forecast accuracy router — joins forecast results with actuals to compute MAPE/WAPE."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import func, select, text

from app.models.enums import IndustryCode
from app.routers.industry_router import ActiveIndustry, TenantId

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/forecast", tags=["forecast-accuracy"])


@router.get("/accuracy")
async def forecast_accuracy(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Join forecast_results with historical_sales to compute per-SKU, per-model MAPE and WAPE.
    Falls back to cached forecast_accuracy_metrics table when available.
    """
    from app.models.forecast import ForecastResult, ForecastRun
    from app.models.sales import HistoricalSale

    db = request.app.state.db
    industry = IndustryCode(ctx.code)

    async with db.session(str(tenant_id)) as session:
        # Try reading from pre-computed cache first. This runs inside a
        # SAVEPOINT (begin_nested) because forecast_accuracy_metrics isn't
        # created by any migration yet — the raw SQL below is expected to
        # fail on most installs. Without the savepoint, that failure would
        # poison the whole session's transaction (Postgres refuses further
        # commands until a rollback), which made every request to this
        # endpoint 500 with a generic "An unexpected error occurred" even
        # though the fallback path below was perfectly capable of running.
        try:
            async with session.begin_nested():
                cache_result = await session.execute(
                    text("""
                        SELECT sku_id::text, model_name, mape, wape, n_obs, computed_at
                        FROM forecast_accuracy_metrics
                        WHERE tenant_id = :tid
                        ORDER BY computed_at DESC
                        LIMIT :lim
                    """),
                    {"tid": str(tenant_id), "lim": limit},
                )
                cached = cache_result.fetchall()
            if cached:
                return {
                    "industry": ctx.code,
                    "source": "cached",
                    "rows": [
                        {
                            "sku_id": r.sku_id,
                            "model_name": r.model_name,
                            "mape": float(r.mape) if r.mape is not None else None,
                            "wape": float(r.wape) if r.wape is not None else None,
                            "n_obs": r.n_obs,
                            "computed_at": str(r.computed_at),
                        }
                        for r in cached
                    ],
                }
        except Exception:
            pass  # Table may not exist yet; fall through to live computation

        # Live computation: most recent completed run
        run = await session.scalar(
            select(ForecastRun)
            .where(
                ForecastRun.tenant_id == tenant_id,
                ForecastRun.industry == industry,
                ForecastRun.status == "completed",
            )
            .order_by(ForecastRun.completed_at.desc())
            .limit(1)
        )
        if run is None:
            return {"industry": ctx.code, "source": "live", "rows": []}

        fc_rows = await session.execute(
            select(ForecastResult)
            .where(
                ForecastResult.run_id == run.id,
                ForecastResult.tenant_id == tenant_id,
            )
            .limit(5000)
        )
        forecasts = fc_rows.scalars().all()

        if not forecasts:
            return {"industry": ctx.code, "source": "live", "rows": []}

        # Gather actuals for the same SKUs and date range
        sku_ids = list({f.sku_id for f in forecasts})
        min_date = min(f.forecast_date for f in forecasts)
        max_date = max(f.forecast_date for f in forecasts)

        _week = func.date_trunc(text("'week'"), HistoricalSale.sale_time)
        actuals_rows = await session.execute(
            select(
                HistoricalSale.sku_id,
                _week.label("week"),
                func.sum(HistoricalSale.units_sold).label("units"),
            )
            .where(
                HistoricalSale.tenant_id == tenant_id,
                HistoricalSale.sku_id.in_(sku_ids),
                HistoricalSale.sale_time >= min_date,
                HistoricalSale.sale_time <= max_date,
            )
            .group_by(HistoricalSale.sku_id, _week)
        )
        actuals_data = actuals_rows.fetchall()

    # Build actuals lookup {sku_id: {week_str: units}}
    actuals: dict[str, dict[str, float]] = {}
    for row in actuals_data:
        sid = str(row.sku_id)
        wk = str(row.week)[:10]
        actuals.setdefault(sid, {})[wk] = float(row.units)

    # Compute MAPE / WAPE per (sku_id, model_name)
    from collections import defaultdict

    errors: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for fc in forecasts:
        sid = str(fc.sku_id)
        wk = str(fc.forecast_date)[:10]
        actual = actuals.get(sid, {}).get(wk)
        if actual is None:
            continue
        p50 = float(fc.p50)
        err = abs(actual - p50)
        errors[(sid, fc.model_name)].append((err, actual))

    rows: list[dict] = []
    for (sku_id, model_name), pairs in errors.items():
        actuals_vals = [a for _, a in pairs]
        abs_errs = [e for e, _ in pairs]
        n = len(pairs)
        sum_actual = sum(actuals_vals)
        mape = sum(e / max(a, 0.01) for e, a in pairs) / n * 100 if n > 0 else None
        wape = sum(abs_errs) / max(sum_actual, 0.01) * 100 if sum_actual > 0 else None
        rows.append(
            {
                "sku_id": sku_id,
                "model_name": model_name,
                "mape": round(mape, 2) if mape is not None else None,
                "wape": round(wape, 2) if wape is not None else None,
                "n_obs": n,
                "computed_at": None,
            }
        )

    rows.sort(key=lambda x: x["mape"] or 999)
    return {"industry": ctx.code, "source": "live", "rows": rows[:limit]}
