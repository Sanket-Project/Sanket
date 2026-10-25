"""Forecast accuracy, date-matched and free of hindsight.

A forecast for the week starting Monday *W* is compared with the units sold in
``[W, W + 7 days)`` (UTC). Two populations are scored and never mixed:

* **Production** — what a planner actually had in hand: for each SKU-week the
  most recent forecast that was completed before the week began and whose
  training data ended no later than that Monday.
* **Backtest** — runs explicitly made from a past cutoff
  (``POST /forecasts/backtest``). Leakage-free by construction (the model saw
  only history before the cutoff), but made after the fact, so labelled apart.

Everything that is not scored is counted with its reason, so an empty result
says why rather than looking like "no accuracy problems".
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.calendar import CALENDAR, WEEK, week_bucket, week_start_instant
from app.models.enums import IndustryCode
from app.models.forecast import ForecastResult, ForecastRun
from app.models.product import Sku
from app.models.sales import HistoricalSale

MAX_RUNS = 60
MAX_RESULTS = 50_000
MAX_BACKTESTS = 5

EXCLUSION_REASONS = (
    "legacy_calendar",              # run predates the Monday-UTC calendar; dates unreliable
    "period_not_complete",          # the week has not finished yet
    "trained_on_period",            # the model's history included the week it predicts
    "generated_after_period_start", # made after the week began: not a real forecast
    "awaiting_actuals",             # the sales feed has not reached the end of the week
)


@dataclass(frozen=True, slots=True)
class _Run:
    id: uuid.UUID
    completed_at: datetime
    mode: str
    calendar: str | None
    history_end: date | None


@dataclass(frozen=True, slots=True)
class _Point:
    run: _Run
    sku_id: uuid.UUID
    model_name: str
    week: date
    p10: float
    p50: float
    p90: float


def _parse_run(run_id: uuid.UUID, completed_at: datetime, metrics: dict | None) -> _Run:
    m = metrics if isinstance(metrics, dict) else {}
    raw_end = m.get("history_end")
    try:
        history_end = date.fromisoformat(raw_end) if raw_end else None
    except (TypeError, ValueError):
        history_end = None
    ts = completed_at if completed_at.tzinfo else completed_at.replace(tzinfo=UTC)
    return _Run(
        id=run_id,
        completed_at=ts,
        mode=str(m.get("mode") or ""),
        calendar=m.get("calendar"),
        history_end=history_end,
    )


def _score(pairs: list[tuple[_Point, float]]) -> dict[str, Any]:
    n = len(pairs)
    total = sum(a for _, a in pairs)
    abs_err = sum(abs(p.p50 - a) for p, a in pairs)
    signed = sum(p.p50 - a for p, a in pairs)
    positive = [(p, a) for p, a in pairs if a > 0]
    covered = sum(1 for p, a in pairs if p.p10 <= a <= p.p90)
    return {
        "n_obs": n,
        # Undefined (not 0%, not infinite) when nothing was sold in the window.
        "wape": round(abs_err / total * 100, 2) if total > 0 else None,
        "bias_pct": round(signed / total * 100, 2) if total > 0 else None,
        "mape": (
            round(sum(abs(p.p50 - a) / a for p, a in positive) / len(positive) * 100, 2)
            if positive
            else None
        ),
        "coverage_p10_p90": round(covered / n * 100, 2) if n else None,
    }


async def compute_accuracy(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    industry: str,
    now: datetime | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    ind = IndustryCode(industry)

    run_rows = (
        await session.execute(
            select(ForecastRun.id, ForecastRun.completed_at, ForecastRun.metrics)
            .where(
                ForecastRun.tenant_id == tenant_id,
                ForecastRun.industry == ind,
                ForecastRun.status == "completed",
                ForecastRun.completed_at.isnot(None),
            )
            .order_by(ForecastRun.completed_at.desc())
            .limit(MAX_RUNS)
        )
    ).all()
    runs = {r.id: _parse_run(r.id, r.completed_at, r.metrics) for r in run_rows}
    excluded: Counter[str] = Counter(dict.fromkeys(EXCLUSION_REASONS, 0))

    production: dict[tuple[uuid.UUID, date, str], _Point] = {}
    backtests: dict[uuid.UUID, list[_Point]] = defaultdict(list)
    if runs:
        results = (
            await session.execute(
                select(
                    ForecastResult.run_id,
                    ForecastResult.sku_id,
                    ForecastResult.forecast_date,
                    ForecastResult.p10,
                    ForecastResult.p50,
                    ForecastResult.p90,
                    ForecastResult.model_name,
                )
                .where(
                    ForecastResult.tenant_id == tenant_id,
                    ForecastResult.run_id.in_(list(runs)),
                )
                .limit(MAX_RESULTS)
            )
        ).all()
        for r in results:
            run = runs[r.run_id]
            week = r.forecast_date
            if run.calendar != CALENDAR or run.history_end is None or week.weekday() != 0:
                excluded["legacy_calendar"] += 1
                continue
            starts = week_start_instant(week)
            if now < starts + WEEK:
                excluded["period_not_complete"] += 1
                continue
            if run.history_end > week:
                excluded["trained_on_period"] += 1
                continue
            point = _Point(run, r.sku_id, r.model_name, week,
                           float(r.p10), float(r.p50), float(r.p90))
            if run.mode == "backtest":
                backtests[run.id].append(point)
                continue
            if run.completed_at > starts:
                excluded["generated_after_period_start"] += 1
                continue
            key = (r.sku_id, week, r.model_name)
            current = production.get(key)
            if current is None or run.completed_at > current.run.completed_at:
                production[key] = point

    kept_backtests = sorted(
        backtests, key=lambda rid: runs[rid].completed_at, reverse=True
    )[:MAX_BACKTESTS]
    all_points = list(production.values()) + [p for rid in kept_backtests for p in backtests[rid]]
    actuals, feed_end = await _actuals(session, tenant_id, ind, all_points)

    def resolve(points: list[_Point], count_missing: bool) -> list[tuple[_Point, float]]:
        out: list[tuple[_Point, float]] = []
        for p in points:
            actual = actuals.get((p.sku_id, p.week))
            if actual is None:
                week_end = week_start_instant(p.week) + WEEK
                if feed_end is None or feed_end < week_end:
                    if count_missing:
                        excluded["awaiting_actuals"] += 1
                    continue
                actual = 0.0  # the feed covers the week and recorded no sale
            out.append((p, actual))
        return out

    scored = resolve(list(production.values()), count_missing=True)
    codes = await _sku_codes(session, tenant_id, {p.sku_id for p in all_points})

    by_sku_model: dict[tuple[uuid.UUID, str], list[tuple[_Point, float]]] = defaultdict(list)
    for p, a in scored:
        by_sku_model[(p.sku_id, p.model_name)].append((p, a))
    rows = [
        {
            "sku_id": str(sku_id),
            "sku_code": codes.get(sku_id),
            "model_name": model,
            **_score(pairs),
            "computed_at": None,
            "weeks": [
                {
                    "week": p.week.isoformat(),
                    "actual": a,
                    "p10": p.p10,
                    "p50": p.p50,
                    "p90": p.p90,
                    "run_id": str(p.run.id),
                    "lead_weeks": (p.week - p.run.history_end).days // 7,
                }
                for p, a in sorted(pairs, key=lambda x: x[0].week)
            ],
        }
        for (sku_id, model), pairs in by_sku_model.items()
    ]
    rows.sort(key=lambda r: (r["wape"] is None, r["wape"] or 0.0))

    backtest_runs = []
    for rid in kept_backtests:
        pairs = resolve(backtests[rid], count_missing=False)
        run = runs[rid]
        backtest_runs.append(
            {
                "run_id": str(rid),
                "cutoff": run.history_end.isoformat() if run.history_end else None,
                "completed_at": run.completed_at.isoformat(),
                "points": len(pairs),
                "skus": len({p.sku_id for p, _ in pairs}),
                **{k: v for k, v in _score(pairs).items() if k != "n_obs"},
            }
        )

    summary = _score(scored)
    return {
        "industry": industry,
        "source": "live",
        "calendar": CALENDAR,
        "basis": (
            "Each forecast week (Monday 00:00 UTC) is compared with the units sold that week. "
            "Production accuracy uses, for every SKU-week, the latest forecast completed before "
            "the week began from history that ended before it."
        ),
        "rows": rows[:limit],
        "summary": {
            "points": summary["n_obs"],
            "skus": len({p.sku_id for p, _ in scored}),
            "wape": summary["wape"],
            "bias_pct": summary["bias_pct"],
            "coverage_p10_p90": summary["coverage_p10_p90"],
        },
        "excluded": dict(excluded),
        "backtest": {
            "note": (
                "Backtests forecast from a past cutoff using only earlier history. They are "
                "leakage-free but were made after the fact, so they are not production accuracy."
            ),
            "runs": backtest_runs,
        },
    }


async def _actuals(
    session: AsyncSession, tenant_id: uuid.UUID, industry: IndustryCode, points: list[_Point]
) -> tuple[dict[tuple[uuid.UUID, date], float], datetime | None]:
    feed_end = await session.scalar(
        select(func.max(HistoricalSale.sale_time)).where(
            HistoricalSale.tenant_id == tenant_id, HistoricalSale.industry == industry
        )
    )
    if feed_end is not None and feed_end.tzinfo is None:
        feed_end = feed_end.replace(tzinfo=UTC)
    if not points:
        return {}, feed_end
    first = min(p.week for p in points)
    last = max(p.week for p in points)
    bucket = week_bucket(HistoricalSale.sale_time).label("week")
    rows = (
        await session.execute(
            select(HistoricalSale.sku_id, bucket, func.sum(HistoricalSale.units_sold).label("units"))
            .where(
                HistoricalSale.tenant_id == tenant_id,
                HistoricalSale.industry == industry,
                HistoricalSale.sku_id.in_({p.sku_id for p in points}),
                HistoricalSale.sale_time >= week_start_instant(first),
                HistoricalSale.sale_time < week_start_instant(last) + WEEK,
            )
            .group_by(HistoricalSale.sku_id, bucket)
        )
    ).all()
    return {(r.sku_id, r.week.date()): float(r.units or 0) for r in rows}, feed_end


async def _sku_codes(
    session: AsyncSession, tenant_id: uuid.UUID, ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = await session.execute(
        select(Sku.id, Sku.sku_code).where(Sku.tenant_id == tenant_id, Sku.id.in_(ids))
    )
    return dict(rows.all())
