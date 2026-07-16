"""Failure-cell variants of haves_havenots load + parse without error."""

from __future__ import annotations

from pathlib import Path

import pytest

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


# --- realized dose (2026-07-16) ---
#
# The tests above assert each cell is CONFIGURED. They cannot catch a cell that
# parses perfectly and is still inert: at seed 23 the defectors cell assigns all
# 6 defectors to have-nots, who hold 0 kW PV and 2-4 kWh batteries and so
# withhold 0.0% of generation. That cell reached a paid live run before anyone
# noticed, and would have produced "robust to 20% defectors" -- false, because
# no defector could defect. Configuration is not dose.


def test_defector_dose_is_inert_at_seed_23() -> None:
    """The 9.1% draw that nearly shipped a false robustness claim.

    P(all 6 defectors land on have-nots | 9 haves, 30 houses)
      = C(21,6)/C(30,6) = 0.091
    """
    from scripts.dose_check import realized_defector_dose

    s = load_scenario(SCEN_DIR / "haves_havenots_solar__defectors.yaml")
    d = realized_defector_dose(s, seed=23)
    assert d.n_defectors == 6
    assert d.n_have_defectors == 0
    assert d.withheld_generation_frac == 0.0
    assert d.is_inert


def test_defector_dose_is_potent_at_seed_7() -> None:
    """Seed 7 is what the cell is actually run at; pin the dose it delivers."""
    from scripts.dose_check import realized_defector_dose

    s = load_scenario(SCEN_DIR / "haves_havenots_solar__defectors.yaml")
    d = realized_defector_dose(s, seed=7)
    assert d.n_have_defectors == 4
    assert d.withheld_generation_frac == pytest.approx(0.336, abs=0.005)
    assert not d.is_inert


def test_clean_cell_has_no_defectors() -> None:
    from scripts.dose_check import realized_defector_dose

    s = load_scenario(SCEN_DIR / "haves_havenots_solar__llm.yaml")
    d = realized_defector_dose(s, seed=23)
    assert d.n_defectors == 0
    assert d.is_inert  # nothing configured -> nothing dosed
