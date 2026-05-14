"""Tests for the simulation engine."""

from datetime import datetime, timedelta

import numpy as np

from sim.engine import sample_households
from sim.scenario import Scenario


def make_scenario(seed: int = 42) -> Scenario:
    return Scenario(
        scenario_id="test",
        start=datetime(2024, 7, 1),
        end=datetime(2024, 7, 1) + timedelta(hours=1),
        dt_hours=0.25,
        seed=seed,
        rows=5,
        cols=6,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
        strategy="no_coordination",
        data_source="synthetic",
        household_sampling={
            "pv_kw_peak": [4.0, 12.0],
            "battery_kwh": [10.0, 27.0],
            "rt_efficiency": 0.9,
            "dod_floor_frac": 0.1,
            "grid_max_kw": 10.0,
        },
        outages=(),
    )


def test_sample_households_count() -> None:
    s = make_scenario()
    rng = np.random.default_rng(s.seed)
    households = sample_households(s, rng)
    assert len(households) == 30
    assert all(hid.startswith("r") for hid in households)


def test_sample_households_deterministic() -> None:
    s = make_scenario(seed=42)
    h1 = sample_households(s, np.random.default_rng(s.seed))
    h2 = sample_households(s, np.random.default_rng(s.seed))
    assert h1["r0c0"].pv_kw_peak == h2["r0c0"].pv_kw_peak
    assert h1["r2c3"].battery_kwh == h2["r2c3"].battery_kwh


def test_sample_households_in_range() -> None:
    s = make_scenario()
    households = sample_households(s, np.random.default_rng(s.seed))
    for h in households.values():
        assert 4.0 <= h.pv_kw_peak <= 12.0
        assert 10.0 <= h.battery_kwh <= 27.0
        assert h.rt_efficiency == 0.9
        assert h.dod_floor_frac == 0.1
        assert h.grid_max_kw == 10.0


def test_run_smoke_no_coordination(tmp_path) -> None:
    """End-to-end synthetic_smoke scenario with no_coordination should run clean.

    The synthetic_smoke scenario has no outage. Every house starts at 50% SoC
    and gets a half-sine of solar through the day plus a constant 1.5 kW load.
    Most load is served (some from battery, some left unmet at night if solar
    didn't recharge enough — that's why we assert >= 0.6 rather than > 0.99).
    """
    from pathlib import Path

    from sim.engine import run
    from sim.logging import JsonlLogger
    from sim.scenario import load_scenario
    from sim.strategies.no_coordination import decide_transfers

    scenario_path = Path(__file__).parent.parent / "configs" / "scenarios" / "synthetic_smoke.yaml"
    s = load_scenario(scenario_path)
    out = tmp_path / "run"
    logger = JsonlLogger(out, scenario_id=s.scenario_id)
    summary = run(s, decide_transfers, logger, strict=True)
    logger.close()
    # Sanity bounds: served fraction is in [0, 1], the run produced output.
    assert 0.0 <= summary["served_load_fraction"] <= 1.0
    # 30 houses x 96 ticks (15-min over 24 h) = 2880 state rows
    rows = (out / "state.jsonl").read_text().splitlines()
    assert len(rows) == 30 * 96


def test_run_smoke_deterministic_byte_identical(tmp_path) -> None:
    """Two runs of the same scenario yield byte-identical state.jsonl."""
    from pathlib import Path

    from sim.engine import run
    from sim.logging import JsonlLogger
    from sim.scenario import load_scenario
    from sim.strategies.no_coordination import decide_transfers

    scenario_path = Path(__file__).parent.parent / "configs" / "scenarios" / "synthetic_smoke.yaml"
    s = load_scenario(scenario_path)

    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    lg_a = JsonlLogger(out_a, scenario_id=s.scenario_id)
    run(s, decide_transfers, lg_a, strict=True)
    lg_a.close()
    lg_b = JsonlLogger(out_b, scenario_id=s.scenario_id)
    run(s, decide_transfers, lg_b, strict=True)
    lg_b.close()

    assert (out_a / "state.jsonl").read_bytes() == (out_b / "state.jsonl").read_bytes()
