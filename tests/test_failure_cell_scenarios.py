"""Failure-cell variants of haves_havenots load + parse without error."""

from __future__ import annotations

from pathlib import Path

from sim.scenario import load_scenario

ROOT = Path(__file__).resolve().parent.parent
SCEN_DIR = ROOT / "configs" / "scenarios"


def test_haves_havenots_llm_loads() -> None:
    s = load_scenario(SCEN_DIR / "haves_havenots__llm.yaml")
    assert s.strategy == "llm_agent"
    assert s.llm["model"].startswith("claude-")
    assert s.failure_modes.defector_fraction == 0.0


def test_haves_havenots_defectors_loads() -> None:
    s = load_scenario(SCEN_DIR / "haves_havenots__defectors.yaml")
    assert s.failure_modes.defector_fraction == 0.2
    assert s.failure_modes.defector_realization == "wrapper"


def test_haves_havenots_noise_loads() -> None:
    s = load_scenario(SCEN_DIR / "haves_havenots__noise.yaml")
    assert s.failure_modes.obs_noise.soc_std_frac == 0.10


def test_haves_havenots_comm_loads() -> None:
    s = load_scenario(SCEN_DIR / "haves_havenots__comm.yaml")
    assert s.failure_modes.comm.per_tick_budget == 2
    assert s.failure_modes.comm.drop_prob_by_circle["geographic"] == 0.30


def test_haves_havenots_all_loads() -> None:
    s = load_scenario(SCEN_DIR / "haves_havenots__all.yaml")
    assert s.failure_modes.defector_fraction > 0
    assert s.failure_modes.obs_noise.soc_std_frac > 0
    assert s.failure_modes.comm.per_tick_budget is not None
