"""DC→store allocation (spec §5.2). Pure."""
from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from app.services.allocation import StoreNeed, allocate


def test_surplus_ships_exact_needs():
    stores = [StoreNeed("a", 10, 30, 2.0), StoreNeed("b", 0, 12, 1.0)]
    assert allocate(stores, supply=100) == {"a": 20, "b": 12}


def test_shortage_equalises_cover():
    stores = [StoreNeed("a", 0, 100, 2.0), StoreNeed("b", 0, 100, 1.0)]
    out = allocate(stores, supply=30)
    assert out == {"a": 20, "b": 10}          # both reach 10 days of cover


def test_shortage_tops_up_the_lowest_first():
    stores = [StoreNeed("a", 20, 100, 1.0), StoreNeed("b", 0, 100, 1.0)]
    assert allocate(stores, supply=10) == {"b": 10}


def test_zero_rate_store_gets_nothing_in_shortage():
    stores = [StoreNeed("a", 0, 50, 1.0), StoreNeed("b", 0, 50, 0.0)]
    assert allocate(stores, supply=10) == {"a": 10}


def test_zero_rate_store_gets_nothing_in_surplus():
    assert allocate([StoreNeed("a", 0, 50, 0.0)], supply=100) == {}


def test_rounds_to_pack_without_exceeding_supply():
    stores = [StoreNeed("a", 0, 7, 1.0), StoreNeed("b", 0, 7, 1.0)]
    out = allocate(stores, supply=10, moq=4)
    assert sum(out.values()) <= 10
    assert all(v % 4 == 0 for v in out.values())


def test_min_units_drops_tiny_lines():
    stores = [StoreNeed("a", 0, 1, 1.0), StoreNeed("b", 0, 20, 1.0)]
    assert allocate(stores, supply=100, min_units=2) == {"b": 20}


def test_no_supply_no_allocation():
    assert allocate([StoreNeed("a", 0, 10, 1.0)], supply=0) == {}


@given(
    st.lists(st.tuples(st.floats(0, 200), st.floats(0, 400), st.floats(0, 20)), min_size=1, max_size=8),
    st.floats(0, 1000), st.integers(1, 12),
)
def test_never_exceeds_supply_or_need(raw, supply, moq):
    stores = [StoreNeed(f"s{i}", p, t, r) for i, (p, t, r) in enumerate(raw)]
    out = allocate(stores, supply=supply, moq=moq)
    assert sum(out.values()) <= int(supply)
    need = {s.location: s.need for s in stores}
    for loc, units in out.items():
        assert units % moq == 0
        assert units <= need[loc] + moq    # rounding to a pack may pass need by < 1 pack
