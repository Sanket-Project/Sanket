"""Self-owned communication preferences and timezone-aware weekly scheduling."""

from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Literal["en", "hi", "te", "ta"] = "en"
    weekly_enabled: StrictBool = False
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    send_hour: int = Field(default=8, ge=0, le=23)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Choose a valid IANA timezone") from None
        return value


def next_delivery(now: datetime, timezone: str, hour: int) -> datetime:
    local = now.astimezone(ZoneInfo(timezone))
    target = (local + timedelta(days=(7 - local.weekday()) % 7)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    if target <= local:
        target += timedelta(days=7)
    return target.astimezone(UTC)


def delivery_key(due: datetime, timezone: str) -> str:
    local = due.astimezone(ZoneInfo(timezone))
    return (local.date() - timedelta(days=local.weekday())).isoformat()
