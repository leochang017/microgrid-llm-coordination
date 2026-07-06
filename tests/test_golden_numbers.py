"""Golden-number regression pins for the showcase scenario (Phase 2.9 Task 11).

Byte-determinism makes exact pins free: any physics, settlement, sampling, or
metric change that moves a headline number fails here LOUDLY instead of
shifting the paper's reference points silently. Values derived 2026-07-06
after the Phase 2.9 conservation + LP fixes.

Update these ONLY on an intentional physics change, in the same commit, with
the progress-log row explaining why.
"""

from __future__ import annotations

import dataclasses
import importlib
from pathlib import Path

import numpy as np
import pytest

from sim.engine import _build_data, run, sample_households
from sim.logging import JsonlLogger
from sim.network import build_overlay_neighborhood
from sim.scenario import load_scenario
from sim.strategies import lp_optimal

_SCENARIO = Path("configs/scenarios/haves_havenots.yaml")

# strategy -> (served_load_fraction, unmet_kwh_total, gini_welfare)
_GOLDEN = {
    "no_coordination": (0.455996451, 195.841278, 0.485104102),
    "round_robin": (0.519448106, 172.998682, 0.224442279),
}
_GOLDEN_LP = (0.529368385, 169.427381, 0.361703260)


@pytest.mark.parametrize("strategy", sorted(_GOLDEN))
def test_golden_engine_strategies(strategy: str, tmp_path: Path) -> None:
    base = load_scenario(_SCENARIO)
    sc = dataclasses.replace(base, strategy=strategy)
    mod = importlib.import_module(f"sim.strategies.{strategy}")
    logger = JsonlLogger(run_dir=tmp_path / strategy, scenario_id=sc.scenario_id)
    summary = run(sc, mod.decide_transfers, logger)
    logger.close()
    served, unmet, gini = _GOLDEN[strategy]
    assert summary["served_load_fraction"] == pytest.approx(served, abs=5e-7)
    assert summary["unmet_kwh_total"] == pytest.approx(unmet, abs=5e-4)
    assert summary["gini_welfare"] == pytest.approx(gini, abs=5e-7)


def test_golden_lp_ceiling() -> None:
    base = load_scenario(_SCENARIO)
    hh = sample_households(base, np.random.default_rng(base.seed))
    nbhd = build_overlay_neighborhood(
        base.rows,
        base.cols,
        base.affiliations,
        bus_max_kw=base.bus_max_kw,
        bus_loss_factor=base.bus_loss_factor,
    )
    solar, loads = _build_data(base, hh)
    metrics = lp_optimal.optimal_metrics(base, hh, solar, loads, nbhd)
    served, unmet, gini = _GOLDEN_LP
    assert metrics["served_load_fraction"] == pytest.approx(served, abs=5e-7)
    assert metrics["unmet_kwh_total"] == pytest.approx(unmet, abs=5e-4)
    assert metrics["gini_welfare"] == pytest.approx(gini, abs=5e-7)
