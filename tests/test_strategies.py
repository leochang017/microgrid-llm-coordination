"""Tests for coordination strategies."""

from datetime import datetime

from sim.household import Household, HouseholdState
from sim.network import build_grid_neighborhood
from sim.strategies.no_coordination import decide_transfers as no_coord
from sim.strategies.round_robin import decide_transfers as round_robin
from sim.types import HouseholdProfile


def make_state(soc: float = 5.0, grid: bool = False) -> HouseholdState:
    return HouseholdState(soc_kwh=soc, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=grid)


def make_household(hid: str) -> Household:
    return Household(
        id=hid,
        pv_kw_peak=8.0,
        battery_kwh=13.5,
        battery_max_rate_kw=5.0,
        rt_efficiency=0.9,
        dod_floor_frac=0.1,
        grid_max_kw=10.0,
        profile=HouseholdProfile(description="test"),
    )


def test_no_coordination_returns_empty() -> None:
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    households = {hid: make_household(hid) for hid in n.comm_graph}
    states = {hid: make_state() for hid in n.comm_graph}
    solar = {hid: 4.0 for hid in n.comm_graph}
    load = {hid: 1.0 for hid in n.comm_graph}
    grid = {hid: False for hid in n.comm_graph}
    transfers = no_coord(
        datetime(2024, 7, 1, 12, 0), states, households, solar, load, grid, n, 0.25
    )
    assert transfers == []


def test_round_robin_moves_from_high_soc_to_low_soc_neighbor() -> None:
    """House with full battery and no load should send to a low-SoC spatial neighbor."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    households = {hid: make_household(hid) for hid in n.comm_graph}
    states = {hid: make_state(soc=5.0) for hid in n.comm_graph}
    # r0c0 nearly full, r0c1 nearly empty.
    states["r0c0"] = make_state(soc=13.0)
    states["r0c1"] = make_state(soc=2.0)
    solar = {hid: 0.0 for hid in n.comm_graph}
    load = {hid: 1.0 for hid in n.comm_graph}
    grid = {hid: False for hid in n.comm_graph}
    transfers = round_robin(
        datetime(2024, 7, 1, 12, 0), states, households, solar, load, grid, n, 0.25
    )
    # At least one transfer should originate at r0c0 and go to r0c1.
    assert any(t.from_id == "r0c0" and t.to_id == "r0c1" for t in transfers)
