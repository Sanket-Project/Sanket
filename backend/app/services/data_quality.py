"""Data quality checker — validates signals and sales rows at write time."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class DataQualityChecker:
    """Validates signal samples and sales rows, returning human-readable issue strings."""

    def check_signal(self, s: Any) -> list[str]:
        """
        s: a SignalSample or dict-like object.
        Returns list of issue strings (empty = clean).
        """
        issues: list[str] = []
        score = getattr(s, "normalized_score", None)
        if score is not None and not (-1.0 <= float(score) <= 1.0):
            issues.append(f"normalized_score {score} outside [-1, 1]")

        confidence = getattr(s, "confidence", None)
        if confidence is not None and not (0.0 <= float(confidence) <= 1.0):
            issues.append(f"confidence {confidence} outside [0, 1]")

        captured_at = getattr(s, "captured_at", None)
        if captured_at is not None:
            now = datetime.now(UTC)
            if hasattr(captured_at, "tzinfo") and captured_at > now:
                issues.append(f"captured_at {captured_at} is in the future")

        raw_value = getattr(s, "raw_value", None)
        if raw_value is not None:
            try:
                v = float(raw_value)
                if v != v:  # NaN check
                    issues.append("raw_value is NaN")
            except (TypeError, ValueError):
                issues.append(f"raw_value {raw_value!r} is not numeric")

        series_key = getattr(s, "series_key", None)
        if not series_key:
            issues.append("series_key is empty")

        return issues

    def check_sale(self, sale: dict[str, Any]) -> list[str]:
        issues: list[str] = []

        units = sale.get("units_sold")
        if units is not None and int(units) < 0:
            issues.append(f"units_sold {units} is negative")

        revenue = sale.get("gross_revenue")
        if revenue is not None and float(revenue) < 0:
            issues.append(f"gross_revenue {revenue} is negative")

        markdown = sale.get("markdown_pct")
        if markdown is not None and float(markdown) > 1.0:
            issues.append(f"markdown_pct {markdown} > 1.0 (should be 0-1 fraction)")

        sale_time = sale.get("sale_time")
        if sale_time is not None:
            now = datetime.now(UTC)
            if hasattr(sale_time, "tzinfo") and sale_time > now:
                issues.append(f"sale_time {sale_time} is in the future")

        return issues

    def is_critical(self, issues: list[str]) -> bool:
        """Returns True if any issue should block the row from being inserted."""
        critical_keywords = ["is in the future", "is negative"]
        return any(any(kw in i for kw in critical_keywords) for i in issues)
