"""One-week onboarding — the promise, made measurable.

"Connect your data, get insights in 7 days" is only a real claim if the product
can tell a customer, on day 3, exactly where they are and what is blocking them.
The wizard tracks which screens someone clicked through; this module checks the
things that actually gate value, against real rows:

* is there history, and is it long enough to fit a model?
* do the SKUs carry the cost / price / lead time the decision engine needs?
* is there stock data, or are order quantities being computed off an estimate?
* is the data clean enough to forecast on?
* has a forecast actually run, and did it produce recommendations?

Each milestone is placed on a day of the seven-day plan, and the next blocking
one is surfaced as *the* next action. Nothing is marked done because a button
was pressed — only because the data is there.
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
from app.models.forecast import ForecastRun
from app.models.integration import IntegrationConnection
from app.models.inventory import InventoryLevel
from app.models.product import Sku
from app.models.recommendation import Recommendation
from app.models.sales import HistoricalSale
from app.models.tenant import Tenant
from app.services import data_quality_audit

log = structlog.get_logger(__name__)

PLAN_DAYS = 7
MIN_HISTORY_WEEKS = 12
#: Share of SKUs that must carry cost, price and lead time before the decision
#: engine's rupee figures mean anything.
ECONOMICS_COVERAGE_TARGET = 0.8
DATA_QUALITY_TARGET = 70


@dataclass
class Milestone:
    key: str
    day: int
    label: str
    done: bool
    blocking: bool
    detail: str
    action: str | None = None
    action_route: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "day": self.day,
            "label": self.label,
            "done": self.done,
            "blocking": self.blocking,
            "detail": self.detail,
            "action": self.action,
            "action_route": self.action_route,
            "metrics": self.metrics,
        }


async def readiness(
    session: AsyncSession, *, tenant_id: uuid.UUID, industry: str
) -> dict[str, Any]:
    """Evaluate the seven-day plan against the tenant's real data."""
    ind = IndustryCode(industry)
    tenant = await session.get(Tenant, tenant_id)
    started_at = getattr(tenant, "created_at", None) if tenant else None

    milestones: list[Milestone] = []

    # ── Day 1: a data source ─────────────────────────────────────────────────
    connections = int(
        await session.scalar(
            select(func.count())
            .select_from(IntegrationConnection)
            .where(
                IntegrationConnection.tenant_id == tenant_id,
                IntegrationConnection.status.in_(["connected", "syncing"]),
            )
        )
        or 0
    )
    sales_rows = int(
        await session.scalar(
            select(func.count())
            .select_from(HistoricalSale)
            .where(HistoricalSale.tenant_id == tenant_id, HistoricalSale.industry == ind)
        )
        or 0
    )
    milestones.append(
        Milestone(
            key="data_source",
            day=1,
            label="Connect a data source or upload a file",
            done=connections > 0 or sales_rows > 0,
            blocking=True,
            detail=(
                f"{connections} live connection(s), {sales_rows:,} sales rows loaded."
                if (connections or sales_rows)
                else "No sales data yet. A CSV or Excel export is the fastest start — "
                "the file connector accepts the same columns your ERP exports."
            ),
            action="Upload a sales file or connect your ERP",
            action_route="/workspace/integrations",
            metrics={"connections": connections, "sales_rows": sales_rows},
        )
    )

    # ── Day 2: catalogue ─────────────────────────────────────────────────────
    skus = list(
        (
            await session.execute(
                select(Sku).where(
                    Sku.tenant_id == tenant_id, Sku.industry == ind, Sku.is_active.is_(True)
                )
            )
        ).scalars().all()
    )
    milestones.append(
        Milestone(
            key="catalogue",
            day=2,
            label="Load your product catalogue",
            done=len(skus) > 0,
            blocking=True,
            detail=(
                f"{len(skus):,} active SKUs."
                if skus
                else "No SKUs yet. Products are created automatically from a sales import "
                "if the file carries SKU codes."
            ),
            action="Import products",
            action_route="/workspace/products",
            metrics={"active_skus": len(skus)},
        )
    )

    # ── Day 3: enough history ────────────────────────────────────────────────
    week = week_bucket(HistoricalSale.sale_time)
    weeks_covered = int(
        await session.scalar(
            select(func.count(func.distinct(week))).where(
                HistoricalSale.tenant_id == tenant_id,
                HistoricalSale.industry == ind,
                HistoricalSale.sale_time >= datetime.now(UTC) - timedelta(weeks=156),
            )
        )
        or 0
    )
    milestones.append(
        Milestone(
            key="history_depth",
            day=3,
            label=f"At least {MIN_HISTORY_WEEKS} weeks of sales history",
            done=weeks_covered >= MIN_HISTORY_WEEKS,
            blocking=True,
            detail=(
                f"{weeks_covered} distinct weeks of history loaded."
                + (
                    ""
                    if weeks_covered >= MIN_HISTORY_WEEKS
                    else f" Below {MIN_HISTORY_WEEKS} weeks a fitted forecast is not defined — "
                    "every SKU falls back to a zero-shot estimate with low confidence."
                )
            ),
            action="Re-export a longer date range from your source system",
            action_route="/workspace/integrations",
            metrics={"weeks_covered": weeks_covered, "target": MIN_HISTORY_WEEKS},
        )
    )

    # ── Day 3: SKU economics ─────────────────────────────────────────────────
    complete = [
        s for s in skus if s.unit_cost and s.unit_price and s.lead_time_days is not None
    ]
    coverage = (len(complete) / len(skus)) if skus else 0.0
    milestones.append(
        Milestone(
            key="sku_economics",
            day=3,
            label="Cost, price and lead time on your SKUs",
            done=coverage >= ECONOMICS_COVERAGE_TARGET,
            blocking=False,
            detail=(
                f"{coverage:.0%} of SKUs have all three. Lead time sizes every order; "
                "cost and price turn units into rupees."
            ),
            action="Fill in the missing fields in your product import",
            action_route="/workspace/data-quality",
            metrics={
                "complete": len(complete),
                "total": len(skus),
                "coverage": round(coverage, 3),
            },
        )
    )

    # ── Day 4: stock ─────────────────────────────────────────────────────────
    stocked = int(
        await session.scalar(
            select(func.count(func.distinct(InventoryLevel.sku_id))).where(
                InventoryLevel.tenant_id == tenant_id, InventoryLevel.industry == ind
            )
        )
        or 0
    )
    stock_coverage = (stocked / len(skus)) if skus else 0.0
    milestones.append(
        Milestone(
            key="stock_position",
            day=4,
            label="Current stock on hand",
            done=stock_coverage >= ECONOMICS_COVERAGE_TARGET,
            blocking=False,
            detail=(
                f"{stocked:,} of {len(skus):,} SKUs have a recorded stock position. "
                "Without it, order quantities are computed against an estimate and "
                "labelled as such."
            ),
            action="Upload a stock file or connect a WMS feed",
            action_route="/workspace/inventory",
            metrics={"skus_with_stock": stocked, "coverage": round(stock_coverage, 3)},
        )
    )

    # ── Day 4: data quality ──────────────────────────────────────────────────
    quality = await data_quality_audit.audit(session, tenant_id=tenant_id, industry=industry)
    milestones.append(
        Milestone(
            key="data_quality",
            day=4,
            label="Data clean enough to forecast on",
            done=quality["health_score"] >= DATA_QUALITY_TARGET,
            blocking=quality["critical"] > 0,
            detail=(
                f"Health score {quality['health_score']}/100 — {quality['grade']}. "
                f"{quality['critical']} critical issue(s), {quality['warnings']} warning(s)."
            ),
            action="Review and fix the flagged issues",
            action_route="/workspace/data-quality",
            metrics={
                "health_score": quality["health_score"],
                "critical": quality["critical"],
                "warnings": quality["warnings"],
            },
        )
    )

    # ── Day 5: first forecast ────────────────────────────────────────────────
    run = await session.scalar(
        select(ForecastRun)
        .where(
            ForecastRun.tenant_id == tenant_id,
            ForecastRun.industry == ind,
            ForecastRun.status == "completed",
        )
        .order_by(ForecastRun.completed_at.desc())
        .limit(1)
    )
    milestones.append(
        Milestone(
            key="first_forecast",
            day=5,
            label="Run your first forecast",
            done=run is not None,
            blocking=True,
            detail=(
                f"Last completed run {run.completed_at.date().isoformat()} "
                f"over {run.horizon_weeks} weeks."
                if run and run.completed_at
                else "No completed forecast run yet."
            ),
            action="Generate a forecast",
            action_route="/workspace/forecasts",
            metrics={"has_run": run is not None},
        )
    )

    # ── Day 6: first decisions ───────────────────────────────────────────────
    open_recs = int(
        await session.scalar(
            select(func.count())
            .select_from(Recommendation)
            .where(
                Recommendation.tenant_id == tenant_id,
                Recommendation.industry == ind,
                Recommendation.status == DecisionStatus.open,
            )
        )
        or 0
    )
    milestones.append(
        Milestone(
            key="first_decisions",
            day=6,
            label="Get your first order recommendations",
            done=open_recs > 0,
            blocking=False,
            detail=(
                f"{open_recs} open recommendation(s) waiting."
                if open_recs
                else "No recommendations yet — they are generated from the latest forecast run."
            ),
            action="Generate recommendations",
            action_route="/workspace/decisions",
            metrics={"open_recommendations": open_recs},
        )
    )

    # ── Day 7: value realised ────────────────────────────────────────────────
    accepted = int(
        await session.scalar(
            select(func.count())
            .select_from(Recommendation)
            .where(
                Recommendation.tenant_id == tenant_id,
                Recommendation.industry == ind,
                Recommendation.status == DecisionStatus.accepted,
            )
        )
        or 0
    )
    milestones.append(
        Milestone(
            key="value_realised",
            day=7,
            label="Act on a recommendation and start the ROI ledger",
            done=accepted > 0,
            blocking=False,
            detail=(
                f"{accepted} recommendation(s) accepted — the ROI dashboard is live."
                if accepted
                else "The ROI dashboard fills in as you accept recommendations; each one "
                "records what you ordered against what the old policy would have."
            ),
            action="Review the queue and accept an order",
            action_route="/workspace/decisions",
            metrics={"accepted": accepted},
        )
    )

    done_count = sum(1 for m in milestones if m.done)
    percent = round(done_count / len(milestones) * 100)
    blockers = [m for m in milestones if m.blocking and not m.done]
    next_up = blockers[0] if blockers else next((m for m in milestones if not m.done), None)

    day_of_journey = None
    if started_at is not None:
        ref = started_at if started_at.tzinfo else started_at.replace(tzinfo=UTC)
        day_of_journey = max(1, (datetime.now(UTC) - ref).days + 1)

    return {
        "industry": industry,
        "plan_days": PLAN_DAYS,
        "day_of_journey": day_of_journey,
        "percent_complete": percent,
        "milestones_done": done_count,
        "milestones_total": len(milestones),
        "on_track": not blockers,
        "blockers": [m.key for m in blockers],
        "next_action": next_up.as_dict() if next_up else None,
        "milestones": [m.as_dict() for m in milestones],
        "days": [
            {
                "day": d,
                "milestones": [m.as_dict() for m in milestones if m.day == d],
                "complete": all(m.done for m in milestones if m.day == d),
            }
            for d in range(1, PLAN_DAYS + 1)
            if any(m.day == d for m in milestones)
        ],
    }
