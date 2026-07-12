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
# LP: only OBJECTIVE-derived values are pinned tightly. The LP has degenerate
# optima — different scipy/HiGHS versions pick different optimal vertices with
# identical served totals but different per-house distributions, so the LP's
# gini is solver-version-dependent (observed 0.3617 locally vs 0.3620 on CI,
# 2026-07-07). Never quote LP gini beyond ~2 decimals in the paper.
_GOLDEN_LP_SERVED = 0.529368385
_GOLDEN_LP_UNMET = 169.427381
_GOLDEN_LP_GINI_BAND = (0.30, 0.42)


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
    assert metrics["served_load_fraction"] == pytest.approx(_GOLDEN_LP_SERVED, abs=5e-7)
    assert metrics["unmet_kwh_total"] == pytest.approx(_GOLDEN_LP_UNMET, abs=5e-4)
    lo, hi = _GOLDEN_LP_GINI_BAND
    assert lo <= metrics["gini_welfare"] <= hi


# --- Phase 3 solar showcase (haves_havenots_solar): the coordination-bound
# regime — energy abundant but misplaced; rr->LP gap ~20.4 points. ---

_SOLAR_SCENARIO = Path("configs/scenarios/haves_havenots_solar.yaml")
_GOLDEN_SOLAR = {
    "no_coordination": (0.427998225, 411.841278, 0.538793996),
    "round_robin": (0.766615062, 168.037156, 0.173723427),
}
_GOLDEN_SOLAR_LP_SERVED = 0.971095995
_GOLDEN_SOLAR_LP_UNMET = 20.810884


@pytest.mark.parametrize("strategy", sorted(_GOLDEN_SOLAR))
def test_golden_solar_engine_strategies(strategy: str, tmp_path: Path) -> None:
    base = load_scenario(_SOLAR_SCENARIO)
    sc = dataclasses.replace(base, strategy=strategy)
    mod = importlib.import_module(f"sim.strategies.{strategy}")
    logger = JsonlLogger(run_dir=tmp_path / strategy, scenario_id=sc.scenario_id)
    summary = run(sc, mod.decide_transfers, logger)
    logger.close()
    served, unmet, gini = _GOLDEN_SOLAR[strategy]
    assert summary["served_load_fraction"] == pytest.approx(served, abs=5e-7)
    assert summary["unmet_kwh_total"] == pytest.approx(unmet, abs=5e-4)
    assert summary["gini_welfare"] == pytest.approx(gini, abs=5e-7)


def test_golden_solar_lp_ceiling() -> None:
    base = load_scenario(_SOLAR_SCENARIO)
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
    assert metrics["served_load_fraction"] == pytest.approx(_GOLDEN_SOLAR_LP_SERVED, abs=5e-7)
    assert metrics["unmet_kwh_total"] == pytest.approx(_GOLDEN_SOLAR_LP_UNMET, abs=5e-4)
    # LP gini is solver-version-dependent (degenerate optima) — band only.
    assert 0.0 <= metrics["gini_welfare"] <= 0.10


# --- Zero-LLM control (llm_fallback): the bar every live LLM cell must beat.
# Pinned P3.1 T21 (2026-07-12) after the Phase 3.1 behavior fixes (T1 receiver
# cap, T5 defector gating, T7-T9 negotiation, T19 critical_load_frac draw).
_GOLDEN_LLM_FALLBACK = {
    "configs/scenarios/haves_havenots__llm.yaml": (0.5196124446654724, 0.31851161610533363, 263),
    "configs/scenarios/haves_havenots_solar__llm.yaml": (
        0.6268723111989367,
        0.2870158834669121,
        966,
    ),
}


@pytest.mark.parametrize("scenario_path", sorted(_GOLDEN_LLM_FALLBACK))
def test_golden_llm_fallback_control(scenario_path: str, tmp_path: Path) -> None:
    from sim.strategies import llm_fallback

    sc = dataclasses.replace(load_scenario(scenario_path), strategy="llm_fallback")
    logger = JsonlLogger(run_dir=tmp_path / "ctl", scenario_id=sc.scenario_id)
    summary = run(sc, None, logger, prepare=llm_fallback.prepare)
    logger.close()
    served, gini, transfers = _GOLDEN_LLM_FALLBACK[scenario_path]
    assert summary["served_load_fraction"] == pytest.approx(served, abs=5e-7)
    assert summary["gini_welfare"] == pytest.approx(gini, abs=5e-7)
    assert summary["transfer_count"] == transfers
