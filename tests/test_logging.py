"""Tests for run logging."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from sim.household import HouseholdState
from sim.logging import JsonlLogger, _gini
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
