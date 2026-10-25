"""How much external-signal evidence stands behind a trend score.

A trend score of 0 can mean "signals agree demand is flat" or "there are no
signals at all"; a volatility of 0 can mean perfect agreement or an empty
input. The audit found the second reading of each shown as the first ("High
(100%) agreement" from zero samples). This module classifies the evidence so
the API and UI can say which it is:

* ``unavailable`` — no samples in the lookback window (and why, if ingestion
  failed on this server);
* ``insufficient`` — fewer than ``MIN_SAMPLES``;
* ``stale`` — the newest sample is older than ``STALE_AFTER_HOURS``;
* ``available`` — enough recent samples to report a score and its agreement.

Only ``available`` evidence supports an agreement figure.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

MIN_SAMPLES = 3
STALE_AFTER_HOURS = 48


def signal_evidence(
    *,
    captured_at: list[datetime],
    sources: list[str],
    industry: str,
    now: datetime,
    lookback_hours: int,
    last_run: dict | None,
) -> dict[str, Any]:
    count = len(captured_at)
    newest = max(captured_at) if captured_at else None
    ingest = None
    if last_run and isinstance(last_run.get("industries"), dict):
        per = last_run["industries"].get(industry)
        if per is not None:
            ingest = {"finished_at": last_run.get("finished_at"), **per}

    if count == 0:
        status = "unavailable"
        if ingest and ingest.get("error"):
            message = f"No signal samples: the last ingestion failed — {ingest['error']}"
        elif ingest is None:
            message = (
                f"No signal samples in the last {lookback_hours} hours, and this server has no "
                "record of a signal ingestion run."
            )
        else:
            message = f"No signal samples in the last {lookback_hours} hours."
    elif count < MIN_SAMPLES:
        status = "insufficient"
        message = f"Only {count} signal sample(s); at least {MIN_SAMPLES} are needed."
    elif newest is not None and now - newest > timedelta(hours=STALE_AFTER_HOURS):
        status = "stale"
        message = f"The newest signal sample is from {newest.isoformat()}; signals are stale."
    else:
        status = "available"
        message = f"{count} signal samples from {len(set(sources))} source(s)."

    return {
        "status": status,
        "sample_count": count,
        "source_count": len(set(sources)),
        "newest_sample_at": newest.isoformat() if newest else None,
        "lookback_hours": lookback_hours,
        "min_samples": MIN_SAMPLES,
        "stale_after_hours": STALE_AFTER_HOURS,
        "agreement_reportable": status == "available",
        "last_ingest": ingest,
        "message": message,
    }
