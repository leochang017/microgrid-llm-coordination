"""Tests for the centralized full-horizon LP optimal baseline."""

from datetime import datetime, timedelta

from sim.household import Household
from sim.network import build_overlay_neighborhood
from sim.scenario import OutageWindow, Scenario
from sim.strategies import lp_optimal
from sim.types import HouseholdProfile


class _Const:
    """Minimal constant profile implementing get_kw(t)."""

    def __init__(self, kw: float) -> None:
        self.kw = kw

    def get_kw(self, t: datetime) -> float:
        return self.kw


def _h(hid: str, battery_kwh: float, rate: float) -> Household:
    return Household(
        id=hid,
        pv_kw_peak=0.0,
        battery_kwh=battery_kwh,
        battery_max_rate_kw=rate,
        rt_efficiency=1.0,
        dod_floor_frac=0.0,
        grid_max_kw=0.0,
        profile=HouseholdProfile(description=hid),
    )


def test_lp_moves_energy_from_full_house_to_deficit_house() -> None:
    # 1x2 grid, both islanded for one 15-min tick. r0c0 has a charged battery and
    # no load; r0c1 has no battery and a 2 kW load it cannot meet alone. The LP
    # optimum is to discharge r0c0 and ship the energy across the bus to r0c1.
    start = datetime(2018, 1, 1)
    dt = 0.25
    sc = Scenario(
        scenario_id="lp_tiny",
        start=start,
        end=start + timedelta(hours=dt),
        dt_hours=dt,
        seed=1,
        rows=1,
        cols=2,
        bus_max_kw=50.0,
        bus_loss_factor=0.0,
        strategy="lp_optimal",
        data_source="synthetic",
        household_sampling={
            "pv_kw_peak": [0.0, 0.0],
            "battery_kwh": [10.0, 10.0],
            "rt_efficiency": 1.0,
            "dod_floor_frac": 0.0,
        },
        outages=(
            OutageWindow(
                start=start, end=start + timedelta(hours=dt), affected_houses=("r0c0", "r0c1")
            ),
        ),
    )
    households = {"r0c0": _h("r0c0", 10.0, 10.0), "r0c1": _h("r0c1", 0.0, 1.0)}
    solar = _Const(0.0)
    loads = {"r0c0": _Const(0.0), "r0c1": _Const(2.0)}
    nbhd = build_overlay_neighborhood(
        rows=1, cols=2, affiliations={}, bus_max_kw=50.0, bus_loss_factor=0.0
    )

    decide = lp_optimal.prepare(sc, households, solar, loads, nbhd)
    transfers = decide(start, {}, households, {}, {}, {}, nbhd, dt)

    assert transfers, "LP produced no transfers"
    assert all(t.from_id == "r0c0" and t.to_id == "r0c1" for t in transfers)
    assert sum(t.kw for t in transfers) > 1.5  # serving 2 kW load -> ~2 kW gross
