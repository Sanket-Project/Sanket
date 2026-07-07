"""Effective per-tenant industry configuration.

The hardcoded :mod:`app.services.industry_context` registry defines an *archetype*
(fashion, electronics, pharma, agrocenter, hardware) with sensible defaults. A
tenant narrows that archetype to its actual business via an
:class:`~app.models.industry.IndustryProfile` row:

* ``custom_horizon_weeks`` / ``custom_signal_types`` — override the archetype
  defaults.
* ``feature_flags["focus"]`` — a *focus watchlist* of keywords/categories that
  scopes which trend signals are considered relevant. This is what lets two
  tenants in the same archetype see different analysis: a rice mill
  (archetype=agrocenter) focuses on ``["rice", "paddy", "basmati"]`` while a
  farm-supply store focuses on ``["fertilizer", "seed", "pesticide"]``.

This module resolves the archetype + the tenant's overrides into one
:class:`EffectiveIndustryConfig` and provides the pure helpers that consume it.
Keeping it framework-agnostic (it only needs an async session) means both the
HTTP layer and the arq worker can call it.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import structlog

from app.models.enums import IndustryCode
from app.models.industry import IndustryProfile
from app.services.industry_context import IndustryContext, get_industry_context

log = structlog.get_logger(__name__)


class _AsyncSession(Protocol):
    async def scalar(self, statement: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class FocusProfile:
    """A tenant's narrowed area of interest within its industry archetype.

    ``keywords`` are matched as case-insensitive substrings against a signal's
    ``series_key`` and its category/sku tags. ``categories`` are matched exactly
    (case-insensitive) against a signal's ``category_tags``. All values are
    normalized to lowercase on construction.
    """

    keywords: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.keywords and not self.categories

    @classmethod
    def from_raw(cls, raw: dict | None) -> FocusProfile:
        if not raw:
            return cls()
        kw = raw.get("keywords") or []
        cats = raw.get("categories") or []
        return cls(
            keywords=tuple(_norm(k) for k in kw if _norm(k)),
            categories=tuple(_norm(c) for c in cats if _norm(c)),
        )


@dataclass(frozen=True, slots=True)
class EffectiveIndustryConfig:
    """The archetype defaults merged with a tenant's profile overrides."""

    base: IndustryContext
    effective_horizon: int
    active_signal_types: tuple[str, ...]
    model_overrides: dict[str, Any]
    feature_flags: dict[str, Any]
    focus: FocusProfile

    @property
    def code(self) -> str:
        return self.base.code


def _norm(value: Any) -> str:
    return str(value).strip().lower()


async def resolve_effective_config(
    session: _AsyncSession,
    tenant_id: uuid.UUID,
    industry_code: str,
) -> EffectiveIndustryConfig:
    """Merge the archetype registry with the tenant's IndustryProfile (if any).

    Falls back to pure archetype defaults when the tenant has no profile row, so
    new tenants still get sensible behavior before they complete onboarding.
    """
    from sqlalchemy import select

    base = get_industry_context(industry_code)
    profile = await session.scalar(
        select(IndustryProfile).where(
            IndustryProfile.tenant_id == tenant_id,
            IndustryProfile.industry == IndustryCode(industry_code),
        )
    )

    if profile is None:
        return EffectiveIndustryConfig(
            base=base,
            effective_horizon=base.default_horizon_weeks,
            active_signal_types=tuple(base.required_signal_types),
            model_overrides={},
            feature_flags={},
            focus=FocusProfile(),
        )

    flags = profile.feature_flags or {}
    # union (order-preserving) of archetype-required + tenant-custom signal types
    active = tuple(
        dict.fromkeys([*base.required_signal_types, *(profile.custom_signal_types or [])])
    )
    return EffectiveIndustryConfig(
        base=base,
        effective_horizon=base.effective_horizon(profile.custom_horizon_weeks),
        active_signal_types=active,
        model_overrides=profile.model_overrides or {},
        feature_flags=flags,
        focus=FocusProfile.from_raw(flags.get("focus")),
    )


def merge_focus_into_flags(
    flags: dict[str, Any] | None,
    keywords: Iterable[Any],
    categories: Iterable[Any],
) -> dict[str, Any]:
    """Return a new feature_flags dict with ``focus`` set, preserving other keys.

    Returns a fresh dict (not a mutation) so SQLAlchemy reliably detects the
    JSONB change when it's reassigned onto the ORM column.
    """
    out = dict(flags or {})
    out["focus"] = {"keywords": list(keywords), "categories": list(categories)}
    return out


def _signal_matches_focus(
    focus: FocusProfile,
    series_key: str | None,
    category_tags: Iterable[Any] | None,
    sku_tags: Iterable[Any] | None,
) -> bool:
    """True if a signal is relevant to the focus watchlist (empty focus → all)."""
    if focus.is_empty:
        return True

    cats = {_norm(t) for t in (category_tags or [])}
    if any(cat in cats for cat in focus.categories):
        return True

    tokens = [_norm(series_key)] if series_key else []
    tokens.extend(cats)
    tokens.extend(_norm(t) for t in (sku_tags or []))
    blob = " ".join(tokens)
    return any(kw in blob for kw in focus.keywords)


def filter_signals_by_focus(signals: Sequence[Any], focus: FocusProfile) -> list[Any]:
    """Keep only signals relevant to the tenant's focus watchlist.

    Operates on any object exposing ``series_key``, ``category_tags`` and
    ``sku_tags`` (e.g. the ``TrendSignal`` ORM model). If the watchlist filters
    everything out, returns the original list unchanged — fusing generic industry
    signals is better than fusing none, and keeps the platform demoable for a
    freshly-onboarded tenant whose keywords don't match current data.
    """
    if focus.is_empty:
        return list(signals)
    kept = [
        s
        for s in signals
        if _signal_matches_focus(
            focus,
            getattr(s, "series_key", None),
            getattr(s, "category_tags", None),
            getattr(s, "sku_tags", None),
        )
    ]
    if not kept:
        log.info("industry_focus.filter_empty_fallback", keywords=list(focus.keywords))
        return list(signals)
    return kept
