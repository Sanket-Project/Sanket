"""share_split_v1 maths (spec §4.1–§4.2). Pure: no database."""
from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from app.services.location_shares import (
    HALF_LIFE_WEEKS, WeekObs, blend_shares, shares_from_obs, split_week,
)

WEEKS = [date(2026, 8, 3) + timedelta(weeks=i) for i in range(12)]  # oldest → newest


def _flat(loc, per_week, weeks=WEEKS, in_stock=None):
    return [WeekObs(w, loc, per_week, in_stock) for w in weeks]


def test_steady_two_stores_split_by_volume():
    r = shares_from_obs(_flat("a", 30) + _flat("b", 10), WEEKS)
    assert r.shares == pytest.approx({"a": 0.75, "b": 0.25})
    assert r.unassigned == 0


def test_recent_weeks_weigh_more():
    obs = _flat("a", 10, WEEKS[:6]) + _flat("b", 10, WEEKS[6:])
    r = shares_from_obs(obs, WEEKS)
    assert r.shares["b"] > r.shares["a"]


def test_out_of_stock_weeks_do_not_shrink_a_share():
    # b sells 10/week but was out of stock in the 6 newest weeks (selling 0).
    obs = _flat("a", 10) + _flat("b", 10, WEEKS[:6]) + _flat("b", 0, WEEKS[6:], in_stock=False)
    r = shares_from_obs(obs, WEEKS)
    assert r.shares == pytest.approx({"a": 0.5, "b": 0.5})


def test_missing_weeks_are_observed_zero():
    r = shares_from_obs(_flat("a", 10) + _flat("b", 10, WEEKS[-1:]), WEEKS)
    assert r.shares["b"] < 0.2


def test_unassigned_is_held_back():
    r = shares_from_obs(_flat("a", 9) + _flat(None, 1), WEEKS)
    assert r.unassigned == pytest.approx(0.1)
    assert sum(r.shares.values()) == pytest.approx(0.9)


def test_blend_no_history_uses_category_prior():
    cat = shares_from_obs(_flat("a", 1) + _flat("b", 3), WEEKS)
    r = blend_shares(None, cat)
    assert r.shares == pytest.approx({"a": 0.25, "b": 0.75})
    assert set(r.basis.values()) == {"category_prior"}


def test_blend_long_history_tracks_sku():
    sku = shares_from_obs(_flat("a", 100) + _flat("b", 100), WEEKS)
    cat = shares_from_obs(_flat("a", 1) + _flat("b", 9), WEEKS)
    r = blend_shares(sku, cat)
    lam = sku.evidence_weeks / (sku.evidence_weeks + 4)
    assert r.shares["a"] == pytest.approx(lam * 0.5 + (1 - lam) * 0.1)
    assert sum(r.shares.values()) == pytest.approx(1.0)


def test_split_preserves_p50_and_floors_p10():
    lp10, lp50, lp90 = split_week(2.0, 10.0, 18.0, 0.3)
    assert lp50 == pytest.approx(3.0)
    assert lp10 >= 0
    assert lp90 > lp50


def test_split_full_share_reproduces_symmetric_band():
    assert split_week(5.0, 10.0, 15.0, 1.0) == pytest.approx((5.0, 10.0, 15.0))


def test_split_small_share_is_relatively_wider():
    _, p50_s, p90_s = split_week(8.0, 10.0, 12.0, 0.1)
    assert (p90_s - p50_s) / p50_s > (12.0 - 10.0) / 10.0


@pytest.mark.parametrize("shares", [[0.5, 0.3, 0.2], [0.9, 0.05, 0.05], [1 / 3] * 3])
def test_location_p50_sums_to_sku_p50(shares):
    assert sum(split_week(4, 10, 16, s)[1] for s in shares) == pytest.approx(10.0)


def test_half_life_constant():
    assert HALF_LIFE_WEEKS == 4.0


def test_all_unassigned_sku_demand_is_not_spread_by_category():
    sku = shares_from_obs(_flat(None, 10), WEEKS)
    cat = shares_from_obs(_flat("a", 10), WEEKS)
    result = blend_shares(sku, cat)
    assert result.unassigned == 1.0
    assert sum(result.shares.values()) == 0.0
