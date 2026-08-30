"""Shared cooldown for the unofficial Google Trends endpoint.

`GoogleTrendsConnector` and `RegionalDemandConnector` both talk to the same
pytrends endpoint, which throttles per source IP. Without coordination a single
throttled tick issues one doomed request per keyword (~25 across both
connectors), logs a warning for each, and repeats the whole sweep every pipeline
interval. The first 429 is enough information: this breaker records it, stops
the current sweep, and suppresses subsequent sweeps for a growing cooldown until
Google lets us back in.
"""

from __future__ import annotations

import random
import threading
import time

import structlog

log = structlog.get_logger(__name__)

# First throttle parks us for one pipeline interval; repeated throttling backs
# off exponentially so a long block costs a couple of probes per hour, not 100.
_BASE_COOLDOWN_S = 15 * 60
_MAX_COOLDOWN_S = 6 * 60 * 60


def is_rate_limited(exc: BaseException) -> bool:
    """True when *exc* looks like a Google Trends throttle rather than a bug."""
    text = str(exc).lower()
    return "429" in text or "too many requests" in text or "rate limit" in text


class _TrendsCooldown:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._blocked_until = 0.0
        self._consecutive = 0

    def seconds_remaining(self) -> float:
        """Seconds left before calls may resume; 0.0 when the endpoint is open."""
        with self._lock:
            return max(0.0, self._blocked_until - time.monotonic())

    def record_rate_limited(self, source: str) -> float:
        """Open (or extend) the cooldown after a throttled response."""
        with self._lock:
            self._consecutive += 1
            consecutive = self._consecutive
            backoff = min(
                _BASE_COOLDOWN_S * (2 ** (consecutive - 1)), _MAX_COOLDOWN_S
            )
            # Jitter so parallel connectors don't resume on the same second.
            backoff *= 1.0 + random.uniform(-0.1, 0.1)
            self._blocked_until = time.monotonic() + backoff
        log.warning(
            "google_trends.cooldown.opened",
            source=source,
            cooldown_s=round(backoff),
            consecutive=consecutive,
        )
        return backoff

    def record_success(self) -> None:
        """Close the cooldown after a sweep that actually returned data."""
        with self._lock:
            recovering = self._consecutive > 0
            self._consecutive = 0
            self._blocked_until = 0.0
        if recovering:
            log.info("google_trends.cooldown.cleared")


cooldown = _TrendsCooldown()
