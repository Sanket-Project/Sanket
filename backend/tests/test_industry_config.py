"""Unit tests for the effective per-tenant industry config resolver + focus filter.

Pure / in-memory: no DB. The resolver is exercised with a stub async session that
returns an in-memory IndustryProfile, and an in-memory signal stand-in is used for
the focus watchlist filter.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from app.models.enums import IndustryCode, SignalType
from app.models.industry import IndustryProfile
from app.services.industry_config import (
    FocusProfile,
    filter_signals_by_focus,
    merge_focus_into_flags,
    resolve_effective_config,
)
from app.services.industry_context import AGROCENTER


@dataclass
class _Sig:
    series_key: str | None = None
    category_tags: list[str] | None = None
    sku_tags: list[str] | None = None


class _StubSession:
    """Minimal async session: scalar() returns a preset profile (or None)."""

    def __init__(self, profile: IndustryProfile | None) -> None:
        self._profile = profile

    async def scalar(self, _statement: object) -> IndustryProfile | None:
        return self._profile


# ── FocusProfile ─────────────────────────────────────────────────────────────


def test_focus_from_raw_normalizes_and_trims() -> None:
    focus = FocusProfile.from_raw({"keywords": ["  Rice ", "PADDY", ""], "categories": ["Grain"]})
    assert focus.keywords == ("rice", "paddy")
    assert focus.categories == ("grain",)
    assert focus.is_empty is False


def test_focus_from_raw_empty() -> None:
    assert FocusProfile.from_raw(None).is_empty
    assert FocusProfile.from_raw({}).is_empty


# ── filter_signals_by_focus ──────────────────────────────────────────────────


def test_filter_empty_focus_keeps_all() -> None:
    sigs = [_Sig(series_key="fertilizer_demand"), _Sig(series_key="rice_price")]
    assert filter_signals_by_focus(sigs, FocusProfile()) == sigs


def test_filter_keyword_substring_on_series_key() -> None:
    focus = FocusProfile(keywords=("rice", "paddy"))
    sigs = [
        _Sig(series_key="rice_price_msp"),
        _Sig(series_key="paddy_arrivals"),
        _Sig(series_key="urea_fertilizer_demand"),
    ]
    kept = filter_signals_by_focus(sigs, focus)
    assert [s.series_key for s in kept] == ["rice_price_msp", "paddy_arrivals"]


def test_filter_matches_category_tags() -> None:
    focus = FocusProfile(categories=("grain",))
    sigs = [_Sig(series_key="x", category_tags=["Grain"]), _Sig(series_key="y", category_tags=["seed"])]
    kept = filter_signals_by_focus(sigs, focus)
    assert len(kept) == 1
    assert kept[0].series_key == "x"


def test_filter_no_match_falls_back_to_all() -> None:
    # A rice-mill watchlist against only fertilizer signals must not zero out fusion.
    focus = FocusProfile(keywords=("rice",))
    sigs = [_Sig(series_key="fertilizer_demand"), _Sig(series_key="seed_sales")]
    assert filter_signals_by_focus(sigs, focus) == sigs


# ── merge_focus_into_flags ───────────────────────────────────────────────────


def test_merge_focus_preserves_other_flags() -> None:
    existing = {"gxp_mode": True, "shortage_alerts": True}
    merged = merge_focus_into_flags(existing, ["rice", "paddy"], ["grain"])
    assert merged["gxp_mode"] is True
    assert merged["shortage_alerts"] is True
    assert merged["focus"] == {"keywords": ["rice", "paddy"], "categories": ["grain"]}
    # returns a fresh dict, does not mutate the input
    assert "focus" not in existing


def test_merge_focus_overwrites_previous_focus() -> None:
    existing = {"focus": {"keywords": ["old"], "categories": []}}
    merged = merge_focus_into_flags(existing, ["new"], [])
    assert merged["focus"]["keywords"] == ["new"]


# ── resolve_effective_config ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_no_profile_uses_archetype_defaults() -> None:
    cfg = await resolve_effective_config(_StubSession(None), uuid.uuid4(), "agrocenter")
    assert cfg.effective_horizon == AGROCENTER.default_horizon_weeks
    assert cfg.active_signal_types == tuple(AGROCENTER.required_signal_types)
    assert cfg.focus.is_empty
    assert cfg.code == "agrocenter"


@pytest.mark.asyncio
async def test_resolve_applies_profile_overrides_and_focus() -> None:
    tenant_id = uuid.uuid4()
    profile = IndustryProfile(
        tenant_id=tenant_id,
        industry=IndustryCode.agrocenter,
        custom_horizon_weeks=40,
        custom_signal_types=[SignalType.competitor_price],
        model_overrides={"baseline": "Chronos"},
        feature_flags={"focus": {"keywords": ["rice", "paddy"], "categories": ["grain"]}},
    )
    cfg = await resolve_effective_config(_StubSession(profile), tenant_id, "agrocenter")

    assert cfg.effective_horizon == 40
    # union preserves archetype-required, then appends the tenant-custom one
    assert "competitor_price" in cfg.active_signal_types
    for required in AGROCENTER.required_signal_types:
        assert required in cfg.active_signal_types
    assert cfg.model_overrides == {"baseline": "Chronos"}
    assert cfg.focus.keywords == ("rice", "paddy")
    assert cfg.focus.categories == ("grain",)
