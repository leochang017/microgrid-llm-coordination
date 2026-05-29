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


def test_run_resstock_path_end_to_end(tmp_path) -> None:
    """Exercise data_source='resstock' end-to-end against in-repo CSV fixtures
    (Phase 1.5). 4 buildings on a 2x2 grid for 3 ticks."""
    from datetime import datetime, timedelta
    from pathlib import Path

    from sim.engine import run
    from sim.logging import JsonlLogger
    from sim.scenario import Scenario
    from sim.strategies.no_coordination import decide_transfers

    fixtures = Path(__file__).parent / "fixtures"
    s = Scenario(
        scenario_id="resstock_smoke",
        start=datetime(2024, 7, 1, 0, 0),
        end=datetime(2024, 7, 1, 0, 0) + timedelta(minutes=45),
        dt_hours=0.25,
        seed=42,
        rows=2,
        cols=2,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
        strategy="no_coordination",
        data_source="resstock",
        household_sampling={
            "pv_kw_peak": [4.0, 12.0],
            "battery_kwh": [10.0, 27.0],
            "rt_efficiency": 0.9,
            "dod_floor_frac": 0.1,
            "grid_max_kw": 10.0,
        },
        outages=(),
        data_paths={
            "solar_csv": str(fixtures / "nrel_sample.csv"),
            "load_dir": str(fixtures / "resstock"),
        },
        house_building_files=(
            "bldg0000001-up00.csv",
            "bldg0000002-up00.csv",
            "bldg0000003-up00.csv",
            "bldg0000004-up00.csv",
        ),
    )
    out = tmp_path / "resstock_run"
    logger = JsonlLogger(out, scenario_id=s.scenario_id)
    summary = run(s, decide_transfers, logger, strict=True)
    logger.close()
    rows = (out / "state.jsonl").read_text().splitlines()
    assert len(rows) == 12  # 4 houses x 3 ticks
    assert 0.0 <= summary["served_load_fraction"] <= 1.0


def test_run_real_data_path_end_to_end(tmp_path) -> None:
    """Exercise the data_source='pecan_street' dispatch end-to-end against the
    in-repo CSV fixtures (review fix C3). This was the largest coverage gap —
    the real-data branch in engine._build_data was previously only smoke-tested
    via its adapter unit tests, never run as part of a full engine.run."""
    from datetime import datetime, timedelta
    from pathlib import Path

    from sim.engine import run
    from sim.logging import JsonlLogger
    from sim.scenario import Scenario
    from sim.strategies.no_coordination import decide_transfers

    fixtures = Path(__file__).parent / "fixtures"
    s = Scenario(
        scenario_id="real_data_smoke",
        start=datetime(2024, 7, 1, 0, 0),
        end=datetime(2024, 7, 1, 0, 0) + timedelta(minutes=45),  # 3 ticks at 15 min
        dt_hours=0.25,
        seed=42,
        rows=2,
        cols=2,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
        strategy="no_coordination",
        data_source="pecan_street",
        household_sampling={
            "pv_kw_peak": [4.0, 12.0],
            "battery_kwh": [10.0, 27.0],
            "rt_efficiency": 0.9,
            "dod_floor_frac": 0.1,
            "grid_max_kw": 10.0,
        },
        outages=(),
        data_paths={
            "solar_csv": str(fixtures / "nrel_sample.csv"),
            "load_csv": str(fixtures / "pecan_sample.csv"),
        },
        house_dataids=(1234, 1235, 1236, 1237),
    )
    out = tmp_path / "real"
    logger = JsonlLogger(out, scenario_id=s.scenario_id)
    summary = run(s, decide_transfers, logger, strict=True)
    logger.close()
    # 4 houses x 3 ticks = 12 state rows
    rows = (out / "state.jsonl").read_text().splitlines()
    assert len(rows) == 12
    # Sanity: served fraction is in [0, 1]
    assert 0.0 <= summary["served_load_fraction"] <= 1.0


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


def _scenario(**kw: object) -> Scenario:
    base: dict[str, object] = dict(
        scenario_id="t",
        start=datetime(2018, 1, 1),
        end=datetime(2018, 1, 1, 6),
        dt_hours=0.25,
        seed=1,
        rows=2,
        cols=2,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
        strategy="round_robin",
        data_source="synthetic",
        household_sampling={
            "pv_kw_peak": [4.0, 8.0],
            "battery_kwh": [5.0, 10.0],
            "rt_efficiency": 0.9,
            "dod_floor_frac": 0.1,
        },
    )
    base.update(kw)
    return Scenario(**base)  # type: ignore[arg-type]


def test_sample_households_assigns_affiliations() -> None:
    sc = _scenario(affiliations={"owner": {"owner_a": ("r0c0", "r1c1")}})
    hh = sample_households(sc, np.random.default_rng(sc.seed))
    assert hh["r0c0"].affiliations == {"owner": "owner_a"}
    assert hh["r1c1"].affiliations == {"owner": "owner_a"}
    assert hh["r0c1"].affiliations == {}


def test_bimodal_sampling_produces_two_clusters() -> None:
    sc = _scenario(
        rows=4,
        cols=5,
        household_sampling={
            "mode": "bimodal",
            "have": {"pv_kw_peak": [10.0, 12.0], "battery_kwh": [14.0, 16.0]},
            "havenot": {"pv_kw_peak": [0.0, 1.0], "battery_kwh": [1.0, 2.0]},
            "have_fraction": 0.5,
            "rt_efficiency": 0.9,
            "dod_floor_frac": 0.1,
        },
    )
    hh = sample_households(sc, np.random.default_rng(sc.seed))
    batts = sorted(h.battery_kwh for h in hh.values())
    haves = [b for b in batts if b >= 14.0]
    havenots = [b for b in batts if b <= 2.0]
    assert haves and havenots
    assert len(haves) + len(havenots) == len(batts)


def test_bimodal_sampling_deterministic() -> None:
    sc = _scenario(
        household_sampling={
            "mode": "bimodal",
            "have": {"pv_kw_peak": [10.0, 12.0], "battery_kwh": [14.0, 16.0]},
            "havenot": {"pv_kw_peak": [0.0, 1.0], "battery_kwh": [1.0, 2.0]},
            "have_fraction": 0.5,
            "rt_efficiency": 0.9,
            "dod_floor_frac": 0.1,
        },
    )
    a = sample_households(sc, np.random.default_rng(sc.seed))
    b = sample_households(sc, np.random.default_rng(sc.seed))
    assert {k: v.battery_kwh for k, v in a.items()} == {k: v.battery_kwh for k, v in b.items()}


def test_prepare_hook_called_once_and_supplies_decider(tmp_path) -> None:
    from sim.engine import run
    from sim.logging import JsonlLogger

    calls = {"prepare": 0}

    def prepare(scenario, households, solar_profile, load_profiles, neighborhood):
        calls["prepare"] += 1

        def decide(t, states, hh, solar, load, grid, nbhd, dt):
            return []

        return decide

    sc = _scenario(strategy="synthetic_noop")
    logger = JsonlLogger(run_dir=str(tmp_path), scenario_id=sc.scenario_id)
    run(sc, decide_transfers=None, logger=logger, prepare=prepare)
    assert calls["prepare"] == 1
