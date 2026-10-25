"""The weekly calendar every weekly number in SANKET uses: Monday 00:00 UTC.

Mirrors ``sanket_ml.data.calendar`` (the ML service buckets history the same
way). The time zone is written into every bucket expression so the database
session's ``TimeZone`` can never move a sale into a different week.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement

CALENDAR = "W-MON-UTC"
WEEK = timedelta(weeks=1)


def week_bucket(column: ColumnElement) -> ColumnElement:
    """``date_trunc('week', <timestamptz> AT TIME ZONE 'UTC')`` — a naive UTC Monday."""
    return func.date_trunc("week", func.timezone("UTC", column))


def week_start(day: date | datetime) -> date:
    """The Monday of the UTC week containing ``day``."""
    if isinstance(day, datetime):
        day = (day.astimezone(UTC) if day.tzinfo else day).date()
    return day - timedelta(days=day.weekday())


def week_start_instant(week: date) -> datetime:
    """00:00 UTC on ``week`` (expected to be a Monday)."""
    return datetime(week.year, week.month, week.day, tzinfo=UTC)


def current_week_start(now: datetime | None = None) -> date:
    return week_start(now or datetime.now(UTC))
