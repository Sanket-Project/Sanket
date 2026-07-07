from __future__ import annotations

from app.services.inventory import InventorySnapshot, resolve_on_hand


def _snap(on_hand, reserved=0.0, inbound=0.0):
    return InventorySnapshot(
        sku_id="S", on_hand_units=on_hand, inbound_units=inbound, reserved_units=reserved
    )


def test_override_wins_over_everything():
    units, source = resolve_on_hand(
        override_units=42.0, snapshot=_snap(999), safety_stock_units=100
    )
    assert (units, source) == (42.0, "override")


def test_override_zero_is_respected_not_treated_as_missing():
    # 0 is a valid explicit position and must not fall through to inventory.
    units, source = resolve_on_hand(
        override_units=0.0, snapshot=_snap(500), safety_stock_units=100
    )
    assert (units, source) == (0.0, "override")


def test_real_inventory_used_when_no_override():
    units, source = resolve_on_hand(
        override_units=None, snapshot=_snap(250), safety_stock_units=100
    )
    assert (units, source) == (250.0, "inventory")


def test_inventory_uses_available_not_gross_on_hand():
    # available = on_hand - reserved
    units, source = resolve_on_hand(
        override_units=None, snapshot=_snap(250, reserved=60), safety_stock_units=100
    )
    assert (units, source) == (190.0, "inventory")


def test_reserved_above_on_hand_floors_at_zero():
    units, source = resolve_on_hand(
        override_units=None, snapshot=_snap(50, reserved=80), safety_stock_units=100
    )
    assert (units, source) == (0.0, "inventory")


def test_fallback_when_no_data():
    units, source = resolve_on_hand(
        override_units=None, snapshot=None, safety_stock_units=100
    )
    assert (units, source) == (200.0, "fallback")


def test_fallback_negative_safety_stock_floors_at_zero():
    units, source = resolve_on_hand(
        override_units=None, snapshot=None, safety_stock_units=-5
    )
    assert (units, source) == (0.0, "fallback")


def test_snapshot_available_property():
    assert _snap(100, reserved=30).available_units == 70.0
    assert _snap(10, reserved=40).available_units == 0.0
