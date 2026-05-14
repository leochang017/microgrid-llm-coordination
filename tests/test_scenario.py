"""Tests for scenario config loading and validation."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from sim.scenario import OutageWindow, Scenario, load_scenario

_SMOKE_YAML = """
scenario_id: synthetic_smoke
start: "2024-07-01T00:00:00"
end:   "2024-07-02T00:00:00"
dt_hours: 0.25
seed: 42
rows: 5
cols: 6
bus_max_kw: 50.0
bus_loss_factor: 0.05
strategy: no_coordination
data_source: synthetic
household_sampling:
  pv_kw_peak: [4.0, 12.0]
  battery_kwh: [10.0, 27.0]
  rt_efficiency: 0.9
  dod_floor_frac: 0.1
outages: []
"""


def test_load_smoke_scenario(tmp_path: Path) -> None:
    p = tmp_path / "synthetic.yaml"
    p.write_text(_SMOKE_YAML)
    s = load_scenario(p)
    assert s.scenario_id == "synthetic_smoke"
    assert s.start == datetime(2024, 7, 1)
    assert s.dt_hours == 0.25
    assert s.rows == 5
    assert s.cols == 6
    assert s.strategy == "no_coordination"
    assert s.outages == ()


def test_outage_window_validation() -> None:
    with pytest.raises(ValueError, match="end before start"):
        OutageWindow(
            start=datetime(2024, 7, 1, 10),
            end=datetime(2024, 7, 1, 9),
            affected_houses=("r0c0",),
        )


def test_load_rejects_end_before_start(tmp_path: Path) -> None:
    bad = _SMOKE_YAML.replace(
        'start: "2024-07-01T00:00:00"', 'start: "2024-07-02T00:00:00"'
    ).replace('end:   "2024-07-02T00:00:00"', 'end:   "2024-07-01T00:00:00"')
    p = tmp_path / "bad.yaml"
    p.write_text(bad)
    with pytest.raises(ValueError, match="end before start"):
        load_scenario(p)


def test_timesteps_count() -> None:
    s = Scenario(
        scenario_id="test",
        start=datetime(2024, 7, 1),
        end=datetime(2024, 7, 1) + timedelta(hours=1),
        dt_hours=0.25,
        seed=42,
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
        },
        outages=(),
    )
    assert list(s.timesteps()) == [
        datetime(2024, 7, 1, 0, 0),
        datetime(2024, 7, 1, 0, 15),
        datetime(2024, 7, 1, 0, 30),
        datetime(2024, 7, 1, 0, 45),
    ]


def test_grid_status_at_during_outage() -> None:
    """House in affected_houses is islanded during the outage window; others stay up."""
    outage = OutageWindow(
        start=datetime(2024, 7, 1, 8),
        end=datetime(2024, 7, 1, 12),
        affected_houses=("r0c0",),
    )
    s = Scenario(
        scenario_id="test",
        start=datetime(2024, 7, 1),
        end=datetime(2024, 7, 2),
        dt_hours=0.25,
        seed=42,
        rows=5,
        cols=6,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
        strategy="no_coordination",
        data_source="synthetic",
        household_sampling={},
        outages=(outage,),
    )
    # During outage, r0c0 is islanded; r0c1 stays connected.
    assert s.grid_status_at(datetime(2024, 7, 1, 10), "r0c0") is False
    assert s.grid_status_at(datetime(2024, 7, 1, 10), "r0c1") is True
    # Outside the outage window, r0c0 is connected.
    assert s.grid_status_at(datetime(2024, 7, 1, 6), "r0c0") is True
    assert s.grid_status_at(datetime(2024, 7, 1, 14), "r0c0") is True
