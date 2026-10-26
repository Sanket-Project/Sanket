"""Store↔store transfers (location spec §6). Pure.

Only when the DC cannot fix a shortage in time: the receiver runs out before its
next DC delivery and a faster store-to-store move exists. Donors keep their own
p90 demand for the window, are fresh, and receive nothing this cycle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TransferSite:
    location: str
    position: float
    window_p50: float
    window_p90: float
    daily_rate: float
    lead_from_parent: int | None
    fresh: bool
    allocated: int = 0


@dataclass(frozen=True, slots=True)
class Transfer:
    source: str
    destination: str
    units: int
    deficit: float
    excess: float


def match_transfers(
    sites: list[TransferSite], *, transfer_lead_days: int, moq: int = 1, min_units: int = 2
) -> list[Transfer]:
    moq = max(1, int(moq))
    receivers: list[tuple[float, TransferSite, float]] = []
    for s in sites:
        if not s.fresh or s.lead_from_parent is None or s.daily_rate <= 0:
            continue
        deficit = s.window_p50 - (s.position + s.allocated)
        cover = (s.position + s.allocated) / s.daily_rate
        if deficit > 0 and cover < s.lead_from_parent and transfer_lead_days < s.lead_from_parent:
            receivers.append((cover, s, deficit))
    receiver_ids = {s.location for _, s, _ in receivers}
    excess = {
        s.location: s.position - s.window_p90
        for s in sites
        if s.fresh and s.allocated == 0 and s.location not in receiver_ids
        and s.position - s.window_p90 > 0
    }

    out: list[Transfer] = []
    for _, r, deficit in sorted(receivers, key=lambda x: x[0]):
        for donor in sorted(excess, key=lambda k: excess[k], reverse=True):
            if deficit <= 0:
                break
            qty = int(math.floor(min(deficit, excess[donor]) / moq)) * moq
            if qty < max(1, min_units):
                continue
            out.append(Transfer(donor, r.location, qty, deficit, excess[donor]))
            excess[donor] -= qty
            deficit -= qty
    return out
