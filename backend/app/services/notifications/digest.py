"""The morning digest — the whole product, compressed into one message.

Most SME owners do not want a dashboard. They want the answer:

    Good morning, Sharma Distributors.

    ⚠️ PARA-500-10 runs out in 8 days
       Order 1,500 units — saves about ₹42,000

Everything in here is written for a phone screen and for someone who will read
it once, standing up. No jargon, no percentiles, no chart references. Numbers
are formatted the way Indian businesses read them (lakh / crore), and every
line ends with an action or is dropped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import ShortageAlert
from app.models.enums import AlertStatus, DecisionStatus, IndustryCode
from app.models.product import Sku
from app.models.recommendation import Recommendation
from app.services.notifications.whatsapp import WhatsAppConfig

log = structlog.get_logger(__name__)

_URGENCY_ICON = {"critical": "🔴", "high": "🟠", "normal": "🟡", "low": "⚪"}


def format_money(amount: float, currency: str = "INR") -> str:
    """Indian numbering for rupees, plain grouping for everything else."""
    if currency != "INR":
        return f"{currency} {amount:,.0f}"
    a = abs(amount)
    sign = "-" if amount < 0 else ""
    if a >= 1_00_00_000:
        return f"{sign}₹{a / 1_00_00_000:.2f} Cr"
    if a >= 1_00_000:
        return f"{sign}₹{a / 1_00_000:.2f} L"
    if a >= 1_000:
        return f"{sign}₹{a:,.0f}"
    return f"{sign}₹{a:.0f}"


@dataclass
class DigestItem:
    sku_code: str
    urgency: str
    headline: str
    units: int
    value: float
    value_label: str
    days_of_cover: float | None
    confidence: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "sku_code": self.sku_code,
            "urgency": self.urgency,
            "headline": self.headline,
            "units": self.units,
            "value": self.value,
            "value_label": self.value_label,
            "days_of_cover": self.days_of_cover,
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass
class DailyDigest:
    tenant_name: str
    industry: str
    currency: str = "INR"
    items: list[DigestItem] = field(default_factory=list)
    open_alerts: int = 0
    total_units: int = 0
    total_value: float = 0.0
    #: Orders with no recorded value (unknown price and cost). While any exist
    #: the total is withheld — a sum of only the valued ones is not the total.
    unvalued: int = 0
    more_count: int = 0
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    #: Set when there is genuinely nothing to say, so callers can skip sending
    #: rather than pushing a daily "all clear" nobody asked for.
    empty_reason: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.items and self.open_alerts == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "tenant_name": self.tenant_name,
            "industry": self.industry,
            "currency": self.currency,
            "items": [i.as_dict() for i in self.items],
            "open_alerts": self.open_alerts,
            "total_units": self.total_units,
            "total_value": None if self.unvalued else self.total_value,
            "unvalued": self.unvalued,
            "more_count": self.more_count,
            "generated_at": self.generated_at.isoformat(),
            "empty_reason": self.empty_reason,
        }


async def build_digest(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    tenant_name: str,
    industry: str,
    config: WhatsAppConfig,
) -> DailyDigest:
    """Assemble the digest from the live decision queue and open alerts."""
    ind = IndustryCode(industry)
    digest = DailyDigest(tenant_name=tenant_name, industry=industry)

    recs = list(
        (
            await session.execute(
                select(Recommendation).where(
                    Recommendation.tenant_id == tenant_id,
                    Recommendation.industry == ind,
                    Recommendation.status == DecisionStatus.open,
                    # Same rule as the queue: past expires_at it is not actionable.
                    or_(
                        Recommendation.expires_at.is_(None),
                        Recommendation.expires_at > datetime.now(UTC),
                    ),
                    Recommendation.kind == "purchase_order",
                    Recommendation.confidence >= config.min_confidence,
                )
            )
        ).scalars().all()
    )

    if config.include_alerts:
        digest.open_alerts = len(
            (
                await session.execute(
                    select(ShortageAlert.id).where(
                        ShortageAlert.tenant_id == tenant_id,
                        ShortageAlert.industry == ind,
                        ShortageAlert.status == AlertStatus.open,
                    )
                )
            ).fetchall()
        )

    if not recs:
        digest.empty_reason = (
            "No purchase recommendations above the confidence threshold today."
        )
        return digest

    codes = {
        r.id: r.sku_code
        for r in (
            await session.execute(
                select(Sku.id, Sku.sku_code).where(
                    Sku.tenant_id == tenant_id, Sku.id.in_([r.sku_id for r in recs])
                )
            )
        ).fetchall()
    }

    rank = {"critical": 0, "high": 1, "normal": 2, "low": 3}
    recs.sort(
        key=lambda r: (
            rank.get(str(r.urgency), 9),
            -float((r.economics or {}).get("revenue_protected") or 0),
        )
    )

    for r in recs:
        econ = r.economics or {}
        inputs = r.inputs or {}
        digest.currency = r.currency or digest.currency
        # The number the owner cares about: revenue this order protects, or
        # failing that the capital it releases against the old way of ordering.
        value = float(econ.get("revenue_protected") or 0)
        label = "protects"
        if value <= 0:
            value = float(econ.get("working_capital_released") or 0)
            label = "frees up"
        if econ.get("revenue_protected") is None and econ.get("working_capital_released") is None:
            digest.unvalued += 1

        digest.items.append(
            DigestItem(
                sku_code=codes.get(r.sku_id, str(r.sku_id)[:8]),
                urgency=str(r.urgency),
                headline=r.headline,
                units=r.recommended_units,
                value=value,
                value_label=label,
                days_of_cover=inputs.get("days_of_cover"),
                confidence=r.confidence,
                reason=_short_reason(r),
            )
        )
        digest.total_units += r.recommended_units
        digest.total_value += value

    digest.more_count = max(0, len(digest.items) - config.max_items)
    digest.items = digest.items[: config.max_items]
    return digest


def _short_reason(rec: Recommendation) -> str:
    """One clause the owner can act on, not the full derivation."""
    inputs = rec.inputs or {}
    cover = inputs.get("days_of_cover")
    lead = inputs.get("lead_time_days")
    if isinstance(cover, (int, float)) and isinstance(lead, (int, float)):
        if cover <= lead:
            return f"stock runs out in {cover:.0f} days, supplier takes {lead:.0f}"
        return f"{cover:.0f} days of stock left, supplier takes {lead:.0f}"
    for r in rec.reasons or []:
        if r.get("code") == "demand_trend":
            return str(r.get("text", ""))
    return "forecast demand exceeds stock on hand"


def render_text(digest: DailyDigest) -> str:
    """Render the digest as a WhatsApp text body."""
    if digest.is_empty:
        return (
            f"Good morning, {digest.tenant_name}.\n\n"
            "Nothing needs your attention today — no stockout risks and no orders due.\n\n"
            "— SANKET"
        )

    lines = [f"Good morning, {digest.tenant_name}.", ""]

    if digest.items:
        lines.append(f"*{len(digest.items)} order{'s' if len(digest.items) != 1 else ''} to place today*")
        lines.append("")
        for item in digest.items:
            icon = _URGENCY_ICON.get(item.urgency, "•")
            lines.append(f"{icon} *{item.sku_code}*")
            lines.append(f"   Order {item.units:,} units")
            lines.append(f"   Why: {item.reason}")
            if item.value > 0:
                lines.append(
                    f"   {item.value_label.capitalize()} "
                    f"{format_money(item.value, digest.currency)}"
                )
            if item.confidence < 60:
                lines.append(f"   ⚠️ Forecast confidence only {item.confidence}% — worth a check")
            lines.append("")

    if digest.more_count:
        lines.append(f"…and {digest.more_count} more in the app.")
        lines.append("")

    if digest.unvalued:
        plural = "order has" if digest.unvalued == 1 else "orders have"
        lines.append(
            f"{digest.unvalued} {plural} no recorded value, so no total is shown — "
            "add unit costs and prices in the app."
        )
    elif digest.total_value > 0:
        lines.append(
            f"Total at stake: {format_money(digest.total_value, digest.currency)} "
            f"across {digest.total_units:,} units."
        )

    if digest.open_alerts:
        lines.append(f"🔔 {digest.open_alerts} open shortage alert(s).")

    lines.append("")
    lines.append("Reply STOP to pause these messages.")
    lines.append("— SANKET")
    return "\n".join(lines).strip()
