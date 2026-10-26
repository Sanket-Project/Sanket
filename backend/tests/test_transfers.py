"""Store↔store transfers (spec §6). Pure."""
from __future__ import annotations

from hypothesis import given, strategies as st

from app.services.transfers import TransferSite, match_transfers


def site(loc, pos, p50, p90, rate, lead=5, fresh=True, allocated=0):
    return TransferSite(loc, pos, p50, p90, rate, lead, fresh, allocated)


def test_moves_excess_to_a_store_running_out():
    sites = [site("r", 2, 20, 30, 2.0), site("d", 60, 10, 15, 1.0)]
    [t] = match_transfers(sites, transfer_lead_days=2)
    assert (t.source, t.destination, t.units) == ("d", "r", 18)


def test_donor_keeps_its_p90():
    sites = [site("r", 0, 100, 120, 10.0), site("d", 40, 10, 30, 1.0)]
    [t] = match_transfers(sites, transfer_lead_days=2)
    assert t.units == 10                       # 40 − 30


def test_no_transfer_when_dc_delivery_is_as_fast():
    sites = [site("r", 2, 20, 30, 2.0, lead=2), site("d", 60, 10, 15, 1.0)]
    assert match_transfers(sites, transfer_lead_days=2) == []


def test_no_transfer_when_receiver_cover_outlasts_dc_lead_time():
    sites = [site("r", 15, 20, 30, 2.0, lead=5), site("d", 60, 10, 15, 1.0)]   # 7.5 days ≥ 5
    assert match_transfers(sites, transfer_lead_days=2) == []


def test_stale_and_allocated_donors_excluded():
    sites = [site("r", 0, 20, 30, 2.0), site("d1", 60, 10, 15, 1.0, fresh=False),
             site("d2", 60, 10, 15, 1.0, allocated=5)]
    assert match_transfers(sites, transfer_lead_days=2) == []


def test_min_units():
    sites = [site("r", 19, 20, 30, 2.0, lead=20), site("d", 60, 10, 15, 1.0)]
    assert match_transfers(sites, transfer_lead_days=2, min_units=2) == []


def test_most_urgent_receiver_served_first():
    sites = [site("r1", 5, 20, 30, 1.0), site("r2", 0, 20, 30, 1.0), site("d", 35, 10, 15, 1.0)]
    out = match_transfers(sites, transfer_lead_days=2)
    assert out[0].destination == "r2" and out[0].units == 20


@given(st.lists(st.tuples(st.floats(0, 100), st.floats(0, 60), st.floats(0, 40),
                          st.floats(0.1, 10), st.integers(0, 10)), min_size=2, max_size=7))
def test_invariants(raw):
    sites = [TransferSite(f"s{i}", p, a, a + b, r, l, True) for i, (p, a, b, r, l) in enumerate(raw)]
    out = match_transfers(sites, transfer_lead_days=1)
    given_by = {}
    for t in out:
        given_by[t.source] = given_by.get(t.source, 0) + t.units
    by_loc = {s.location: s for s in sites}
    for src, units in given_by.items():
        assert by_loc[src].position - units >= by_loc[src].window_p90 - 1e-9
    assert not ({t.source for t in out} & {t.destination for t in out})
