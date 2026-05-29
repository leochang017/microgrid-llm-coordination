"""Tests for the centralized full-horizon LP optimal baseline."""

import dataclasses
import importlib
from datetime import datetime, timedelta
from pathlib import Path

from sim.engine import run
from sim.household import Household
from sim.logging import JsonlLogger
from sim.network import build_overlay_neighborhood
from sim.scenario import OutageWindow, Scenario, load_scenario
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


def _run_strategy(strategy: str, tmp_path: Path) -> dict:
    sc = load_scenario("configs/scenarios/synthetic_lp_smoke.yaml")
    sc = dataclasses.replace(sc, strategy=strategy)
    mod = importlib.import_module(f"sim.strategies.{strategy}")
    prepare = getattr(mod, "prepare", None)
    decide = getattr(mod, "decide_transfers", None)
    logger = JsonlLogger(run_dir=str(tmp_path / strategy), scenario_id=sc.scenario_id)
    return run(sc, decide, logger, prepare=prepare)


def test_lp_dominates_all_other_strategies(tmp_path: Path) -> None:
    # The only guaranteed invariant is that the full-foresight, full-bus LP is an
    # upper bound on served load — it must be >= every heuristic. (Whether
    # round_robin beats no_coordination is empirical and scenario-dependent: lossy,
    # poorly-targeted sharing can be net-negative vs. hoarding. That is exactly why
    # the "gap closed" metric is measured *relative to* round_robin, and why the
    # stress scenarios in test_stress_scenarios exist.)
    served = {
        s: _run_strategy(s, tmp_path)["served_load_fraction"]
        for s in ("no_coordination", "round_robin", "round_robin_overlay", "lp_optimal")
    }
    for s in ("no_coordination", "round_robin", "round_robin_overlay"):
        assert served["lp_optimal"] >= served[s] - 1e-6, (s, served)


def test_lp_run_deterministic(tmp_path: Path) -> None:
    a = _run_strategy("lp_optimal", tmp_path / "a")
    b = _run_strategy("lp_optimal", tmp_path / "b")
    assert a == b
    sa = (tmp_path / "a" / "lp_optimal" / "state.jsonl").read_text()
    sb = (tmp_path / "b" / "lp_optimal" / "state.jsonl").read_text()
    assert sa == sb
