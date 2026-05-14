"""End-to-end integration tests.

These are the first cross-module checks of the simulator: real scenario YAML +
real strategy + real engine + real logger producing a real summary.json. The
round-robin-vs-no-coordination test is the 'does coordination actually do
anything?' sanity check — if it fails, the strategy or the network module
needs tuning before Phase 2 lands.
"""

from pathlib import Path

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


def test_round_robin_strictly_helps_on_harsh_overnight_outage(tmp_path: Path) -> None:
    """On the overnight_outage_hard scenario (12 h outage with no solar to recharge,
    high load, heterogeneous batteries) round_robin must STRICTLY improve on
    no_coordination on at least one of: unmet kWh (lower), Gini (lower). This is
    the test that proves coordination does something — the easy scenario's
    sub-test passes vacuously because both strategies hit Gini=0."""
    scenario = _SCENARIOS_DIR / "overnight_outage_hard.yaml"
    rr_summary = _run_to_summary(scenario, round_robin, tmp_path / "rr")
    nc_summary = _run_to_summary(scenario, no_coord, tmp_path / "nc")
    # Round-robin must reduce total unmet load by at least 10 kWh (review fix I2).
    assert rr_summary["unmet_kwh_total"] <= nc_summary["unmet_kwh_total"] - 10.0, (
        f"round_robin unmet={rr_summary['unmet_kwh_total']:.1f} vs "
        f"no_coord unmet={nc_summary['unmet_kwh_total']:.1f}"
    )
    # And Gini (welfare inequality) must not be worse.
    assert rr_summary["gini_welfare"] <= nc_summary["gini_welfare"]
    # And round_robin must actually perform transfers (sanity check the strategy ran).
    assert rr_summary["transfer_count"] > 0


def test_determinism_byte_identical(tmp_path: Path) -> None:
    """Two runs of the same scenario produce byte-identical state.jsonl."""
    scenario = _SCENARIOS_DIR / "synthetic_smoke.yaml"
    _run_to_summary(scenario, no_coord, tmp_path / "a")
    _run_to_summary(scenario, no_coord, tmp_path / "b")
    assert (tmp_path / "a" / "state.jsonl").read_bytes() == (
        tmp_path / "b" / "state.jsonl"
    ).read_bytes()
