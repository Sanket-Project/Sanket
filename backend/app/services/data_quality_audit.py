"""Dataset-level data quality — the boring feature that decides whether any of
the interesting ones work.

:mod:`app.services.data_quality` validates one row at write time. This module
looks at the *whole* tenant dataset and answers the question a new customer
actually has: **is my data good enough to forecast on, and if not, exactly what
do I fix first?**

Every check reports what it found, why it matters *for this product* (a missing
lead time is not a spreadsheet nit — it silently drops the SKU out of the
decision engine), a sample of affected rows so the user can go look, and
whether we can fix it automatically.

Auto-fixes are deliberately few and all destructive-by-omission rather than
destructive-by-guess: we will delete a row that is provably junk (an exact
duplicate, a future-dated sale, a negative quantity), and we will not invent
values. Everything runs as a dry run unless the caller explicitly opts in.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import structlog
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import IndustryCode
from app.models.inventory import InventoryLevel
from app.models.product import Sku
from app.models.sales import HistoricalSale

log = structlog.get_logger(__name__)

Severity = Literal["critical", "warning", "info"]

SAMPLE_LIMIT = 10
STALE_INVENTORY_DAYS = 30
#: Robust z-score above which a weekly total is called an outlier. 5 median
#: absolute deviations is far enough out that seasonal peaks survive.
OUTLIER_MAD_THRESHOLD = 5.0
MIN_WEEKS_FOR_OUTLIER_TEST = 12

#: Points knocked off the dataset health score per severity, per check that
#: fires. A dataset with three critical problems is not 3% worse than a clean
#: one — it is unusable, and the score should say so.
SEVERITY_WEIGHT: dict[Severity, int] = {"critical": 18, "warning": 8, "info": 2}

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_code(value: str | None) -> str:
    """Collapse a SKU code to its comparable form.

    ``"ABC-123"``, ``"abc 123"`` and ``"ABC_123"`` are the same SKU entered
    three ways by three people, which is exactly how duplicate catalogs happen.
    """
    return _NON_ALNUM.sub("", (value or "").lower())


@dataclass
class Finding:
    key: str
    label: str
    severity: Severity
    count: int
    why_it_matters: str
    how_to_fix: str
    sample: list[dict] = field(default_factory=list)
    autofix: str | None = None  # action key accepted by `apply_fix`

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "severity": self.severity,
            "count": self.count,
            "why_it_matters": self.why_it_matters,
            "how_to_fix": self.how_to_fix,
            "sample": self.sample[:SAMPLE_LIMIT],
            "autofix": self.autofix,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Checks
# ──────────────────────────────────────────────────────────────────────────────


async def _duplicate_skus(
    session: AsyncSession, tenant_id: uuid.UUID, industry: IndustryCode
) -> Finding | None:
    rows = (
        await session.execute(
            select(Sku.id, Sku.sku_code, Sku.external_id, Sku.gtin).where(
                Sku.tenant_id == tenant_id, Sku.industry == industry
            )
        )
    ).fetchall()

    groups: dict[str, list[dict]] = {}
    for r in rows:
        key = normalize_code(r.sku_code)
        if not key:
            continue
        groups.setdefault(key, []).append(
            {"sku_id": str(r.id), "sku_code": r.sku_code, "external_id": r.external_id}
        )

    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    if not dupes:
        return None

    total = sum(len(v) for v in dupes.values())
    return Finding(
        key="duplicate_skus",
        label="Duplicate SKU codes",
        severity="critical",
        count=total,
        why_it_matters=(
            "Sales for one physical product get split across several SKU records, so each one "
            "looks like a low-volume item with too little history to forecast. Stock and "
            "recommendations end up split too."
        ),
        how_to_fix=(
            "Merge the duplicates in your source system and re-import, or map them to a single "
            "SKU code before upload. We do not merge automatically — picking the survivor is a "
            "business decision."
        ),
        sample=[
            {"normalized_code": k, "records": v} for k, v in list(dupes.items())[:SAMPLE_LIMIT]
        ],
    )


async def _duplicate_sales(
    session: AsyncSession, tenant_id: uuid.UUID, industry: IndustryCode
) -> Finding | None:
    rows = (
        await session.execute(
            select(
                HistoricalSale.sku_id,
                HistoricalSale.sale_time,
                HistoricalSale.channel,
                HistoricalSale.units_sold,
                func.count().label("n"),
            )
            .where(HistoricalSale.tenant_id == tenant_id, HistoricalSale.industry == industry)
            .group_by(
                HistoricalSale.sku_id,
                HistoricalSale.sale_time,
                HistoricalSale.channel,
                HistoricalSale.units_sold,
            )
            .having(func.count() > 1)
            .limit(1000)
        )
    ).fetchall()
    if not rows:
        return None

    extra = sum(r.n - 1 for r in rows)
    return Finding(
        key="duplicate_sales_rows",
        label="Duplicate sales rows",
        severity="critical",
        count=extra,
        why_it_matters=(
            "Re-importing the same file double-counts demand. The forecast reads inflated history "
            "and every recommendation over-orders."
        ),
        how_to_fix="Remove the extra copies — the earliest row of each group is kept.",
        autofix="dedupe_sales",
        sample=[
            {
                "sku_id": str(r.sku_id),
                "sale_time": r.sale_time.isoformat() if r.sale_time else None,
                "channel": r.channel,
                "units_sold": r.units_sold,
                "copies": r.n,
            }
            for r in rows[:SAMPLE_LIMIT]
        ],
    )


async def _bad_sales_values(
    session: AsyncSession, tenant_id: uuid.UUID, industry: IndustryCode
) -> list[Finding]:
    findings: list[Finding] = []
    now = datetime.now(UTC)

    negative = (
        await session.execute(
            select(HistoricalSale.sku_id, HistoricalSale.sale_time, HistoricalSale.units_sold)
            .where(
                HistoricalSale.tenant_id == tenant_id,
                HistoricalSale.industry == industry,
                HistoricalSale.units_sold < 0,
            )
            .limit(1000)
        )
    ).fetchall()
    if negative:
        findings.append(
            Finding(
                key="negative_units",
                label="Negative sales quantities",
                severity="critical",
                count=len(negative),
                why_it_matters=(
                    "Returns booked as negative sales rows drag the demand series below zero and "
                    "corrupt the trend. Returns belong in the returns column, not as negative sales."
                ),
                how_to_fix="Delete these rows and re-import returns in the `returns` field.",
                autofix="drop_negative_sales",
                sample=[
                    {
                        "sku_id": str(r.sku_id),
                        "sale_time": r.sale_time.isoformat() if r.sale_time else None,
                        "units_sold": r.units_sold,
                    }
                    for r in negative[:SAMPLE_LIMIT]
                ],
            )
        )

    future = (
        await session.execute(
            select(HistoricalSale.sku_id, HistoricalSale.sale_time, HistoricalSale.units_sold)
            .where(
                HistoricalSale.tenant_id == tenant_id,
                HistoricalSale.industry == industry,
                HistoricalSale.sale_time > now,
            )
            .limit(1000)
        )
    ).fetchall()
    if future:
        findings.append(
            Finding(
                key="future_dated_sales",
                label="Sales dated in the future",
                severity="critical",
                count=len(future),
                why_it_matters=(
                    "Almost always a date-format mix-up (DD/MM read as MM/DD). The rows land in "
                    "weeks that have not happened, so recent history looks empty and the forecast "
                    "starts from the wrong level."
                ),
                how_to_fix=(
                    "Check the date column format in your export, then delete and re-import."
                ),
                autofix="drop_future_sales",
                sample=[
                    {
                        "sku_id": str(r.sku_id),
                        "sale_time": r.sale_time.isoformat() if r.sale_time else None,
                        "units_sold": r.units_sold,
                    }
                    for r in future[:SAMPLE_LIMIT]
                ],
            )
        )

    return findings


async def _orphan_sales(
    session: AsyncSession, tenant_id: uuid.UUID, industry: IndustryCode
) -> Finding | None:
    """Sales rows pointing at a SKU that no longer exists.

    ``historical_sales`` is partitioned and therefore carries no FK, so this is
    the only thing standing between a deleted SKU and silently orphaned demand.
    """
    rows = (
        await session.execute(
            select(HistoricalSale.sku_id, func.count().label("n"), func.sum(HistoricalSale.units_sold).label("units"))
            .outerjoin(Sku, Sku.id == HistoricalSale.sku_id)
            .where(
                HistoricalSale.tenant_id == tenant_id,
                HistoricalSale.industry == industry,
                Sku.id.is_(None),
            )
            .group_by(HistoricalSale.sku_id)
            .limit(500)
        )
    ).fetchall()
    if not rows:
        return None

    return Finding(
        key="orphan_sales",
        label="Sales for unknown SKUs",
        severity="warning",
        count=sum(r.n for r in rows),
        why_it_matters=(
            "This demand is invisible to forecasting and to every dashboard, because there is no "
            "product record to attach it to."
        ),
        how_to_fix="Import the missing SKUs (or their product master) and the history reconnects.",
        sample=[
            {"sku_id": str(r.sku_id), "rows": r.n, "units": int(r.units or 0)}
            for r in rows[:SAMPLE_LIMIT]
        ],
    )


async def _missing_sku_fields(
    session: AsyncSession, tenant_id: uuid.UUID, industry: IndustryCode
) -> list[Finding]:
    rows = (
        await session.execute(
            select(Sku).where(
                Sku.tenant_id == tenant_id, Sku.industry == industry, Sku.is_active.is_(True)
            )
        )
    ).scalars().all()
    if not rows:
        return []

    no_cost = [s for s in rows if not s.unit_cost]
    no_price = [s for s in rows if not s.unit_price]
    no_lead = [s for s in rows if s.lead_time_days is None]

    findings: list[Finding] = []

    def sample(items: list[Sku]) -> list[dict]:
        return [{"sku_id": str(s.id), "sku_code": s.sku_code} for s in items[:SAMPLE_LIMIT]]

    if no_lead:
        findings.append(
            Finding(
                key="missing_lead_time",
                label="SKUs with no supplier lead time",
                severity="critical",
                count=len(no_lead),
                why_it_matters=(
                    "Lead time sets the protection window every purchase recommendation is sized "
                    f"against. Without it these SKUs fall back to a {14}-day assumption, which is "
                    "wrong for anything imported."
                ),
                how_to_fix="Set `lead_time_days` per SKU (or per supplier) in your product master.",
                sample=sample(no_lead),
            )
        )
    if no_cost:
        findings.append(
            Finding(
                key="missing_unit_cost",
                label="SKUs with no unit cost",
                severity="warning",
                count=len(no_cost),
                why_it_matters=(
                    "Every rupee figure — working capital, carrying cost, ROI — is zero for these "
                    "SKUs. They appear free to hold."
                ),
                how_to_fix="Populate `unit_cost` in the product import.",
                sample=sample(no_cost),
            )
        )
    if no_price:
        findings.append(
            Finding(
                key="missing_unit_price",
                label="SKUs with no selling price",
                severity="warning",
                count=len(no_price),
                why_it_matters=(
                    "Revenue at risk and revenue protected cannot be computed, so these SKUs never "
                    "rank in the priority queue no matter how important they are."
                ),
                how_to_fix="Populate `unit_price` in the product import.",
                sample=sample(no_price),
            )
        )
    return findings


async def _inventory_coverage(
    session: AsyncSession, tenant_id: uuid.UUID, industry: IndustryCode
) -> list[Finding]:
    sku_rows = (
        await session.execute(
            select(Sku.id, Sku.sku_code).where(
                Sku.tenant_id == tenant_id, Sku.industry == industry, Sku.is_active.is_(True)
            )
        )
    ).fetchall()
    if not sku_rows:
        return []

    inv_rows = (
        await session.execute(
            select(InventoryLevel.sku_id, func.max(InventoryLevel.as_of).label("as_of"))
            .where(InventoryLevel.tenant_id == tenant_id, InventoryLevel.industry == industry)
            .group_by(InventoryLevel.sku_id)
        )
    ).fetchall()
    have = {r.sku_id: r.as_of for r in inv_rows}

    missing = [r for r in sku_rows if r.id not in have]
    cutoff = datetime.now(UTC) - timedelta(days=STALE_INVENTORY_DAYS)
    stale = [
        r
        for r in sku_rows
        if r.id in have
        and have[r.id] is not None
        and (have[r.id] if have[r.id].tzinfo else have[r.id].replace(tzinfo=UTC)) < cutoff
    ]

    findings: list[Finding] = []
    if missing:
        findings.append(
            Finding(
                key="no_inventory_record",
                label="Active SKUs with no stock record",
                severity="critical",
                count=len(missing),
                why_it_matters=(
                    "With no recorded stock the system falls back to an estimate "
                    "(safety stock × 2) and flags it. Coverage days, shortage alerts and order "
                    "quantities for these SKUs are guesses, not measurements."
                ),
                how_to_fix=(
                    "Connect a WMS/ERP inventory feed, or upload a stock file with on-hand units "
                    "per SKU."
                ),
                sample=[{"sku_id": str(r.id), "sku_code": r.sku_code} for r in missing[:SAMPLE_LIMIT]],
            )
        )
    if stale:
        findings.append(
            Finding(
                key="stale_inventory",
                label=f"Stock last updated over {STALE_INVENTORY_DAYS} days ago",
                severity="warning",
                count=len(stale),
                why_it_matters=(
                    "Order quantities subtract stock on hand. A month-old position means we are "
                    "subtracting inventory that has probably already been sold."
                ),
                how_to_fix="Re-sync the inventory feed, or increase its polling frequency.",
                sample=[
                    {
                        "sku_id": str(r.id),
                        "sku_code": r.sku_code,
                        "as_of": have[r.id].isoformat() if have[r.id] else None,
                    }
                    for r in stale[:SAMPLE_LIMIT]
                ],
            )
        )
    return findings


async def _series_health(
    session: AsyncSession, tenant_id: uuid.UUID, industry: IndustryCode
) -> list[Finding]:
    """Gaps and outliers in the weekly demand series."""
    week = func.date_trunc("week", HistoricalSale.sale_time).label("week")
    rows = (
        await session.execute(
            select(HistoricalSale.sku_id, week, func.sum(HistoricalSale.units_sold).label("units"))
            .where(
                HistoricalSale.tenant_id == tenant_id,
                HistoricalSale.industry == industry,
                HistoricalSale.sale_time >= datetime.now(UTC) - timedelta(weeks=104),
                HistoricalSale.sale_time <= datetime.now(UTC),
            )
            .group_by(HistoricalSale.sku_id, week)
            .order_by(HistoricalSale.sku_id, week)
        )
    ).fetchall()
    if not rows:
        return [
            Finding(
                key="no_sales_history",
                label="No sales history in the last two years",
                severity="critical",
                count=0,
                why_it_matters=(
                    "There is nothing to forecast from. Every downstream feature — forecasts, "
                    "alerts, recommendations, ROI — is inert until history is loaded."
                ),
                how_to_fix="Upload a sales CSV/Excel export, or connect a sales system.",
            )
        ]

    per_sku: dict[uuid.UUID, list[tuple[Any, float]]] = {}
    for r in rows:
        per_sku.setdefault(r.sku_id, []).append((r.week, float(r.units or 0)))

    gappy: list[dict] = []
    outliers: list[dict] = []
    thin: list[dict] = []

    for sku_id, series in per_sku.items():
        weeks = [w for w, _ in series]
        values = [v for _, v in series]
        span_weeks = int((weeks[-1] - weeks[0]).days / 7) + 1
        missing = span_weeks - len(weeks)
        if missing > 0 and span_weeks >= 8:
            gappy.append(
                {
                    "sku_id": str(sku_id),
                    "weeks_covered": len(weeks),
                    "weeks_in_span": span_weeks,
                    "missing_weeks": missing,
                }
            )
        if len(weeks) < 12:
            thin.append({"sku_id": str(sku_id), "weeks_of_history": len(weeks)})

        if len(values) >= MIN_WEEKS_FOR_OUTLIER_TEST:
            ordered = sorted(values)
            mid = len(ordered) // 2
            median = (
                ordered[mid]
                if len(ordered) % 2
                else (ordered[mid - 1] + ordered[mid]) / 2
            )
            devs = sorted(abs(v - median) for v in values)
            m = len(devs) // 2
            mad = devs[m] if len(devs) % 2 else (devs[m - 1] + devs[m]) / 2
            if mad > 0:
                for wk, v in series:
                    z = 0.6745 * (v - median) / mad
                    if abs(z) > OUTLIER_MAD_THRESHOLD:
                        outliers.append(
                            {
                                "sku_id": str(sku_id),
                                "week": wk.date().isoformat(),
                                "units": v,
                                "median_units": median,
                                "robust_z": round(z, 1),
                            }
                        )

    findings: list[Finding] = []
    if gappy:
        findings.append(
            Finding(
                key="missing_weeks",
                label="Gaps in weekly sales history",
                severity="warning",
                count=sum(g["missing_weeks"] for g in gappy),
                why_it_matters=(
                    "A missing week is not a zero-sales week, but the models cannot tell the "
                    "difference. Gaps flatten seasonality and understate demand."
                ),
                how_to_fix=(
                    "Re-export the full date range from your source system. If those weeks really "
                    "had no sales, include explicit zero rows."
                ),
                sample=sorted(gappy, key=lambda g: -g["missing_weeks"])[:SAMPLE_LIMIT],
            )
        )
    if outliers:
        findings.append(
            Finding(
                key="outlier_weeks",
                label="Implausible weekly spikes",
                severity="warning",
                count=len(outliers),
                why_it_matters=(
                    "A single mistyped quantity can dominate a fitted trend. These weeks are more "
                    f"than {OUTLIER_MAD_THRESHOLD:g} median-absolute-deviations from the SKU's own "
                    "median — check them before trusting the forecast."
                ),
                how_to_fix=(
                    "Verify each week against the source. Genuine promotions are fine — mark them "
                    "with the promo flag so the model treats them as explained."
                ),
                sample=sorted(outliers, key=lambda o: -abs(o["robust_z"]))[:SAMPLE_LIMIT],
            )
        )
    if thin:
        findings.append(
            Finding(
                key="thin_history",
                label="SKUs with under 12 weeks of history",
                severity="info",
                count=len(thin),
                why_it_matters=(
                    "Below 12 weeks a fitted forecast is not defined; these SKUs get a zero-shot "
                    "estimate and an 'insufficient' confidence band."
                ),
                how_to_fix="Load more history, or accept the lower confidence for new products.",
                sample=sorted(thin, key=lambda t: t["weeks_of_history"])[:SAMPLE_LIMIT],
            )
        )
    return findings


# ──────────────────────────────────────────────────────────────────────────────
# Report
# ──────────────────────────────────────────────────────────────────────────────


async def audit(
    session: AsyncSession, *, tenant_id: uuid.UUID, industry: str
) -> dict[str, Any]:
    """Run every check and score the dataset 0–100."""
    ind = IndustryCode(industry)
    findings: list[Finding] = []

    for maybe in (
        await _duplicate_skus(session, tenant_id, ind),
        await _duplicate_sales(session, tenant_id, ind),
        await _orphan_sales(session, tenant_id, ind),
    ):
        if maybe is not None:
            findings.append(maybe)

    findings.extend(await _bad_sales_values(session, tenant_id, ind))
    findings.extend(await _missing_sku_fields(session, tenant_id, ind))
    findings.extend(await _inventory_coverage(session, tenant_id, ind))
    findings.extend(await _series_health(session, tenant_id, ind))

    deduction = sum(SEVERITY_WEIGHT[f.severity] for f in findings)
    score = max(0, 100 - deduction)
    rank = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (rank[f.severity], -f.count))

    return {
        "industry": industry,
        "health_score": score,
        "grade": _grade(score),
        "checks_run": 11,
        "issues_found": len(findings),
        "critical": sum(1 for f in findings if f.severity == "critical"),
        "warnings": sum(1 for f in findings if f.severity == "warning"),
        "fixable_automatically": [f.autofix for f in findings if f.autofix],
        "findings": [f.as_dict() for f in findings],
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _grade(score: int) -> str:
    if score >= 90:
        return "Ready to forecast"
    if score >= 70:
        return "Usable with caveats"
    if score >= 40:
        return "Needs cleanup"
    return "Not forecastable yet"


# ──────────────────────────────────────────────────────────────────────────────
# Auto-fixes
# ──────────────────────────────────────────────────────────────────────────────

FIX_ACTIONS = ("dedupe_sales", "drop_future_sales", "drop_negative_sales")


async def apply_fix(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    industry: str,
    action: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Apply one auto-fix. Dry run by default — the caller must opt into writes.

    Only provably-junk rows are ever removed. Nothing here fills in a missing
    value: an invented cost or lead time would be indistinguishable from a real
    one a week later.
    """
    if action not in FIX_ACTIONS:
        raise ValueError(f"Unknown fix action '{action}'")

    ind = IndustryCode(industry)
    now = datetime.now(UTC)

    if action == "drop_future_sales":
        where = and_(
            HistoricalSale.tenant_id == tenant_id,
            HistoricalSale.industry == ind,
            HistoricalSale.sale_time > now,
        )
        affected = await _count(session, where)
        if not dry_run and affected:
            await session.execute(delete(HistoricalSale).where(where))

    elif action == "drop_negative_sales":
        where = and_(
            HistoricalSale.tenant_id == tenant_id,
            HistoricalSale.industry == ind,
            HistoricalSale.units_sold < 0,
        )
        affected = await _count(session, where)
        if not dry_run and affected:
            await session.execute(delete(HistoricalSale).where(where))

    else:  # dedupe_sales
        affected = await _dedupe_sales(session, tenant_id, ind, dry_run=dry_run)

    log.info(
        "data_quality.fix",
        tenant_id=str(tenant_id),
        action=action,
        dry_run=dry_run,
        affected=affected,
    )
    return {
        "action": action,
        "dry_run": dry_run,
        "rows_affected": affected,
        "applied": (not dry_run) and affected > 0,
    }


async def _count(session: AsyncSession, where: Any) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(HistoricalSale).where(where)) or 0
    )


async def _dedupe_sales(
    session: AsyncSession, tenant_id: uuid.UUID, industry: IndustryCode, *, dry_run: bool
) -> int:
    """Keep the lowest-id row of each identical group, delete the rest.

    ``historical_sales`` is partitioned with a composite mapper key and no
    unique constraint, so the duplicates have to be identified explicitly rather
    than left to an upsert.
    """
    groups = (
        await session.execute(
            select(
                HistoricalSale.sku_id,
                HistoricalSale.sale_time,
                HistoricalSale.channel,
                HistoricalSale.units_sold,
                func.count().label("n"),
                func.min(HistoricalSale.id).label("keep_id"),
            )
            .where(HistoricalSale.tenant_id == tenant_id, HistoricalSale.industry == industry)
            .group_by(
                HistoricalSale.sku_id,
                HistoricalSale.sale_time,
                HistoricalSale.channel,
                HistoricalSale.units_sold,
            )
            .having(func.count() > 1)
        )
    ).fetchall()

    removed = sum(g.n - 1 for g in groups)
    if dry_run or not groups:
        return removed

    for g in groups:
        await session.execute(
            delete(HistoricalSale).where(
                HistoricalSale.tenant_id == tenant_id,
                HistoricalSale.sku_id == g.sku_id,
                HistoricalSale.sale_time == g.sale_time,
                HistoricalSale.channel == g.channel,
                HistoricalSale.units_sold == g.units_sold,
                HistoricalSale.id != g.keep_id,
            )
        )
    return removed
