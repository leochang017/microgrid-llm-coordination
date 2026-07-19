"""Tests for coordination strategies."""

from datetime import datetime

import pytest

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


def test_round_robin_does_not_crash_on_zero_battery_household() -> None:
    """C2-4: soc_kwh / battery_kwh has no zero-guard. A degenerate
    battery_kwh=0 household must not crash the islanded round_robin path —
    treat it as fraction 0.0 (neutral / never a net sender)."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    households = {hid: make_household(hid) for hid in n.comm_graph}
    households["r0c0"] = Household(
        id="r0c0",
        pv_kw_peak=8.0,
        battery_kwh=0.0,
        battery_max_rate_kw=5.0,
        rt_efficiency=0.9,
        dod_floor_frac=0.1,
        grid_max_kw=10.0,
        profile=HouseholdProfile(description="test"),
    )
    states = {hid: make_state(soc=5.0) for hid in n.comm_graph}
    states["r0c0"] = make_state(soc=0.0)
    solar = {hid: 0.0 for hid in n.comm_graph}
    load = {hid: 1.0 for hid in n.comm_graph}
    grid = {hid: False for hid in n.comm_graph}
    transfers = round_robin(
        datetime(2024, 7, 1, 12, 0), states, households, solar, load, grid, n, 0.25
    )
    assert not any(t.from_id == "r0c0" for t in transfers)


def test_round_robin_overlay_does_not_crash_on_zero_battery_household() -> None:
    from sim.strategies import round_robin_overlay

    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    households = {hid: make_household(hid) for hid in n.comm_graph}
    households["r0c0"] = Household(
        id="r0c0",
        pv_kw_peak=8.0,
        battery_kwh=0.0,
        battery_max_rate_kw=5.0,
        rt_efficiency=0.9,
        dod_floor_frac=0.1,
        grid_max_kw=10.0,
        profile=HouseholdProfile(description="test"),
    )
    states = {hid: make_state(soc=5.0) for hid in n.comm_graph}
    states["r0c0"] = make_state(soc=0.0)
    solar = {hid: 0.0 for hid in n.comm_graph}
    load = {hid: 1.0 for hid in n.comm_graph}
    grid = {hid: False for hid in n.comm_graph}
    transfers = round_robin_overlay.decide_transfers(
        datetime(2024, 7, 1, 12, 0), states, households, solar, load, grid, n, 0.25
    )
    assert not any(t.from_id == "r0c0" for t in transfers)


def test_overlay_shares_across_owner_edge_that_geographic_lacks() -> None:
    from sim.network import Neighborhood
    from sim.strategies import round_robin_overlay

    def _h(hid: str, batt: float) -> Household:
        return Household(
            id=hid,
            pv_kw_peak=5.0,
            battery_kwh=batt,
            battery_max_rate_kw=5.0,
            rt_efficiency=1.0,
            dod_floor_frac=0.0,
            grid_max_kw=10.0,
            profile=HouseholdProfile(description=hid),
        )

    n = Neighborhood(
        comm_graph={"a": [], "b": []},
        edges_by_type={"geographic": {"a": [], "b": []}, "owner": {"a": ["b"], "b": ["a"]}},
        bus_max_kw=50.0,
        bus_loss_factor=0.0,
    )
    households = {"a": _h("a", 10.0), "b": _h("b", 10.0)}
    states = {
        "a": HouseholdState(soc_kwh=10.0, last_solar_kw=0, last_load_kw=0, grid_connected=False),
        "b": HouseholdState(soc_kwh=2.0, last_solar_kw=0, last_load_kw=0, grid_connected=False),
    }
    grid = {"a": False, "b": False}
    transfers = round_robin_overlay.decide_transfers(
        datetime(2018, 1, 1),
        states,
        households,
        {"a": 0.0, "b": 0.0},
        {"a": 0.0, "b": 0.0},
        grid,
        n,
        0.25,
    )
    assert any(t.from_id == "a" and t.to_id == "b" for t in transfers)


def test_round_robin_exact_share_math() -> None:
    """Numeric pin for the paper's reference baseline (2026-07-06): with soc
    13.0, floor 1.35, dt 0.25 and two below-mean neighbors, r0c0 sends exactly
    (13.0 - 1.35) * 0.05 / 0.25 / 2 = 1.165 kW to each. Previously the only
    assertion was existence, so a silent SHARE_FRACTION or targeting change
    would have moved every headline number while the suite stayed green."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    households = {hid: make_household(hid) for hid in n.comm_graph}
    states = {hid: make_state(soc=5.0) for hid in n.comm_graph}
    states["r0c0"] = make_state(soc=13.0)
    states["r0c1"] = make_state(soc=2.0)
    solar = {hid: 0.0 for hid in n.comm_graph}
    load = {hid: 1.0 for hid in n.comm_graph}
    grid = {hid: False for hid in n.comm_graph}
    transfers = round_robin(
        datetime(2024, 7, 1, 12, 0), states, households, solar, load, grid, n, 0.25
    )
    # Only r0c0 is above the mean SoC fraction; its below-mean neighbors are
    # r0c1 (0.148) and r1c0 (0.370 < mean 0.3827) — the 5% share splits in two.
    assert len(transfers) == 2
    assert all(t.from_id == "r0c0" for t in transfers)
    assert {t.to_id for t in transfers} == {"r0c1", "r1c0"}
    for t in transfers:
        assert t.kw == pytest.approx((13.0 - 1.35) * 0.05 / 0.25 / 2, abs=1e-12)


def test_round_robin_above_mean_houses_receive_nothing() -> None:
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    households = {hid: make_household(hid) for hid in n.comm_graph}
    states = {hid: make_state(soc=5.0) for hid in n.comm_graph}
    states["r0c0"] = make_state(soc=13.0)
    states["r2c2"] = make_state(soc=12.0)  # also above mean
    solar = {hid: 0.0 for hid in n.comm_graph}
    load = {hid: 1.0 for hid in n.comm_graph}
    grid = {hid: False for hid in n.comm_graph}
    transfers = round_robin(
        datetime(2024, 7, 1, 12, 0), states, households, solar, load, grid, n, 0.25
    )
    senders = {"r0c0", "r2c2"}
    assert all(t.to_id not in senders for t in transfers)


def test_round_robin_empty_when_nobody_islanded() -> None:
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    households = {hid: make_household(hid) for hid in n.comm_graph}
    states = {hid: make_state(soc=5.0, grid=True) for hid in n.comm_graph}
    states["r0c0"] = make_state(soc=13.0, grid=True)
    solar = {hid: 0.0 for hid in n.comm_graph}
    load = {hid: 1.0 for hid in n.comm_graph}
    grid = {hid: True for hid in n.comm_graph}
    transfers = round_robin(
        datetime(2024, 7, 1, 12, 0), states, households, solar, load, grid, n, 0.25
    )
    assert transfers == []


def test_overlay_exact_share_math_across_owner_edge() -> None:
    """round_robin_overlay must use the SAME share formula as round_robin
    (10.0 soc, floor 0, one target: 10 * 0.05 / 0.25 = 2.0 kW) — any silent
    divergence would make the overlay-vs-geographic comparison meaningless."""
    from sim.network import Neighborhood
    from sim.strategies import round_robin_overlay

    def _h(hid: str) -> Household:
        return Household(
            id=hid,
            pv_kw_peak=5.0,
            battery_kwh=10.0,
            battery_max_rate_kw=5.0,
            rt_efficiency=1.0,
            dod_floor_frac=0.0,
            grid_max_kw=10.0,
            profile=HouseholdProfile(description=hid),
        )

    n = Neighborhood(
        comm_graph={"a": [], "b": []},
        edges_by_type={"geographic": {"a": [], "b": []}, "owner": {"a": ["b"], "b": ["a"]}},
        bus_max_kw=50.0,
        bus_loss_factor=0.0,
    )
    households = {"a": _h("a"), "b": _h("b")}
    states = {
        "a": HouseholdState(soc_kwh=10.0, last_solar_kw=0, last_load_kw=0, grid_connected=False),
        "b": HouseholdState(soc_kwh=2.0, last_solar_kw=0, last_load_kw=0, grid_connected=False),
    }
    transfers = round_robin_overlay.decide_transfers(
        datetime(2018, 1, 1),
        states,
        households,
        {"a": 0.0, "b": 0.0},
        {"a": 0.0, "b": 0.0},
        {"a": False, "b": False},
        n,
        0.25,
    )
    assert len(transfers) == 1
    assert transfers[0].from_id == "a" and transfers[0].to_id == "b"
    assert transfers[0].kw == pytest.approx(10.0 * 0.05 / 0.25, abs=1e-12)
