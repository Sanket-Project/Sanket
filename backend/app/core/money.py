"""Totals of money fields that respect currency: never add rupees to dollars."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any


def totals_by_currency(
    rows: Iterable[dict[str, Any]], fields: Iterable[str], *, currency_key: str = "currency"
) -> tuple[str | None, dict[str, float | None], dict[str, dict[str, float]]]:
    """Sum ``fields`` per currency across ``rows``.

    Returns ``(currency, totals, by_currency)``: with one currency, ``currency``
    names it and ``totals`` holds the sums; with several (or rows whose currency
    is unknown mixed with known ones) ``currency`` is ``None`` and every total
    is ``None`` — the per-currency sums are the only meaningful figures.
    """
    keys = list(fields)
    by: dict[str, dict[str, float]] = defaultdict(lambda: dict.fromkeys(keys, 0.0))
    for row in rows:
        code = row.get(currency_key) or "unknown"
        for k in keys:
            by[code][k] += float(row.get(k) or 0)
    by_currency = {c: {k: round(v, 2) for k, v in vals.items()} for c, vals in by.items()}
    if len(by_currency) == 1:
        (code, vals), = by_currency.items()
        return code, dict(vals), by_currency
    if not by_currency:
        return None, dict.fromkeys(keys, 0.0), {}
    return None, dict.fromkeys(keys), by_currency
