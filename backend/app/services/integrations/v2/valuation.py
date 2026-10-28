"""V2 Historical Costing and Qualified Profitability (P0-07).

Enforces:
- COGS is based strictly on historical valuation/issue cost at the time of fulfillment.
- Never use current catalog cost as historical COGS.
- Customer returns reverse the original issue COGS (for restocked items).
- Missing cost history qualifies gross profit as unavailable (is_cost_known=False), never zero-cost.
- Gross Margin % = 100 * Gross Profit / Net Revenue (when Net Revenue > 0).
- Markup % = 100 * Gross Profit / Net COGS (when Net COGS > 0).
- Negative gross profit is preserved for genuine business loss.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

_TWO_DP = Decimal("0.01")
_FOUR_DP = Decimal("0.0001")


def _round_paise(d: Decimal) -> Decimal:
    return d.quantize(_TWO_DP, rounding=ROUND_HALF_UP)


@dataclass
class SaleProfitabilityInput:
    gross_ex_tax: Decimal
    discount_ex_tax: Decimal
    net_sale_ex_tax: Decimal
    quantity_sold: int
    historical_unit_cost: Decimal | None


@dataclass
class ReturnProfitabilityInput:
    return_value_ex_tax: Decimal
    returned_qty: int
    original_unit_cost: Decimal | None
    disposition: str = "restock"


@dataclass
class ProfitabilityResult:
    net_revenue_ex_tax: Decimal
    net_cogs: Decimal | None
    gross_profit: Decimal | None
    gross_margin_pct: Decimal | None
    markup_pct: Decimal | None
    is_cost_known: bool


def calculate_period_profitability(
    sales: list[SaleProfitabilityInput],
    returns: list[ReturnProfitabilityInput],
) -> ProfitabilityResult:
    total_net_sale = sum((s.net_sale_ex_tax for s in sales), Decimal("0.00"))
    total_credit = sum((r.return_value_ex_tax for r in returns), Decimal("0.00"))
    net_revenue = _round_paise(total_net_sale - total_credit)

    # Check if any sale or return has unknown historical unit cost
    has_unknown_sale_cost = any(s.historical_unit_cost is None for s in sales if s.quantity_sold > 0)
    has_unknown_return_cost = any(r.original_unit_cost is None for r in returns if r.returned_qty > 0)

    if has_unknown_sale_cost or has_unknown_return_cost:
        return ProfitabilityResult(
            net_revenue_ex_tax=net_revenue,
            net_cogs=None,
            gross_profit=None,
            gross_margin_pct=None,
            markup_pct=None,
            is_cost_known=False,
        )

    # All costs known: calculate historical COGS
    sale_cogs = sum(
        (Decimal(s.quantity_sold) * (s.historical_unit_cost or Decimal("0")) for s in sales),
        Decimal("0.00"),
    )

    # Restocked returns reverse original COGS; damaged goods cost is retained as loss
    reversed_cogs = sum(
        (
            Decimal(r.returned_qty) * (r.original_unit_cost or Decimal("0"))
            for r in returns
            if r.disposition == "restock"
        ),
        Decimal("0.00"),
    )

    net_cogs = _round_paise(sale_cogs - reversed_cogs)
    gross_profit = _round_paise(net_revenue - net_cogs)

    # Gross margin % based on sale (denominator = net_revenue_ex_tax)
    gross_margin_pct: Decimal | None = None
    if net_revenue > Decimal("0"):
        gross_margin_pct = (100 * gross_profit / net_revenue).quantize(_FOUR_DP, rounding=ROUND_HALF_UP)

    # Markup % based on cost (denominator = net_cogs)
    markup_pct: Decimal | None = None
    if net_cogs != Decimal("0"):
        markup_pct = (100 * gross_profit / net_cogs).quantize(_FOUR_DP, rounding=ROUND_HALF_UP)

    return ProfitabilityResult(
        net_revenue_ex_tax=net_revenue,
        net_cogs=net_cogs,
        gross_profit=gross_profit,
        gross_margin_pct=gross_margin_pct,
        markup_pct=markup_pct,
        is_cost_known=True,
    )
