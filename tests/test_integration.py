"""End-to-end integration tests.

These are the first cross-module checks of the simulator: real scenario YAML +
real strategy + real engine + real logger producing a real summary.json. The
round-robin-vs-no-coordination test is the 'does coordination actually do
anything?' sanity check — if it fails, the strategy or the network module
needs tuning before Phase 2 lands.
"""

from pathlib import Path

import pytest

from sim.engine import run
from sim.logging import JsonlLogger
from sim.scenario import load_scenario
from sim.strategies.no_coordination import decide_transfers as no_coord
from sim.strategies.round_robin import decide_transfers as round_robin

_SCENARIOS_DIR = Path(__file__).parent.parent / "configs" / "scenarios"


def _run_to_summary(scenario_path: Path, strategy, out: Path) -> dict:  # type: ignore[no-untyped-def]
    s = load_scenario(scenario_path)
    logger = JsonlLogger(out, scenario_id=s.scenario_id)
    summary = run(s, strategy, logger, strict=True)
    logger.close()
    return summary


def test_round_robin_no_worse_than_no_coord_on_easy_scenario(tmp_path: Path) -> None:
    """On the synthetic 24h_uniform scenario both strategies serve ~100% load
    (batteries are oversized), so the test only checks that round_robin is no
    worse than no_coordination on Gini or served fraction (not strict improvement).
    The strict-improvement test lives on the harsh overnight scenario below.
    """
    scenario = _SCENARIOS_DIR / "24h_uniform.yaml"
    rr_summary = _run_to_summary(scenario, round_robin, tmp_path / "rr")
    nc_summary = _run_to_summary(scenario, no_coord, tmp_path / "nc")
    assert rr_summary["gini_welfare"] <= nc_summary["gini_welfare"]
    assert rr_summary["served_load_fraction"] >= nc_summary["served_load_fraction"] - 0.05


def test_round_robin_cannot_create_energy_on_harsh_overnight_outage(tmp_path: Path) -> None:
    """Conservation regression for overnight_outage_hard (2026-07-06 correction).

    The pre-Phase-2.9 version of this test asserted round_robin saves >=10 kWh
    of unmet load here. That entire saving was PHANTOM energy from the old
    sender-cap bug: at night every house's load (3 kW) exceeds its battery's
    deliverable power (~1.9 kW), so nobody has anything to spare — with
    conservation enforced, round_robin's transfers are all clipped to zero and
    it must land EXACTLY on no_coordination's numbers. Real coordination
    headroom on this scenario exists (LP ceiling 0.8642 vs 0.8300) but the
    5%-share heuristic cannot reach it; that gap is Phase 3 material.
    """
    scenario = _SCENARIOS_DIR / "overnight_outage_hard.yaml"
    rr_summary = _run_to_summary(scenario, round_robin, tmp_path / "rr")
    nc_summary = _run_to_summary(scenario, no_coord, tmp_path / "nc")
    assert rr_summary["unmet_kwh_total"] == pytest.approx(nc_summary["unmet_kwh_total"], abs=1e-6)
    assert rr_summary["served_load_fraction"] == pytest.approx(
        nc_summary["served_load_fraction"], abs=1e-9
    )
    assert rr_summary["gini_welfare"] <= nc_summary["gini_welfare"] + 1e-9


def test_round_robin_genuinely_helps_on_lp_smoke(tmp_path: Path) -> None:
    """The 'coordination actually does something' check, on a scenario where
    that is physically true post-conservation-fix: synthetic_lp_smoke's mixed
    battery sizes leave real deliverable surplus, and the load-aware receiver
    cap lets deficit houses absorb it. round_robin saves ~4.7 kWh of unmet
    load (10.6 -> 5.9) and executes real transfers.
    """
    scenario = _SCENARIOS_DIR / "synthetic_lp_smoke.yaml"
    rr_summary = _run_to_summary(scenario, round_robin, tmp_path / "rr")
    nc_summary = _run_to_summary(scenario, no_coord, tmp_path / "nc")
    assert rr_summary["unmet_kwh_total"] <= nc_summary["unmet_kwh_total"] - 4.0, (
        f"round_robin unmet={rr_summary['unmet_kwh_total']:.1f} vs "
        f"no_coord unmet={nc_summary['unmet_kwh_total']:.1f}"
    )
    assert rr_summary["gini_welfare"] <= nc_summary["gini_welfare"]
    assert rr_summary["transfer_count"] > 0


def test_determinism_byte_identical(tmp_path: Path) -> None:
    """Two runs of the same scenario produce byte-identical state.jsonl."""
    scenario = _SCENARIOS_DIR / "synthetic_smoke.yaml"
    _run_to_summary(scenario, no_coord, tmp_path / "a")
    _run_to_summary(scenario, no_coord, tmp_path / "b")
    assert (tmp_path / "a" / "state.jsonl").read_bytes() == (
        tmp_path / "b" / "state.jsonl"
    ).read_bytes()
