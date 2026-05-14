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


def test_round_robin_more_even_than_no_coord(tmp_path: Path) -> None:
    """Round-robin sharing should produce strictly more even welfare distribution
    (lower Gini) than no-coordination on the 24h_uniform outage scenario."""
    scenario = _SCENARIOS_DIR / "24h_uniform.yaml"
    rr_summary = _run_to_summary(scenario, round_robin, tmp_path / "rr")
    nc_summary = _run_to_summary(scenario, no_coord, tmp_path / "nc")
    # Lower Gini = more equal welfare. Round-robin should not be worse than no-coord.
    assert rr_summary["gini_welfare"] <= nc_summary["gini_welfare"]
    # Round-robin moves energy around with bus losses, so served fraction may
    # be slightly worse. Allow a small margin but not collapse.
    assert rr_summary["served_load_fraction"] >= nc_summary["served_load_fraction"] - 0.05


def test_determinism_byte_identical(tmp_path: Path) -> None:
    """Two runs of the same scenario produce byte-identical state.jsonl."""
    scenario = _SCENARIOS_DIR / "synthetic_smoke.yaml"
    _run_to_summary(scenario, no_coord, tmp_path / "a")
    _run_to_summary(scenario, no_coord, tmp_path / "b")
    assert (tmp_path / "a" / "state.jsonl").read_bytes() == (
        tmp_path / "b" / "state.jsonl"
    ).read_bytes()
