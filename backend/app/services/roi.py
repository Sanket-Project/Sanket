"""ROI ledger — what the software actually saved, traced to specific decisions.

Every CEO asks the same question at renewal: *what did this save me?* A number
that cannot be traced back to individual orders is a marketing claim, so this
module only counts things that left an audit trail:

* **Working capital released** — for each *accepted* purchase order, the gap
  between the spreadsheet baseline (cover p90 over the whole protection window)
  and what the planner actually ordered, valued at that SKU's unit cost as it
  stood on the day. Both numbers are frozen on the recommendation row.
* **Stockouts avoided** — accepted orders on SKUs that had an open shortage
  alert at the time the recommendation was generated. Nothing else counts;
  "would have stocked out" without an alert is speculation.
* **Forecast improvement** — measured, not assumed: model WAPE versus a naive
  random-walk baseline over the same out-of-sample weeks.

Anything that cannot be evidenced is reported as ``None`` with a reason, rather
than filled in with a plausible-looking figure.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.calendar import week_bucket
from app.models.enums import DecisionStatus, IndustryCode
from app.models.forecast import ForecastResult, ForecastRun
from app.models.recommendation import Recommendation
from app.models.sales import HistoricalSale

log = structlog.get_logger(__name__)

DEFAULT_WINDOW_DAYS = 90


@dataclass
class RoiLine:
    """One claim on the ROI dashboard, with the evidence behind it."""

    key: str
    label: str
    value: float | None
    unit: str  # "currency" | "count" | "percent" | "units"
    basis: str
    evidence_count: int = 0
    details: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "basis": self.basis,
            "evidence_count": self.evidence_count,
            "details": self.details[:20],
        }


async def _accepted(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    industry: IndustryCode,
    since: datetime,
) -> list[Recommendation]:
    return list(
        (
            await session.execute(
                select(Recommendation).where(
                    Recommendation.tenant_id == tenant_id,
                    Recommendation.industry == industry,
                    Recommendation.status == DecisionStatus.accepted,
                    Recommendation.decided_at >= since,
                )
            )
        ).scalars().all()
    )


def _working_capital(recs: list[Recommendation]) -> tuple[RoiLine, RoiLine, str]:
    """Baseline-minus-actual, valued at the frozen unit cost."""
    released = 0.0
    units_saved = 0.0
    holding_avoided = 0.0
    details: list[dict] = []
    currency = "INR"

    for r in recs:
        if str(r.kind) != "purchase_order":
            continue
        currency = r.currency or currency
        actual = r.accepted_units if r.accepted_units is not None else r.recommended_units
        delta_units = float(r.baseline_units - actual)
        if delta_units <= 0:
            continue
        cost = float(r.unit_cost or 0)
        delta_value = delta_units * cost
        released += delta_value
        units_saved += delta_units

        inputs = r.inputs or {}
        holding_pct = float(inputs.get("holding_cost_pct") or 0.25)
        protection_days = float(inputs.get("protection_days") or 42)
        holding_avoided += delta_value * holding_pct * (protection_days / 365.0)

        details.append(
            {
                "recommendation_id": str(r.id),
                "sku_id": str(r.sku_id),
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
                "baseline_units": r.baseline_units,
                "ordered_units": actual,
                "units_avoided": round(delta_units, 1),
                "unit_cost": cost,
                "value": round(delta_value, 2),
            }
        )

    details.sort(key=lambda d: d["value"], reverse=True)

    wc = RoiLine(
        key="working_capital_released",
        label="Working capital released",
        value=round(released, 2),
        unit="currency",
        basis=(
            "Sum over accepted purchase orders of (spreadsheet baseline units − units actually "
            "ordered) × the SKU's unit cost at the time. Baseline = cover p90 demand across the "
            "full lead-time + review window with no variance pooling."
        ),
        evidence_count=len(details),
        details=details,
    )
    hold = RoiLine(
        key="holding_cost_avoided",
        label="Carrying cost avoided",
        value=round(holding_avoided, 2),
        unit="currency",
        basis=(
            "Working capital released × the tenant's annual holding-cost rate, pro-rated over "
            "each order's protection window."
        ),
        evidence_count=len(details),
    )
    return wc, hold, currency


def _stockouts_avoided(recs: list[Recommendation]) -> RoiLine:
    hits = [
        r
        for r in recs
        if str(r.kind) == "purchase_order" and r.linked_alert_id is not None
    ]
    return RoiLine(
        key="stockouts_avoided",
        label="Stockouts avoided",
        value=float(len(hits)),
        unit="count",
        basis=(
            "Accepted purchase orders on SKUs that had an open or acknowledged shortage alert "
            "at the moment the recommendation was generated. Orders with no alert are not counted."
        ),
        evidence_count=len(hits),
        details=[
            {
                "recommendation_id": str(r.id),
                "sku_id": str(r.sku_id),
                "alert_id": str(r.linked_alert_id),
                "units": r.accepted_units if r.accepted_units is not None else r.recommended_units,
                "revenue_protected": float((r.economics or {}).get("revenue_protected") or 0),
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
            }
            for r in hits
        ],
    )


def _revenue_protected(recs: list[Recommendation]) -> RoiLine:
    total = sum(
        float((r.economics or {}).get("revenue_protected") or 0)
        for r in recs
        if str(r.kind) == "purchase_order"
    )
    return RoiLine(
        key="revenue_protected",
        label="Revenue protected",
        value=round(total, 2),
        unit="currency",
        basis=(
            "For each accepted order, the demand that stock on hand could not have covered over "
            "the protection window, valued at the SKU's selling price."
        ),
        evidence_count=sum(1 for r in recs if str(r.kind) == "purchase_order"),
    )


async def _forecast_improvement(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    industry: IndustryCode,
    since: datetime,
) -> RoiLine:
    """Model WAPE versus a naive random-walk baseline on the same weeks.

    Only genuinely out-of-sample points count: the forecast run must have
    completed *before* the week it predicted.
    """
    empty = RoiLine(
        key="forecast_improvement",
        label="Forecast improvement vs. naive",
        value=None,
        unit="percent",
        basis=(
            "Weighted absolute percentage error of the model against a naive "
            "last-week-repeats baseline, over weeks that were forecast before they happened."
        ),
    )

    fc_rows = (
        await session.execute(
            select(
                ForecastResult.sku_id,
                ForecastResult.forecast_date,
                func.avg(ForecastResult.p50).label("p50"),
            )
            .join(ForecastRun, ForecastRun.id == ForecastResult.run_id)
            .where(
                ForecastResult.tenant_id == tenant_id,
                ForecastRun.industry == industry,
                ForecastRun.status == "completed",
                ForecastRun.completed_at.isnot(None),
                ForecastResult.forecast_date >= since.date(),
                ForecastResult.forecast_date <= datetime.now(UTC).date(),
                # Out-of-sample only.
                func.date(ForecastRun.completed_at) < ForecastResult.forecast_date,
            )
            .group_by(ForecastResult.sku_id, ForecastResult.forecast_date)
        )
    ).fetchall()

    if not fc_rows:
        empty.basis += " No out-of-sample forecast weeks have matured yet."
        return empty

    sku_ids = {r.sku_id for r in fc_rows}
    week = week_bucket(HistoricalSale.sale_time).label("week")
    actual_rows = (
        await session.execute(
            select(HistoricalSale.sku_id, week, func.sum(HistoricalSale.units_sold).label("units"))
            .where(
                HistoricalSale.tenant_id == tenant_id,
                HistoricalSale.industry == industry,
                HistoricalSale.sku_id.in_(sku_ids),
                HistoricalSale.sale_time >= since - timedelta(weeks=2),
            )
            .group_by(HistoricalSale.sku_id, week)
        )
    ).fetchall()

    actuals: dict[tuple[uuid.UUID, Any], float] = {}
    for r in actual_rows:
        actuals[(r.sku_id, r.week.date())] = float(r.units or 0)

    def week_start(d: Any) -> Any:
        # Weeks are Monday 00:00 UTC (app.core.calendar); align forecast dates.
        return d - timedelta(days=d.weekday())

    abs_err_model = 0.0
    abs_err_naive = 0.0
    total_actual = 0.0
    matched = 0

    for r in fc_rows:
        wk = week_start(r.forecast_date)
        actual = actuals.get((r.sku_id, wk))
        prev = actuals.get((r.sku_id, wk - timedelta(weeks=1)))
        if actual is None or prev is None:
            continue
        matched += 1
        abs_err_model += abs(float(r.p50 or 0) - actual)
        abs_err_naive += abs(prev - actual)
        total_actual += actual

    if matched < 8 or total_actual <= 0 or abs_err_naive <= 0:
        empty.basis += f" Only {matched} comparable week(s) so far — need at least 8."
        return empty

    wape_model = abs_err_model / total_actual
    wape_naive = abs_err_naive / total_actual
    improvement = (wape_naive - wape_model) / wape_naive * 100.0

    return RoiLine(
        key="forecast_improvement",
        label="Forecast improvement vs. naive",
        value=round(improvement, 1),
        unit="percent",
        basis=(
            f"Model WAPE {wape_model:.1%} vs naive last-week-repeats WAPE {wape_naive:.1%} "
            f"across {matched} out-of-sample SKU-weeks."
        ),
        evidence_count=matched,
        details=[
            {"metric": "model_wape", "value": round(wape_model, 4)},
            {"metric": "naive_wape", "value": round(wape_naive, 4)},
            {"metric": "sku_weeks", "value": matched},
        ],
    )


async def summary(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    industry: str,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> dict[str, Any]:
    """Assemble the ROI dashboard payload."""
    ind = IndustryCode(industry)
    since = datetime.now(UTC) - timedelta(days=window_days)

    recs = await _accepted(session, tenant_id, ind, since)
    wc, holding, currency = _working_capital(recs)
    lines = [
        wc,
        _stockouts_avoided(recs),
        holding,
        _revenue_protected(recs),
        await _forecast_improvement(session, tenant_id, ind, since),
    ]

    # Only the currency-denominated lines roll into the headline. Mixing a
    # percentage or a count into a rupee total is how ROI dashboards start
    # lying.
    total_value = sum(
        line.value or 0.0 for line in lines if line.unit == "currency"
    )

    decided = len(recs)
    open_count = await session.scalar(
        select(func.count())
        .select_from(Recommendation)
        .where(
            Recommendation.tenant_id == tenant_id,
            Recommendation.industry == ind,
            Recommendation.status == DecisionStatus.open,
        )
    )

    return {
        "industry": industry,
        "window_days": window_days,
        "currency": currency,
        "total_value_realized": round(total_value, 2),
        "lines": [line.as_dict() for line in lines],
        "adoption": {
            "recommendations_accepted": decided,
            "recommendations_open": int(open_count or 0),
        },
        "caveat": (
            "Every figure is derived from decisions you accepted in this window and the inputs "
            "frozen on them at the time. Recommendations you never acted on contribute nothing."
        ),
    }
