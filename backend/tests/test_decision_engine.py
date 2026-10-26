"""Tests for the pure decision engine and confidence scorer.

These cover the arithmetic that turns a forecast into a purchase order, since
that arithmetic is what the ROI claim on the dashboard ultimately rests on. No
database, no FastAPI — just the policy math.
"""

from __future__ import annotations

import math

import pytest

from app.services.decision_engine import (
    DemandBand,
    PolicyConfig,
    SkuEconomics,
    _pooled_sigma,
    _round_to_moq,
    _window_sum,
    decide,
)
from app.services.forecast_confidence import (
    ConfidenceFeatures,
    features_from_series,
    score_confidence,
)


def flat_band(weeks: int = 26, p50: float = 100.0, spread: float = 40.0) -> DemandBand:
    return DemandBand(
        p10=[p50 - spread] * weeks,
        p50=[p50] * weeks,
        p90=[p50 + spread] * weeks,
    )


def confident() -> object:
    return score_confidence(ConfidenceFeatures(history_weeks=104, zero_weeks_ratio=0.0))


# ── Window arithmetic ────────────────────────────────────────────────────────


def test_window_sum_prorates_the_partial_week():
    weekly = [10.0] * 10
    # 10 days = one whole week + 3/7 of the next.
    assert _window_sum(weekly, 10) == pytest.approx(10 + 10 * 3 / 7)


def test_window_sum_extends_last_value_past_the_horizon():
    """A protection window longer than the forecast must not silently order zero."""
    assert _window_sum([10.0, 10.0], 28) == pytest.approx(40.0)


def test_pooled_sigma_grows_as_sqrt_of_the_window():
    band = flat_band(weeks=8)
    one = _pooled_sigma(band, 7)
    four = _pooled_sigma(band, 28)
    assert four == pytest.approx(one * math.sqrt(4), rel=1e-6)


@pytest.mark.parametrize(
    ("units", "moq", "expected"),
    [(0, 100, 0), (-5, 100, 0), (1, 100, 100), (100, 100, 100), (101, 100, 200), (7, 1, 7)],
)
def test_round_to_moq(units, moq, expected):
    assert _round_to_moq(units, moq) == expected


# ── Purchase orders ──────────────────────────────────────────────────────────


def test_order_covers_lead_time_plus_review_period_with_safety_stock():
    sku = SkuEconomics(
        sku_id="s1", sku_code="SKU-1", on_hand_units=0.0,
        lead_time_days=14, moq=1, unit_cost=10.0, unit_price=25.0,
    )
    policy = PolicyConfig(service_level=0.97, review_period_days=28)
    [decision] = [
        d for d in decide(sku=sku, band=flat_band(), confidence=confident(), policy=policy)
        if d.kind == "purchase_order"
    ]

    # 42-day protection window at 100/week = 600 units of expected demand.
    assert decision.inputs["protection_days"] == 42
    assert decision.inputs["demand_p50_over_window"] == pytest.approx(600.0)
    # Plus z(0.97)·σ of safety stock — strictly more than bare demand.
    assert decision.recommended_units > 600
    assert decision.inputs["safety_stock_units"] > 0


def test_existing_stock_and_inbound_reduce_the_order():
    band = flat_band()
    policy = PolicyConfig(review_period_days=28)
    bare = SkuEconomics(sku_id="s", sku_code="S", on_hand_units=0.0, lead_time_days=14)
    stocked = SkuEconomics(
        sku_id="s", sku_code="S", on_hand_units=300.0, inbound_units=100.0, lead_time_days=14
    )

    [a] = [d for d in decide(sku=bare, band=band, confidence=confident(), policy=policy)
           if d.kind == "purchase_order"]
    [b] = [d for d in decide(sku=stocked, band=band, confidence=confident(), policy=policy)
           if d.kind == "purchase_order"]
    assert b.recommended_units == pytest.approx(a.recommended_units - 400, abs=1)


def test_reserved_stock_is_not_counted_as_available():
    policy = PolicyConfig(review_period_days=28)
    sku = SkuEconomics(
        sku_id="s", sku_code="S", on_hand_units=300.0, reserved_units=300.0, lead_time_days=14
    )
    [d] = [x for x in decide(sku=sku, band=flat_band(), confidence=confident(), policy=policy)
           if x.kind == "purchase_order"]
    assert d.inputs["position_units"] == 0.0


def test_baseline_orders_more_than_the_policy():
    """The p90-cover baseline is what the working-capital claim is measured against."""
    sku = SkuEconomics(sku_id="s", sku_code="S", on_hand_units=0.0, lead_time_days=14,
                       unit_cost=10.0)
    [d] = [x for x in decide(sku=sku, band=flat_band(), confidence=confident())
           if x.kind == "purchase_order"]
    assert d.baseline_units > d.recommended_units
    assert d.economics["working_capital_released"] == pytest.approx(
        (d.baseline_units - d.recommended_units) * 10.0
    )


def test_moq_rounding_is_reported_as_a_reason():
    sku = SkuEconomics(sku_id="s", sku_code="S", on_hand_units=0.0, lead_time_days=14, moq=1000)
    [d] = [x for x in decide(sku=sku, band=flat_band(), confidence=confident())
           if x.kind == "purchase_order"]
    assert d.recommended_units % 1000 == 0
    assert any(r.code == "moq_rounding" for r in d.reasons)


def test_higher_service_level_orders_more():
    sku = SkuEconomics(sku_id="s", sku_code="S", on_hand_units=0.0, lead_time_days=14)
    band = flat_band()
    low = [x for x in decide(sku=sku, band=band, confidence=confident(),
                             policy=PolicyConfig(service_level=0.90))
           if x.kind == "purchase_order"][0]
    high = [x for x in decide(sku=sku, band=band, confidence=confident(),
                              policy=PolicyConfig(service_level=0.99))
            if x.kind == "purchase_order"][0]
    assert high.recommended_units > low.recommended_units


def test_urgency_is_critical_when_cover_is_shorter_than_lead_time():
    # 50 units against 100/week is 3.5 days of cover, well under a 30-day lead time.
    sku = SkuEconomics(sku_id="s", sku_code="S", on_hand_units=50.0, lead_time_days=30)
    [d] = [x for x in decide(sku=sku, band=flat_band(), confidence=confident())
           if x.kind == "purchase_order"]
    assert d.urgency == "critical"


def test_every_order_explains_itself():
    sku = SkuEconomics(sku_id="s", sku_code="S", on_hand_units=100.0, lead_time_days=21,
                       unit_cost=10.0, unit_price=25.0)
    [d] = [x for x in decide(sku=sku, band=flat_band(), confidence=confident())
           if x.kind == "purchase_order"]
    codes = {r.code for r in d.reasons}
    assert {"protection_window", "forecast_demand", "service_level"} <= codes
    assert all(r.text for r in d.reasons)


def test_low_confidence_is_surfaced_on_the_order():
    weak = score_confidence(ConfidenceFeatures(history_weeks=14, zero_weeks_ratio=0.7))
    sku = SkuEconomics(sku_id="s", sku_code="S", on_hand_units=0.0, lead_time_days=14)
    [d] = [x for x in decide(sku=sku, band=flat_band(), confidence=weak)
           if x.kind == "purchase_order"]
    assert any(r.code == "low_confidence" for r in d.reasons)


# ── Other decision kinds ─────────────────────────────────────────────────────


def test_excess_stock_is_flagged_instead_of_an_order():
    sku = SkuEconomics(sku_id="s", sku_code="S", on_hand_units=100_000.0, lead_time_days=14,
                       unit_cost=10.0)
    kinds = {d.kind for d in decide(sku=sku, band=flat_band(), confidence=confident())}
    assert "excess_stock" in kinds
    assert "purchase_order" not in kinds


def test_safety_stock_correction_is_raised_when_the_setting_is_stale():
    sku = SkuEconomics(
        sku_id="s", sku_code="S", on_hand_units=0.0, lead_time_days=14,
        configured_safety_stock=1,
    )
    [d] = [x for x in decide(sku=sku, band=flat_band(), confidence=confident())
           if x.kind == "safety_stock_update"]
    assert d.recommended_units > 1


# ── Confidence ───────────────────────────────────────────────────────────────


def test_short_history_is_insufficient_regardless_of_score():
    s = score_confidence(ConfidenceFeatures(history_weeks=6))
    assert s.band == "insufficient"
    assert not s.is_actionable
    assert any("6 week" in r for r in s.reasons)


def test_clean_long_history_scores_high():
    s = score_confidence(ConfidenceFeatures(history_weeks=104, zero_weeks_ratio=0.0))
    assert s.score == 100
    assert s.band == "high"


def test_every_lost_point_is_explained():
    s = score_confidence(
        ConfidenceFeatures(
            history_weeks=30,
            zero_weeks_ratio=0.65,
            days_since_last_sale=120,
            relative_interval_width=2.0,
            backtest_wape=0.6,
        )
    )
    assert s.score < 60
    assert s.band == "low"
    # Deductions reconcile to the score, which floors at 0 rather than going negative.
    assert s.score == max(0, 100 - sum(-d["points"] for d in s.deductions))
    assert {d["code"] for d in s.deductions} == {
        "short_history",
        "highly_intermittent",
        "stale_data",
        "wide_interval",
        "poor_backtest",
    }


def test_measured_backtest_accuracy_is_credited():
    s = score_confidence(ConfidenceFeatures(history_weeks=104, backtest_wape=0.1))
    assert s.score == 100
    assert any("10% error" in r for r in s.reasons)


def test_features_from_series_counts_zero_weeks():
    f = features_from_series(weekly_units=[0, 0, 5, 0, 10, 0, 0, 3])
    assert f.history_weeks == 8
    assert f.zero_weeks_ratio == pytest.approx(5 / 8)


def test_features_from_series_derives_interval_width():
    f = features_from_series(
        weekly_units=[10] * 20, p10_sum=80.0, p50_sum=100.0, p90_sum=140.0
    )
    assert f.relative_interval_width == pytest.approx(0.6)


# ── Unknown money stays unknown (deep audit F3) ──────────────────────────────


def _po(sku: SkuEconomics):
    return next(d for d in decide(sku=sku, band=flat_band(), confidence=confident())
                if d.kind == "purchase_order")


def test_unknown_unit_cost_yields_no_capital_figures():
    sku = SkuEconomics(sku_id="a", sku_code="A", on_hand_units=0, unit_cost=0.0,
                       unit_price=100.0, cost_known=False)
    order = _po(sku)
    for key in ("capital_committed", "baseline_capital", "working_capital_released",
                "holding_cost_over_window"):
        assert order.economics[key] is None, key
    assert order.economics["revenue_protected"] > 0
    assert order.inputs["unit_cost"] is None


def test_unknown_unit_price_yields_no_revenue_protected():
    sku = SkuEconomics(sku_id="a", sku_code="A", on_hand_units=0, unit_cost=40.0,
                       unit_price=0.0, price_known=False)
    econ = _po(sku).economics
    assert econ["revenue_protected"] is None
    assert econ["capital_committed"] > 0


def test_a_recorded_zero_cost_is_a_known_zero():
    sku = SkuEconomics(sku_id="a", sku_code="A", on_hand_units=0, unit_cost=0.0, unit_price=100.0)
    assert _po(sku).economics["capital_committed"] == 0.0


def test_excess_stock_with_unknown_cost_does_not_claim_locked_capital():
    sku = SkuEconomics(sku_id="a", sku_code="A", on_hand_units=5000, unit_cost=0.0,
                       cost_known=False)
    excess = next(d for d in decide(sku=sku, band=flat_band(), confidence=confident())
                  if d.kind == "excess_stock")
    assert excess.economics["capital_locked"] is None
    assert excess.economics["annual_holding_cost"] is None
    assert all(r.code != "capital_locked" for r in excess.reasons)
