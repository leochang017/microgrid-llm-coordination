"""Acceptance tests: stress scenarios where simple sharing visibly breaks.

The advisor's bar before Phase 2: a regime where the no-coordination baseline is
well below the forgiving ~98.5% ceiling of the original headline scenario, where
geographic round_robin still leaves substantial unmet demand, and where the LP
ceiling proves there is real coordination headroom left to capture.
"""

import dataclasses
import importlib

import numpy as np

from sim.engine import _build_data, run, sample_households
from sim.logging import JsonlLogger
from sim.network import build_overlay_neighborhood
from sim.scenario import load_scenario
from sim.strategies import lp_optimal

_SCENARIO = "configs/scenarios/haves_havenots.yaml"


def _run(strategy: str, tmp_path) -> dict:
    sc = dataclasses.replace(load_scenario(_SCENARIO), strategy=strategy)
    mod = importlib.import_module(f"sim.strategies.{strategy}")
    logger = JsonlLogger(run_dir=str(tmp_path / strategy), scenario_id=sc.scenario_id)
    return run(
        sc,
        getattr(mod, "decide_transfers", None),
        logger,
        prepare=getattr(mod, "prepare", None),
    )


def _lp_ceiling() -> float:
    sc = load_scenario(_SCENARIO)
    households = sample_households(sc, np.random.default_rng(sc.seed))
    nbhd = build_overlay_neighborhood(
        sc.rows,
        sc.cols,
        sc.affiliations,
        bus_max_kw=sc.bus_max_kw,
        bus_loss_factor=sc.bus_loss_factor,
    )
    solar, loads = _build_data(sc, households)
    return lp_optimal.optimal_served_fraction(sc, households, solar, loads, nbhd)


def test_haves_havenots_breaks_simple_sharing(tmp_path) -> None:
    nocoord = _run("no_coordination", tmp_path)
    rr = _run("round_robin", tmp_path)
    lp_ceiling = _lp_ceiling()

    # 1. No-coordination is well below the forgiving ceiling of the easy scenario.
    assert nocoord["served_load_fraction"] < 0.90
    # 2. Geographic round-robin still leaves substantial unmet demand.
    assert rr["unmet_kwh_total"] > 100.0
    # 3. The LP optimum is a genuine ceiling above round-robin (room to capture).
    assert lp_ceiling >= rr["served_load_fraction"] - 1e-9
    # 4. Total coordination headroom over no-coordination is meaningful (> 2 pts).
    assert lp_ceiling > nocoord["served_load_fraction"] + 0.02
