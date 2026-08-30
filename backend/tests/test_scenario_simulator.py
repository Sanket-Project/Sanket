"""Tests for the digital-twin simulator.

The point of the simulator is that levers move *physical* parameters and the
consequences fall out of the inventory recursion. These tests assert the
consequences, not the levers — e.g. a supplier outage must actually starve
stock, and a longer lead time must actually cost fill rate.
"""

from __future__ import annotations

import pytest

from app.services.decision_engine import DemandBand, SkuEconomics
from app.services.scenario import (
    PRESETS,
    Scenario,
    SimConfig,
    compare,
    simulate_sku,
)


def band(weeks: int = 26, p50: float = 100.0, spread: float = 30.0) -> DemandBand:
    return DemandBand(
        p10=[p50 - spread] * weeks, p50=[p50] * weeks, p90=[p50 + spread] * weeks
    )


def sku(**kw) -> SkuEconomics:
    defaults = {
        "sku_id": "s1", "sku_code": "SKU-1", "on_hand_units": 1000.0,
        "lead_time_days": 14, "moq": 1, "unit_cost": 10.0, "unit_price": 25.0,
    }
    return SkuEconomics(**{**defaults, **kw})


CONFIG = SimConfig(horizon_weeks=26, review_weeks=4)
BASELINE = Scenario(name="Baseline")


def test_baseline_keeps_a_well_stocked_sku_in_service():
    out = simulate_sku(sku=sku(), band=band(), scenario=BASELINE, config=CONFIG)
    assert out.fill_rate == pytest.approx(1.0)
    assert out.weeks_stocked_out == 0


def test_demand_shock_raises_both_demand_and_replenishment():
    base = simulate_sku(sku=sku(), band=band(), scenario=BASELINE, config=CONFIG)
    surge = simulate_sku(
        sku=sku(), band=band(), scenario=Scenario(demand_shock_pct=30.0), config=CONFIG
    )
    assert surge.demand_units == pytest.approx(base.demand_units * 1.3)
    assert surge.ordered_units > base.ordered_units


def test_ramp_delays_the_full_shock():
    immediate = simulate_sku(
        sku=sku(), band=band(), scenario=Scenario(demand_shock_pct=50.0), config=CONFIG
    )
    ramped = simulate_sku(
        sku=sku(),
        band=band(),
        scenario=Scenario(demand_shock_pct=50.0, ramp_weeks=8),
        config=CONFIG,
    )
    assert ramped.demand_units < immediate.demand_units


def test_supplier_outage_starves_stock_and_breaks_the_fill_rate():
    """Nothing arrives for the outage window — the SKU must actually run dry."""
    thin = sku(on_hand_units=300.0)  # ~3 weeks of cover at 100/week
    out = simulate_sku(
        sku=thin, band=band(), scenario=Scenario(supplier_outage_weeks=12), config=CONFIG
    )
    assert out.weeks_stocked_out > 0
    assert out.fill_rate < 1.0
    assert out.first_stockout_week is not None


def test_outage_can_be_scoped_to_specific_skus():
    thin = sku(on_hand_units=300.0)
    spared = simulate_sku(
        sku=thin,
        band=band(),
        scenario=Scenario(supplier_outage_weeks=12, supplier_outage_sku_ids=("other",)),
        config=CONFIG,
    )
    assert spared.weeks_stocked_out == 0


def test_longer_lead_time_costs_fill_rate():
    thin = sku(on_hand_units=200.0)
    base = simulate_sku(sku=thin, band=band(), scenario=BASELINE, config=CONFIG)
    strike = simulate_sku(
        sku=thin, band=band(), scenario=Scenario(lead_time_delta_days=42), config=CONFIG
    )
    assert strike.fill_rate <= base.fill_rate
    assert strike.short_units >= base.short_units


def test_tariff_squeezes_margin_without_touching_volume():
    base = simulate_sku(sku=sku(), band=band(), scenario=BASELINE, config=CONFIG)
    tariff = simulate_sku(
        sku=sku(), band=band(), scenario=Scenario(cost_change_pct=15.0), config=CONFIG
    )
    assert tariff.shipped_units == pytest.approx(base.shipped_units)
    assert tariff.revenue == pytest.approx(base.revenue)
    assert tariff.gross_margin < base.gross_margin


def test_price_cut_lifts_volume_through_elasticity():
    base = simulate_sku(sku=sku(), band=band(), scenario=BASELINE, config=CONFIG)
    cut = simulate_sku(
        sku=sku(),
        band=band(),
        scenario=Scenario(price_change_pct=-10.0, price_elasticity=-1.2),
        config=CONFIG,
    )
    assert cut.demand_units > base.demand_units


def test_compare_reports_baseline_scenario_and_delta():
    result = compare(
        skus=[sku(on_hand_units=300.0)],
        bands={"s1": band()},
        scenario=Scenario(name="Outage", supplier_outage_weeks=12),
        config=CONFIG,
        currency="INR",
    )
    assert result["baseline"]["fill_rate"] > result["result"]["fill_rate"]
    assert result["impact"]["fill_rate_pts"] < 0
    assert result["impact"]["lost_revenue"] > 0
    assert result["by_sku"][0]["delta"]["short_units"] > 0


def test_compare_baseline_is_unaffected_by_the_scenario():
    """Two different scenarios must produce the same baseline, or every delta lies."""
    args = {"skus": [sku()], "bands": {"s1": band()}, "config": CONFIG, "currency": "INR"}
    a = compare(scenario=Scenario(demand_shock_pct=40.0), **args)
    b = compare(scenario=Scenario(lead_time_delta_days=30), **args)
    assert a["baseline"] == b["baseline"]


def test_a_noop_scenario_matches_its_own_baseline():
    result = compare(
        skus=[sku()], bands={"s1": band()}, scenario=Scenario(), config=CONFIG
    )
    assert result["impact"]["fill_rate_pts"] == 0
    assert result["impact"]["gross_margin"] == 0


def test_skus_without_a_forecast_are_skipped_not_faked():
    result = compare(
        skus=[sku(), sku(sku_id="no-forecast", sku_code="SKU-2")],
        bands={"s1": band()},
        scenario=Scenario(demand_shock_pct=10.0),
        config=CONFIG,
    )
    assert result["result"]["skus"] == 1
    assert {r["sku_id"] for r in result["by_sku"]} == {"s1"}


@pytest.mark.parametrize("key", sorted(PRESETS))
def test_every_preset_builds_a_valid_scenario(key):
    scenario = Scenario(**PRESETS[key]["scenario"])
    result = compare(
        skus=[sku(on_hand_units=400.0)],
        bands={"s1": band()},
        scenario=scenario,
        config=CONFIG,
    )
    assert result["scenario"]["name"]
    assert "impact" in result
