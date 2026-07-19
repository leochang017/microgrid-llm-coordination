"""Tests for dotted-key scenario overrides + the sweep driver (Phase 3 T9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sim.overrides import apply_overrides
from sim.scenario import load_scenario

_SCENARIO = Path("configs/scenarios/haves_havenots__llm.yaml")


def test_override_nested_dataclass_field() -> None:
    sc = load_scenario(_SCENARIO)
    out = apply_overrides(sc, ["failure_modes.defector_fraction=0.4"])
    assert out.failure_modes.defector_fraction == 0.4
    assert sc.failure_modes.defector_fraction != 0.4  # original untouched


def test_override_double_nested_and_null() -> None:
    sc = load_scenario(_SCENARIO)
    out = apply_overrides(
        sc,
        [
            "failure_modes.obs_noise.soc_std_frac=0.2",
            "failure_modes.comm.per_tick_budget=null",
            "seed=99",
        ],
    )
    assert out.failure_modes.obs_noise.soc_std_frac == 0.2
    assert out.failure_modes.comm.per_tick_budget is None
    assert out.seed == 99


def test_override_dict_field() -> None:
    sc = load_scenario(_SCENARIO)
    out = apply_overrides(sc, ["llm.messaging=off", "household_sampling.have_fraction=0.5"])
    # YAML parses bare `off` as boolean False — the facade accepts both that
    # and the string "off" as messaging-disabled (see llm_agent.prepare).
    assert out.llm["messaging"] is False
    assert out.household_sampling["have_fraction"] == 0.5


def test_override_unknown_key_is_hard_error() -> None:
    """A typo'd sweep axis must never silently run the base scenario."""
    sc = load_scenario(_SCENARIO)
    with pytest.raises(ValueError, match="defectr_fraction"):
        apply_overrides(sc, ["failure_modes.defectr_fraction=0.4"])
    with pytest.raises(ValueError, match="not_a_field"):
        apply_overrides(sc, ["not_a_field=1"])


def test_override_dict_leaf_typo_is_hard_error() -> None:
    """A typo'd FINAL leaf key inside a dict-typed field (llm/household_sampling/
    data_paths) must be rejected exactly like a dataclass-path typo — it must
    never silently add a dead key while leaving the real field untouched (C6-2).
    """
    sc = load_scenario(_SCENARIO)
    with pytest.raises(ValueError, match="rect_max_per_tick"):
        apply_overrides(sc, ["llm.rect_max_per_tick=99"])
    with pytest.raises(ValueError, match="hve_fraction"):
        apply_overrides(sc, ["household_sampling.hve_fraction=0.9"])


def test_override_dict_leaf_real_key_still_works() -> None:
    """The fix must not collateral-damage legitimate dict-leaf overrides."""
    sc = load_scenario(_SCENARIO)
    out = apply_overrides(sc, ["llm.react_max_per_tick=5"])
    assert out.llm["react_max_per_tick"] == 5
    # A brand-new-but-known llm key (not present in this YAML) must still work.
    out2 = apply_overrides(sc, ["llm.messaging=off"])
    assert out2.llm["messaging"] is False
    # household_sampling has no fixed known-key set; a key already present in
    # the scenario's dict must still be overridable.
    out3 = apply_overrides(sc, ["household_sampling.have_fraction=0.9"])
    assert out3.household_sampling["have_fraction"] == 0.9


def test_sweep_driver_end_to_end_smoke(tmp_path: Path) -> None:
    """One tiny axis x one strategy x one seed through real subprocesses."""
    import yaml

    from scripts.sweep import run_grid

    grid = {
        "name": "smoke",
        "scenario": "configs/scenarios/synthetic_lp_smoke.yaml",
        "strategies": ["no_coordination", "round_robin"],
        "seeds": [7],
        "axes": [
            {
                "name": "bus",
                "set": "bus_max_kw",
                "values": [50.0],
            }
        ],
    }
    grid_path = tmp_path / "grid.yaml"
    grid_path.write_text(yaml.safe_dump(grid))
    report = run_grid(grid_path, tmp_path / "out")
    assert "axis: bus" in report
    assert "no_coordination" in report and "round_robin" in report
    assert (tmp_path / "out" / "smoke" / "report.md").exists()


def test_sweep_records_failed_cells_and_keeps_going(tmp_path: Path) -> None:
    from scripts.sweep import run_grid

    grid = tmp_path / "grid.yaml"
    grid.write_text(
        "name: failgrid\n"
        "scenario: configs/scenarios/synthetic_lp_smoke.yaml\n"
        "strategies: [round_robin, no_such_strategy]\n"
        "seeds: [23]\n"
        "axes:\n"
        "  - name: dt\n    set: seed\n    values: [23]\n"
    )
    report = run_grid(grid, tmp_path / "out")
    assert "FAILED" in report  # bad strategy recorded in-place
    assert "0." in report.split("FAILED")[0]  # round_robin cell still tabulated
    assert (tmp_path / "out" / "failgrid" / "report.md").exists()
