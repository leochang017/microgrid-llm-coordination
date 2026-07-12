"""Tests for run logging."""

import importlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from sim.engine import run
from sim.household import HouseholdState
from sim.logging import JsonlLogger, _gini
from sim.scenario import load_scenario
from sim.types import Event, EventKind


def test_logger_writes_state_rows(tmp_path: Path) -> None:
    out = tmp_path / "run"
    lg = JsonlLogger(out, scenario_id="test")
    states = {
        "r0c0": HouseholdState(
            soc_kwh=5.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=True
        ),
        "r0c1": HouseholdState(
            soc_kwh=3.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=True
        ),
    }
    solar = {"r0c0": 4.0, "r0c1": 4.0}
    load = {"r0c0": 1.0, "r0c1": 1.0}
    grid = {"r0c0": True, "r0c1": True}
    lg.write_state(datetime(2024, 7, 1, 0, 0), states, solar, load, grid)
    lg.close()

    lines = (out / "state.jsonl").read_text().splitlines()
    assert len(lines) == 2
    row = json.loads(lines[0])
    assert {"t", "house_id", "soc_kwh", "solar_kw", "load_kw", "grid_status"} <= row.keys()


def test_logger_writes_events(tmp_path: Path) -> None:
    out = tmp_path / "run"
    lg = JsonlLogger(out, scenario_id="test")
    events = [Event(kind=EventKind.OUTAGE_STARTED, house_ids=("r0c0",))]
    lg.write_events(events, t=datetime(2024, 7, 1, 0, 0))
    lg.close()

    lines = (out / "events.jsonl").read_text().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["kind"] == "outage_started"
    assert row["house_ids"] == ["r0c0"]


def test_logger_creates_config_json(tmp_path: Path) -> None:
    out = tmp_path / "run"
    lg = JsonlLogger(out, scenario_id="test")
    lg.write_config({"foo": "bar"})
    lg.close()
    cfg = json.loads((out / "config.json").read_text())
    assert cfg == {"foo": "bar"}


def test_finalize_writes_summary(tmp_path: Path) -> None:
    out = tmp_path / "run"
    lg = JsonlLogger(out, scenario_id="test")
    t0 = datetime(2024, 7, 1, 0, 0)
    states = {
        "r0c0": HouseholdState(
            soc_kwh=5.0,
            last_solar_kw=0.0,
            last_load_kw=2.0,
            grid_connected=False,
            unmet_kwh=0.5,
        ),
        "r0c1": HouseholdState(
            soc_kwh=3.0,
            last_solar_kw=0.0,
            last_load_kw=2.0,
            grid_connected=False,
            unmet_kwh=0.0,
        ),
    }
    lg.write_state(
        t0,
        states,
        {"r0c0": 0.0, "r0c1": 0.0},
        {"r0c0": 2.0, "r0c1": 2.0},
        {"r0c0": False, "r0c1": False},
    )
    summary = lg.finalize(dt_hours=0.25)
    lg.close()

    cfg = json.loads((out / "summary.json").read_text())
    assert cfg["scenario_id"] == "test"
    # Load each: 2 kW * 0.25 h = 0.5 kWh per house; total load 1.0; total unmet 0.5.
    assert cfg["served_load_fraction"] == pytest.approx(0.5, abs=1e-6)
    assert cfg["unmet_kwh_total"] == pytest.approx(0.5, abs=1e-6)
    assert cfg["transfer_count"] == 0
    assert "gini_welfare" in cfg
    assert summary == cfg


class TestGini:
    """Hand-computed pins for the paper's headline fairness metric —
    previously only presence-checked, so a formula regression (dropping the
    (n+1)/n term, forgetting the sort) would have passed the whole suite."""

    def test_perfectly_equal_is_zero(self) -> None:
        assert _gini([1.0, 1.0, 1.0]) == pytest.approx(0.0, abs=1e-12)

    def test_two_values_one_zero(self) -> None:
        assert _gini([0.0, 1.0]) == pytest.approx(0.5, abs=1e-12)

    def test_three_values_one_nonzero(self) -> None:
        assert _gini([0.0, 0.0, 1.0]) == pytest.approx(2.0 / 3.0, abs=1e-12)

    def test_four_value_hand_case(self) -> None:
        # sorted [1,2,3,4]: cum = 1+4+9+16 = 30; 60/(4*10) - 5/4 = 1.5-1.25
        assert _gini([3.0, 1.0, 4.0, 2.0]) == pytest.approx(0.25, abs=1e-12)

    def test_unsorted_input_is_sorted_internally(self) -> None:
        assert _gini([1.0, 0.0]) == _gini([0.0, 1.0])

    def test_empty_and_all_zero_return_zero(self) -> None:
        assert _gini([]) == 0.0
        assert _gini([0.0, 0.0]) == 0.0


class TestNeedsAwareMetrics:
    """Phase 3 fairness substrate: Jain's index, Rawlsian floor, critical load."""

    def test_jains_index_hand_cases(self) -> None:
        from sim.logging import _jains_index

        assert _jains_index([1.0, 1.0, 1.0, 1.0]) == pytest.approx(1.0)
        assert _jains_index([1.0, 0.0]) == pytest.approx(0.5)
        # (1.5)^2 / (2 * 1.25) = 0.9
        assert _jains_index([1.0, 0.5]) == pytest.approx(0.9)
        assert _jains_index([]) == 1.0
        assert _jains_index([0.0, 0.0]) == 1.0

    def test_served_critical_fraction_flexible_absorbs_first(self) -> None:
        from sim.logging import _served_critical_fraction

        # House h1: load 10, critical 40% (4 kWh critical, 6 flexible).
        # Unmet 5 -> flexible absorbs 5... wait 5 < 6, so critical untouched.
        assert _served_critical_fraction({"h1": 10.0}, {"h1": 5.0}, {"h1": 0.4}) == 1.0
        # Unmet 8 -> flexible absorbs 6, critical loses 2 of 4 -> 50% served.
        assert _served_critical_fraction({"h1": 10.0}, {"h1": 8.0}, {"h1": 0.4}) == pytest.approx(
            0.5
        )
        # No critical load configured anywhere -> defined as 1.0.
        assert _served_critical_fraction({"h1": 10.0}, {"h1": 8.0}, {}) == 1.0


def test_min_house_served_fraction_matches_state_log(tmp_path: Path) -> None:
    sc = load_scenario("configs/scenarios/synthetic_lp_smoke.yaml")
    mod = importlib.import_module(f"sim.strategies.{sc.strategy}")
    logger = JsonlLogger(run_dir=tmp_path / "r", scenario_id=sc.scenario_id)
    summary = run(
        sc,
        getattr(mod, "decide_transfers", None),
        logger,
        prepare=getattr(mod, "prepare", None),
    )
    logger.close()
    load, unmet = {}, {}
    for line in (tmp_path / "r" / "state.jsonl").read_text().splitlines():
        row = json.loads(line)
        load[row["house_id"]] = load.get(row["house_id"], 0.0) + row["load_kw"] * sc.dt_hours
        unmet[row["house_id"]] = unmet.get(row["house_id"], 0.0) + row["unmet_kwh"]
    expected = min((load[h] - unmet[h]) / load[h] if load[h] > 0 else 1.0 for h in load)
    assert summary["min_house_served_fraction"] == pytest.approx(expected)
