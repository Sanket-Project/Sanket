"""Tests for V2 Historical Costing & Qualified Profitability (P0-07)."""

from __future__ import annotations

from decimal import Decimal
import pytest

from app.services.integrations.v2 import valuation as v2_val


def test_sample_kurti_profitability_reconciliation():
    """Verify exact arithmetic from Retail V2 review package README.md:
    Sell 2 kurtis for INR 1,800 ex-tax (after INR 200 discount); tax INR 90.
    Return 1 kurti for INR 900 ex-tax; refund INR 945.
    Retained ex-tax net revenue = INR 900.
    Historical issue cost = INR 600/unit.
    Retained COGS = INR 600.
    Gross Profit = INR 300.
    Gross Margin = 33.3333%.
    Markup = 50.0000%.
    """
    sale_line = v2_val.SaleProfitabilityInput(
        gross_ex_tax=Decimal("2000.00"),
        discount_ex_tax=Decimal("200.00"),
        net_sale_ex_tax=Decimal("1800.00"),
        quantity_sold=2,
        historical_unit_cost=Decimal("600.0000"),
    )
    return_line = v2_val.ReturnProfitabilityInput(
        return_value_ex_tax=Decimal("900.00"),
        returned_qty=1,
        original_unit_cost=Decimal("600.0000"),
        disposition="restock",
    )

    profit = v2_val.calculate_period_profitability(sales=[sale_line], returns=[return_line])
    assert profit.net_revenue_ex_tax == Decimal("900.00")
    assert profit.net_cogs == Decimal("600.00")
    assert profit.gross_profit == Decimal("300.00")
    assert profit.gross_margin_pct == Decimal("33.3333")
    assert profit.markup_pct == Decimal("50.0000")
    assert profit.is_cost_known is True


def test_missing_historical_cost_marks_profitability_unavailable():
    """Missing cost history must qualify gross profit as unavailable, never defaulting to zero-cost!"""
    sale_line = v2_val.SaleProfitabilityInput(
        gross_ex_tax=Decimal("1000.00"),
        discount_ex_tax=Decimal("0.00"),
        net_sale_ex_tax=Decimal("1000.00"),
        quantity_sold=1,
        historical_unit_cost=None,  # Unknown historical cost
    )
    profit = v2_val.calculate_period_profitability(sales=[sale_line], returns=[])
    assert profit.net_revenue_ex_tax == Decimal("1000.00")
    assert profit.net_cogs is None
    assert profit.gross_profit is None
    assert profit.gross_margin_pct is None
    assert profit.is_cost_known is False


def test_negative_gross_profit_preserved_for_loss():
    """Sales below cost produce genuine negative gross profit, which must be preserved, not clamped."""
    sale_line = v2_val.SaleProfitabilityInput(
        gross_ex_tax=Decimal("500.00"),
        discount_ex_tax=Decimal("0.00"),
        net_sale_ex_tax=Decimal("500.00"),
        quantity_sold=1,
        historical_unit_cost=Decimal("800.0000"),
    )
    profit = v2_val.calculate_period_profitability(sales=[sale_line], returns=[])
    assert profit.net_revenue_ex_tax == Decimal("500.00")
    assert profit.net_cogs == Decimal("800.00")
    assert profit.gross_profit == Decimal("-300.00")
    assert profit.gross_margin_pct == Decimal("-60.0000")
    assert profit.markup_pct == Decimal("-37.5000")


def test_zero_revenue_denominator_marks_margin_unavailable():
    """If net revenue is zero, gross margin percentage cannot divide by zero and is unavailable."""
    profit = v2_val.calculate_period_profitability(sales=[], returns=[])
    assert profit.net_revenue_ex_tax == Decimal("0.00")
    assert profit.gross_margin_pct is None
