"""Allocation (DC→store) and transfer (store↔store) decisions (location spec §5–§6).

Inputs are the run's location forecasts, current stock per location and the
confirmed network. Nothing is assumed: an unready network, a stale stock row or
a location without a forecast produces a note or a skipped entry, not a number.
"""

from __future__ import annotations

import uuid
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.models.enums import DecisionKind, LocationKind
from app.models.forecast import ForecastRun
from app.models.inventory import InventoryLevel
from app.models.product import Sku
from app.models.location import LocationForecastResult
from app.models.sales import HistoricalSale
from app.services.allocation import StoreNeed, allocate, cover_level
from app.services.decision_engine import (
    Decision, DemandBand, PolicyConfig, Reason, _money, _pooled_sigma, _window_sum, _z_for,
)
from app.services.location_forecast import location_bands
from app.services.locations import load_locations, network_readiness
from app.services.planning_inputs import stock_is_stale
from app.services.transfers import TransferSite, match_transfers


@dataclass
class NetworkBuild:
    decisions: list[Decision] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _position(rows: list[InventoryLevel]) -> float:
    return sum(float(r.available_units) + max(0.0, float(r.inbound_units or 0)) for r in rows)


def _target(band: DemandBand, days: float, z: float) -> float:
    return _window_sum(band.p50, days) + z * _pooled_sigma(band, days)


async def _baseline_units(session, tenant_id, industry, review_days, now):
    code = func.lower(func.btrim(HistoricalSale.location))
    rows = (await session.execute(
        select(HistoricalSale.sku_id, code, func.sum(HistoricalSale.units_sold))
        .where(HistoricalSale.tenant_id == tenant_id, HistoricalSale.industry == industry,
               HistoricalSale.sale_time >= now - timedelta(days=review_days),
               HistoricalSale.sale_time < now)
        .group_by(HistoricalSale.sku_id, code)
    )).all()
    return {(sid, loc): float(units) for sid, loc, units in rows}


async def build_network_decisions(
    session: AsyncSession, *, tenant_id: uuid.UUID, industry: str, run: ForecastRun,
    skus: dict[uuid.UUID, Sku], levels: dict[uuid.UUID, list[InventoryLevel]],
    confidence: dict[uuid.UUID, tuple[int, str]], policy: PolicyConfig, now: datetime,
    include_transfers: bool = True,
) -> NetworkBuild:
    out = NetworkBuild()
    locs = [l for l in await load_locations(session, tenant_id) if l.is_active]
    if not locs:
        return out
    ready = network_readiness(locs)
    if not ready.allocation_ready:
        out.notes = list(ready.missing)  # once per refresh, not per SKU
    if (run.metrics or {}).get("location_degraded"):
        out.skipped = [{"sku_code": s.sku_code,
                        "reason": "Location forecast is degraded: sales have unassigned locations"}
                       for s in skus.values()]
        return out
    by_code = {l.code: l for l in locs}
    bands = await location_bands(session, tenant_id, run.id, now)
    shares = {(sid, lid): float(share) for sid, lid, share in (await session.execute(
        select(LocationForecastResult.sku_id, LocationForecastResult.location_id,
               func.min(LocationForecastResult.share))
        .where(LocationForecastResult.tenant_id == tenant_id, LocationForecastResult.run_id == run.id)
        .group_by(LocationForecastResult.sku_id, LocationForecastResult.location_id)
    )).all()}
    z = _z_for(policy.service_level)
    baseline = await _baseline_units(session, tenant_id, industry, policy.review_period_days, now)

    for sku_id, sku in skus.items():
        rows_by_code: dict[str, list[InventoryLevel]] = {}
        for lvl in levels.get(sku_id, []):
            code = (lvl.location or "").strip().lower()
            if code in by_code:
                rows_by_code.setdefault(code, []).append(lvl)
        conf, band_label = confidence.get(sku_id, (0, "insufficient"))
        allocated: dict[str, int] = {}

        if ready.allocation_ready:
            for dc in (l for l in locs if l.kind == LocationKind.warehouse):
                dc_rows = rows_by_code.get(dc.code, [])
                if not dc_rows or any(stock_is_stale(r.as_of, now) for r in dc_rows):
                    out.skipped.append({"sku_code": sku.sku_code,
                                        "reason": f"Stock at {dc.name} is missing or stale"})
                    continue
                dc_band = bands.get((sku_id, dc.id))
                dc_own = _window_sum(dc_band.p50, policy.review_period_days) if dc_band else 0.0
                supply = max(0.0, sum(float(r.available_units) for r in dc_rows) - dc_own)

                needs: list[StoreNeed] = []
                meta: dict[str, tuple] = {}
                for st in (l for l in locs if l.kind == LocationKind.store
                           and l.parent_location_id == dc.id):
                    rows = rows_by_code.get(st.code, [])
                    band = bands.get((sku_id, st.id))
                    if band is None:
                        out.skipped.append({"sku_code": sku.sku_code,
                                            "reason": f"No location forecast for {st.name}"})
                        continue
                    if not rows or any(stock_is_stale(r.as_of, now) for r in rows):
                        out.skipped.append({"sku_code": sku.sku_code,
                                            "reason": f"Stock at {st.name} is missing or stale"})
                        continue
                    days = float((st.lead_time_days_from_parent or 0) + policy.review_period_days)
                    pos = _position(rows)
                    tgt = _target(band, days, z)
                    rate = _window_sum(band.p50, days) / days if days > 0 else 0.0
                    needs.append(StoreNeed(st.code, pos, tgt, rate))
                    meta[st.code] = (st, days, pos, tgt, rate, band)

                alloc = allocate(needs, supply, moq=int(sku.moq or 1),
                                 min_units=policy.min_allocation_units)
                allocated.update(alloc)
                level = cover_level(needs, supply)
                baseline_total = sum(baseline.get((sku_id, st.code), 0.0) for st in locs
                                     if st.kind == LocationKind.store and st.parent_location_id == dc.id)
                baseline_scale = min(1.0, supply / baseline_total) if baseline_total > 0 else 0.0
                for code, units in alloc.items():
                    st, days, pos, tgt, rate, band = meta[code]
                    cover_after = (pos + units) / rate if rate > 0 else None
                    out.decisions.append(Decision(
                        kind=DecisionKind.allocation, sku_id=str(sku_id), sku_code=sku.sku_code,
                        headline=f"Send {units} × {sku.sku_code} from {dc.name} to {st.name}",
                        recommended_units=units,
                        baseline_units=math.floor(baseline.get((sku_id, code), 0.0) * baseline_scale),
                        urgency="high" if rate > 0 and pos / rate < days else "normal",
                        confidence=conf, confidence_band=band_label,
                        reasons=[Reason("store_target",
                                        f"{st.name} needs {tgt:.0f} units for the next {days:.0f} "
                                        f"days and holds {pos:.0f}.", tgt - pos)],
                        economics={"currency": sku.currency or "INR",
                                   "stock_value_moved": _money(units * float(sku.unit_cost or 0),
                                                               sku.unit_cost is not None)},
                        inputs={"window_days": days, "position": pos, "target": tgt,
                                "daily_rate": rate, "dc_supply": supply,
                                "cover_after_days": cover_after, "share_method": "share_split_v1",
                                "cover_level_days": level,
                                "location_band": {"p10": band.p10, "p50": band.p50, "p90": band.p90},
                                "share": shares.get((sku_id, st.id)),
                                "unit_cost": float(sku.unit_cost) if sku.unit_cost is not None else None,
                                "unit_price": float(sku.unit_price) if sku.unit_price is not None else None},
                        location_id=str(st.id), source_location_id=str(dc.id),
                    ))
        if include_transfers and ready.transfers_ready:
            sites: list[TransferSite] = []
            for store in (l for l in locs if l.kind == LocationKind.store):
                band = bands.get((sku_id, store.id))
                rows = rows_by_code.get(store.code, [])
                if band is None:
                    continue
                days = float((store.lead_time_days_from_parent or 0) + policy.review_period_days)
                p50 = _window_sum(band.p50, days)
                sites.append(TransferSite(
                    store.code, _position(rows), p50, _window_sum(band.p90, days),
                    p50 / days if days > 0 else 0.0, store.lead_time_days_from_parent,
                    bool(rows) and not any(stock_is_stale(r.as_of, now) for r in rows),
                    allocated.get(store.code, 0),
                ))
            by_site = {s.location: s for s in sites}
            for transfer in match_transfers(sites, transfer_lead_days=policy.transfer_lead_time_days,
                                           moq=int(sku.moq or 1), min_units=policy.min_transfer_units):
                src, dest = by_code[transfer.source], by_code[transfer.destination]
                receiver = by_site[dest.code]
                donor = by_site[src.code]
                units = transfer.units
                margin_known = sku.unit_cost is not None and sku.unit_price is not None
                cost = policy.transfer_cost_per_unit
                net = (units * (float(sku.unit_price) - float(sku.unit_cost)) - units * cost
                       if margin_known and cost is not None else None)
                if net is not None and net <= 0:
                    out.skipped.append({"sku_code": sku.sku_code,
                        "reason": f"Transfer of {sku.sku_code} to {dest.code} not worth its cost"})
                    continue
                cover = (receiver.position + receiver.allocated) / receiver.daily_rate
                reasons = [Reason("receiver_runs_out",
                    f"{dest.code} runs out in {cover:.1f} days; the next warehouse delivery "
                    f"takes {receiver.lead_from_parent} days.", transfer.deficit)]
                if cost is None:
                    reasons.append(Reason("transfer_cost_unknown", "Transfer cost not known", None))
                if not margin_known:
                    reasons.append(Reason("transfer_margin_unknown", "Transfer margin not known", None))
                out.decisions.append(Decision(
                    kind=DecisionKind.transfer, sku_id=str(sku_id), sku_code=sku.sku_code,
                    headline=f"Move {units} × {sku.sku_code} from {src.code} to {dest.code}",
                    recommended_units=units, baseline_units=0, urgency="high",
                    confidence=conf, confidence_band=band_label, reasons=reasons,
                    economics={"currency": sku.currency or "INR", "net_value": net},
                    inputs={"deficit": transfer.deficit, "excess": transfer.excess,
                        "receiver_window_p50": receiver.window_p50, "donor_window_p90": donor.window_p90,
                        "receiver_position": receiver.position, "donor_position": donor.position,
                        "receiver_cover_days": cover, "receiver_allocated": receiver.allocated,
                        "transfer_lead_time_days": policy.transfer_lead_time_days,
                        "min_transfer_units": policy.min_transfer_units, "transfer_cost_per_unit": cost,
                        "unit_cost": float(sku.unit_cost) if sku.unit_cost is not None else None,
                        "unit_price": float(sku.unit_price) if sku.unit_price is not None else None},
                    location_id=str(dest.id), source_location_id=str(src.id),
                ))
    return out
