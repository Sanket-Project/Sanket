"""ROI ledger — estimates, approvals and observed outcomes, never confused.

Every figure here is one of three things, and is labelled as such:

* **Opportunity** — open recommendations: what the forecast says is at stake
  if the planner acts. A forecast-based estimate.
* **Estimated at approval** — accepted recommendations, valued with the
  inputs frozen on them when they were approved: working capital versus the
  spreadsheet baseline, the carrying cost that implies (derived from the same
  units — never added to it), revenue at risk the order covers, and how many
  approved orders were on SKUs with an open shortage alert. An approval is a
  decision, not an outcome: none of this is money saved.
* **Observed** — outcomes that actually happened. Sanket records approvals but
  not supplier orders, goods receipts or post-order sell-through, so realised
  savings are reported as not measurable, with the reason. The one observed
  measurement it can make is forecast accuracy versus a naive baseline on
  weeks that were forecast before they happened.

Money is reported per currency and never summed across currencies or across
unlike measures (working capital, carrying cost and revenue are different
things); there is no grand total.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.calendar import week_bucket
from app.models.enums import DecisionStatus, IndustryCode
from app.models.recommendation import Recommendation
from app.models.sales import HistoricalSale
from app.services.forecast_accuracy import MAX_RESULTS, compute_accuracy

log = structlog.get_logger(__name__)

DEFAULT_WINDOW_DAYS = 90

TIERS = {
    "opportunity": "Open recommendations — forecast-based estimates of what is at stake",
    "estimated_at_approval": "Estimated when you approved — not observed savings",
    "observed": "Observed outcomes",
}


@dataclass
class RoiLine:
    """One figure on the ROI dashboard, with its tier and the evidence behind it."""

    key: str
    label: str
    value: float | None
    unit: str  # "currency" | "count" | "percent" | "units"
    basis: str
    evidence_count: int = 0
    details: list[dict] = field(default_factory=list)
    tier: str = "observed"
    #: Per-currency values for money lines; ``value`` is set only for one currency.
    values_by_currency: dict[str, float] = field(default_factory=dict)
    #: False for figures derived from another line (adding them double-counts).
    additive: bool = True

    def as_dict(self) -> dict[str, Any]:
        currencies = sorted(self.values_by_currency)
        return {
            "key": self.key,
            "label": self.label,
            "tier": self.tier,
            "value": self.value,
            "unit": self.unit,
            "currency": currencies[0] if len(currencies) == 1 else None,
            "values_by_currency": self.values_by_currency,
            "additive": self.additive,
            "basis": self.basis,
            "evidence_count": self.evidence_count,
            "details": self.details[:20],
        }


def _money_line(
    key: str,
    label: str,
    tier: str,
    per_currency: dict[str, float],
    basis: str,
    *,
    evidence: int,
    details: list[dict] | None = None,
    additive: bool = True,
) -> RoiLine:
    rounded = {c: round(v, 2) for c, v in per_currency.items()}
    if not rounded:
        value: float | None = 0.0
    elif len(rounded) == 1:
        value = next(iter(rounded.values()))
    else:
        value = None  # several currencies: no single number exists
    return RoiLine(
        key=key,
        label=label,
        tier=tier,
        value=value,
        unit="currency",
        basis=basis,
        evidence_count=evidence,
        details=details or [],
        values_by_currency=rounded,
        additive=additive,
    )


async def _recommendations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    industry: IndustryCode,
    *,
    status: DecisionStatus,
    since: datetime | None = None,
) -> list[Recommendation]:
    q = select(Recommendation).where(
        Recommendation.tenant_id == tenant_id,
        Recommendation.industry == industry,
        Recommendation.status == status,
    )
    if since is not None:
        q = q.where(Recommendation.decided_at >= since)
    return list((await session.execute(q)).scalars().all())


def _is_po(r: Recommendation) -> bool:
    return str(r.kind) == "purchase_order"


def _opportunity(open_recs: list[Recommendation]) -> list[RoiLine]:
    at_risk: dict[str, float] = defaultdict(float)
    order_value: dict[str, float] = defaultdict(float)
    pos = [r for r in open_recs if _is_po(r)]
    for r in pos:
        at_risk[r.currency] += float((r.economics or {}).get("revenue_protected") or 0)
        order_value[r.currency] += float(r.recommended_units) * float(r.unit_cost or 0)
    return [
        _money_line(
            "open_revenue_at_risk",
            "Revenue at risk on open recommendations",
            "opportunity",
            dict(at_risk),
            "Forecast demand that current stock would not cover over each open order's "
            "protection window, valued at selling price. An estimate of what is at stake.",
            evidence=len(pos),
        ),
        _money_line(
            "open_order_value",
            "Cost of open recommended orders",
            "opportunity",
            dict(order_value),
            "Recommended units x unit cost for open purchase recommendations.",
            evidence=len(pos),
        ),
    ]


def _at_approval(accepted: list[Recommendation]) -> list[RoiLine]:
    wc: dict[str, float] = defaultdict(float)
    carrying: dict[str, float] = defaultdict(float)
    covered: dict[str, float] = defaultdict(float)
    details: list[dict] = []
    pos = [r for r in accepted if _is_po(r)]
    for r in pos:
        ordered = r.accepted_units if r.accepted_units is not None else r.recommended_units
        covered[r.currency] += float((r.economics or {}).get("revenue_protected") or 0)
        delta_units = float(r.baseline_units - ordered)
        if delta_units <= 0:
            continue
        delta_value = delta_units * float(r.unit_cost or 0)
        wc[r.currency] += delta_value
        inputs = r.inputs or {}
        holding_pct = float(inputs.get("holding_cost_pct") or 0.25)
        protection_days = float(inputs.get("protection_days") or 42)
        carrying[r.currency] += delta_value * holding_pct * (protection_days / 365.0)
        details.append(
            {
                "recommendation_id": str(r.id),
                "sku_id": str(r.sku_id),
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
                "baseline_units": r.baseline_units,
                "ordered_units": ordered,
                "units_below_baseline": round(delta_units, 1),
                "unit_cost": float(r.unit_cost or 0),
                "currency": r.currency,
                "value": round(delta_value, 2),
            }
        )
    details.sort(key=lambda d: d["value"], reverse=True)
    alerted = [r for r in pos if r.linked_alert_id is not None]
    return [
        _money_line(
            "working_capital_vs_baseline",
            "Working capital below the spreadsheet baseline (estimate at approval)",
            "estimated_at_approval",
            dict(wc),
            "For approved purchase orders: (baseline units - units approved) x the unit cost "
            "frozen on the recommendation. Baseline = P90 demand over the full lead-time + "
            "review window. It becomes a saving only if the order is placed and received as "
            "approved, which Sanket does not record.",
            evidence=len(details),
            details=details,
        ),
        _money_line(
            "carrying_cost_implied",
            "Carrying cost implied by that difference (derived — not additional)",
            "estimated_at_approval",
            dict(carrying),
            "The working-capital difference x the holding-cost rate, pro-rated over each "
            "order's protection window. Derived from the line above; adding the two "
            "double-counts.",
            evidence=len(details),
            additive=False,
        ),
        _money_line(
            "revenue_at_risk_covered",
            "Revenue at risk covered by approved orders (estimate)",
            "estimated_at_approval",
            dict(covered),
            "Forecast demand stock on hand would not have covered, valued at selling price, "
            "for each approved order. Revenue, not profit, and not observed sales.",
            evidence=len(pos),
        ),
        RoiLine(
            key="approved_orders_on_alerted_skus",
            label="Approved orders on SKUs with an open shortage alert",
            tier="estimated_at_approval",
            value=float(len(alerted)),
            unit="count",
            basis=(
                "Approved purchase orders whose SKU had an open or acknowledged shortage alert "
                "when the recommendation was generated. A count of approvals, not of stockouts "
                "avoided: whether a stockout was avoided is not observed."
            ),
            evidence_count=len(alerted),
            details=[
                {
                    "recommendation_id": str(r.id),
                    "sku_id": str(r.sku_id),
                    "alert_id": str(r.linked_alert_id),
                }
                for r in alerted
            ],
        ),
    ]


def _realized() -> RoiLine:
    return RoiLine(
        key="realized_savings",
        label="Realised savings",
        tier="observed",
        value=None,
        unit="currency",
        basis=(
            "Not measurable yet. Sanket records approvals, but no supplier order, goods receipt "
            "or post-order sell-through, so no saving or avoided stockout has been observed. "
            "Measuring it needs those records, compared against the baseline for the same weeks."
        ),
    )


async def _forecast_improvement(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    industry: IndustryCode,
    since: datetime,
) -> RoiLine:
    """Model WAPE versus a naive random-walk baseline on the same weeks.

    Only genuinely out-of-sample points count, on the same rules as production
    accuracy: Monday-UTC calendar runs, completed before the week began, whose
    training history ended no later than that week.
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

    # Use exactly the date-matched production points shown on the accuracy
    # page. Averaging historical runs would invent a forecast nobody used.
    accuracy = await compute_accuracy(
        session, tenant_id=tenant_id, industry=industry.value, limit=MAX_RESULTS,
    )
    fc_rows = [
        (uuid.UUID(row["sku_id"]), date.fromisoformat(week["week"]), week["p50"], week["actual"])
        for row in accuracy["rows"]
        for week in row["weeks"]
        if date.fromisoformat(week["week"]) >= since.date()
    ]

    if not fc_rows:
        empty.basis += " No out-of-sample forecast weeks have matured yet."
        return empty

    sku_ids = {row[0] for row in fc_rows}
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

    abs_err_model = 0.0
    abs_err_naive = 0.0
    total_actual = 0.0
    matched = 0

    for sku_id, wk, prediction, actual in fc_rows:
        # The scored week proves the feed reaches this period, so a preceding
        # week with no sale is a real zero, as in the accuracy service.
        prev = actuals.get((sku_id, wk - timedelta(weeks=1)), 0.0)
        matched += 1
        abs_err_model += abs(float(prediction) - actual)
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
    """Assemble the ROI dashboard payload: three tiers, no grand total."""
    ind = IndustryCode(industry)
    since = datetime.now(UTC) - timedelta(days=window_days)

    open_recs = await _recommendations(session, tenant_id, ind, status=DecisionStatus.open)
    accepted = await _recommendations(
        session, tenant_id, ind, status=DecisionStatus.accepted, since=since
    )
    improvement = await _forecast_improvement(session, tenant_id, ind, since)

    by_tier = {
        "opportunity": _opportunity(open_recs),
        "estimated_at_approval": _at_approval(accepted),
        "observed": [_realized(), improvement],
    }
    lines = [line for tier_lines in by_tier.values() for line in tier_lines]
    currencies = sorted({c for line in lines for c in line.values_by_currency})
    observed_status = "measured" if improvement.value is not None else "not_measurable"

    return {
        "industry": industry,
        "window_days": window_days,
        "currency": currencies[0] if len(currencies) == 1 else None,
        "currencies": currencies,
        "tiers": {
            key: {
                "label": TIERS[key],
                "status": observed_status if key == "observed" else "estimate",
                "lines": [line.as_dict() for line in tier_lines],
            }
            for key, tier_lines in by_tier.items()
        },
        "lines": [line.as_dict() for line in lines],
        "adoption": {
            "recommendations_accepted": len(accepted),
            "recommendations_open": len(open_recs),
        },
        "caveat": (
            "Estimates use the inputs frozen on each recommendation. Approving a recommendation "
            "is a decision, not an outcome: none of these figures is money saved until orders, "
            "receipts and sales confirm it."
        ),
    }
