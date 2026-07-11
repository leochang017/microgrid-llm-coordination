"""Tests for the centralized full-horizon LP optimal baseline."""

import dataclasses
import importlib
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from sim.engine import _build_data, run, sample_households
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


def test_lp_feasible_with_surplus_solar_on_islanded_houses() -> None:
    """Excess islanded solar must be curtailable, not an infeasibility crash.

    Pre-Phase-2.9 the power balance was a strict equality with no curtailment
    slack: 12 kW of solar against ~8.5 kW of total system absorption (served 2
    + charge 4 + max bus burn 2.5) made the LP hard-crash with
    'RuntimeError: LP failed ... infeasible' — and the LP had never been solved
    on a scenario with nonzero PV. Post-fix, the curt variable absorbs the
    surplus exactly like the engine's wasted-energy accounting, and both loads
    are fully served.
    """
    start = datetime(2018, 7, 1, 12, 0)
    dt = 0.25
    sc = Scenario(
        scenario_id="lp_solar_rich",
        start=start,
        end=start + timedelta(hours=dt),
        dt_hours=dt,
        seed=1,
        rows=1,
        cols=2,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
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
    hh = {
        "r0c0": dataclasses.replace(_h("r0c0", 10.0, 2.0), pv_kw_peak=1.0),
        "r0c1": _h("r0c1", 10.0, 2.0),
    }
    solar = _Const(12.0)  # r0c0 sees 12 kW (pv_kw_peak=1), r0c1 sees 0
    loads = {"r0c0": _Const(1.0), "r0c1": _Const(1.0)}
    nbhd = build_overlay_neighborhood(
        rows=1, cols=2, affiliations={}, bus_max_kw=50.0, bus_loss_factor=0.05
    )
    metrics = lp_optimal.optimal_metrics(sc, hh, solar, loads, nbhd)
    assert metrics["served_load_fraction"] == 1.0


def test_lp_ceiling_regression_haves_havenots() -> None:
    """The showcase ceiling must not move when LP internals change.

    Pinned 2026-07-06 (pre- and post- curtailment-slack + send/recv bounds:
    verified identical). Update ONLY on an intentional physics/LP change.
    """
    import numpy as np

    from sim.engine import _build_data, sample_households

    sc = load_scenario("configs/scenarios/haves_havenots.yaml")
    hh = sample_households(sc, np.random.default_rng(sc.seed))
    nbhd = build_overlay_neighborhood(
        sc.rows,
        sc.cols,
        sc.affiliations,
        bus_max_kw=sc.bus_max_kw,
        bus_loss_factor=sc.bus_loss_factor,
    )
    solar, loads = _build_data(sc, hh)
    ceiling = lp_optimal.optimal_served_fraction(sc, hh, solar, loads, nbhd)
    assert abs(ceiling - 0.529368385) < 5e-7


def test_lp_run_deterministic(tmp_path: Path) -> None:
    a = _run_strategy("lp_optimal", tmp_path / "a")
    b = _run_strategy("lp_optimal", tmp_path / "b")
    assert a == b
    sa = (tmp_path / "a" / "lp_optimal" / "state.jsonl").read_text()
    sb = (tmp_path / "b" / "lp_optimal" / "state.jsonl").read_text()
    assert sa == sb


def test_schedule_conserves_gross_when_house_both_sends_and_receives() -> None:
    """A house appearing in both the sender and receiver pools must not lose
    its share: pre-P2.9 the self-pair share was silently dropped, so the
    scheduled gross fell short of the LP's planned flows."""
    from sim.strategies.lp_optimal import _schedule_from_solution

    ids = ["a", "b"]
    ticks = [datetime(2018, 1, 1)]
    col = {}
    x = []
    for hid in ids:
        for kind in ("send", "recv"):
            col[(kind, hid, 0)] = len(x)
            x.append(0.0)
    import numpy as np

    xa = np.zeros(len(x))
    xa[col[("send", "a", 0)]] = 1.0
    xa[col[("send", "b", 0)]] = 0.5
    xa[col[("recv", "b", 0)]] = 1.425  # 0.95 * (1.0 + 0.5) gross
    grid_at = {("a", 0): False, ("b", 0): False}
    schedule = _schedule_from_solution(xa, col, ids, ticks, grid_at, loss=0.05)
    transfers = schedule[ticks[0]]
    assert all(t.from_id == "a" and t.to_id == "b" for t in transfers)
    # b's own 0.5 kW send must be re-normalized onto a, conserving 1.5 kW gross.
    assert sum(t.kw for t in transfers) == pytest.approx(1.5, abs=1e-9)


def test_lp_solves_partial_island_and_dominates_round_robin(tmp_path: Path) -> None:
    base = load_scenario("configs/scenarios/synthetic_lp_smoke.yaml")
    for n_islanded in (3, 5):  # 3: two >=2-member groups; 5: a 1-member connected group
        w = base.outages[0]
        partial = dataclasses.replace(
            base,
            outages=(dataclasses.replace(w, affected_houses=w.affected_houses[:n_islanded]),),
        )
        hh = sample_households(partial, np.random.default_rng(partial.seed))
        nbhd = build_overlay_neighborhood(
            partial.rows,
            partial.cols,
            partial.affiliations,
            bus_max_kw=partial.bus_max_kw,
            bus_loss_factor=partial.bus_loss_factor,
        )
        solar, loads = _build_data(partial, hh)
        lp = lp_optimal.optimal_metrics(partial, hh, solar, loads, nbhd)
        rr_sc = dataclasses.replace(partial, strategy="round_robin")
        logger = JsonlLogger(run_dir=tmp_path / f"rr{n_islanded}", scenario_id=rr_sc.scenario_id)
        rr = run(
            rr_sc,
            importlib.import_module("sim.strategies.round_robin").decide_transfers,
            logger,
        )
        logger.close()
        assert 0.0 < lp["served_load_fraction"] <= 1.0
        assert lp["served_load_fraction"] >= rr["served_load_fraction"] - 1e-9


def test_lp_gini_counts_zero_load_houses_as_fully_served(tmp_path: Path) -> None:
    from sim.logging import _gini

    base = load_scenario("configs/scenarios/synthetic_lp_smoke.yaml")
    zero_load = dataclasses.replace(
        base, household_sampling={**base.household_sampling, "synthetic_load_kw": 0.0}
    )
    hh = sample_households(zero_load, np.random.default_rng(zero_load.seed))
    nbhd = build_overlay_neighborhood(
        zero_load.rows,
        zero_load.cols,
        zero_load.affiliations,
        bus_max_kw=zero_load.bus_max_kw,
        bus_loss_factor=zero_load.bus_loss_factor,
    )
    solar, loads = _build_data(zero_load, hh)
    lp = lp_optimal.optimal_metrics(zero_load, hh, solar, loads, nbhd)
    # Every house has zero load -> engine rule scores each 1.0 -> gini 0 (parity
    # with sim/logging.py, which counts zero-load houses at served-fraction 1.0).
    assert lp["gini_welfare"] == pytest.approx(_gini([1.0] * len(hh)))
    assert lp["served_load_fraction"] == pytest.approx(1.0)
