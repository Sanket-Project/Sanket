"""The one weekly calendar SANKET forecasts in: weeks start Monday 00:00 UTC.

Sales are bucketed with ``date_trunc('week', sale_time AT TIME ZONE 'UTC')``,
forecast dates are those same Mondays, and accuracy compares a forecast for a
week with the sales of ``[Monday, next Monday)``. Writing the time zone out —
rather than inheriting the database session's — is what keeps the three in step.

A sale timestamped 00:00–05:30 IST on a Monday is still Sunday in UTC and so
belongs to the previous week; a per-workspace planning time zone is a
documented follow-up, not something to approximate here.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

CALENDAR = "W-MON-UTC"


def week_start(day: date | datetime) -> date:
    """The Monday of the UTC week containing ``day``."""
    if isinstance(day, datetime):
        day = (day.astimezone(UTC) if day.tzinfo else day).date()
    return day - timedelta(days=day.weekday())


def current_week_start(now: datetime | None = None) -> date:
    """Monday of the current UTC week — the first instant *not* yet complete."""
    return week_start(now or datetime.now(UTC))


def period_start(freq: str, now: datetime | None = None) -> date:
    """Start of the current, still-incomplete period for ``freq`` (D, W or M)."""
    today = (now or datetime.now(UTC)).astimezone(UTC).date()
    if freq == "W":
        return week_start(today)
    if freq == "M":
        return today.replace(day=1)
    return today
