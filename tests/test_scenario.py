"""Tests for scenario config loading and validation."""

import textwrap
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


def test_scenario_rejects_nonpositive_dt_hours() -> None:
    with pytest.raises(ValueError, match="dt_hours must be positive"):
        Scenario(
            scenario_id="bad",
            start=datetime(2024, 7, 1),
            end=datetime(2024, 7, 2),
            dt_hours=0.0,
            seed=0,
            rows=5,
            cols=6,
            bus_max_kw=50.0,
            bus_loss_factor=0.05,
            strategy="no_coordination",
            data_source="synthetic",
            household_sampling={},
            outages=(),
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


_AFFIL_BASE = """
scenario_id: t
start: "2018-01-01T00:00:00"
end: "2018-01-01T06:00:00"
dt_hours: 0.25
seed: 1
rows: 2
cols: 2
bus_max_kw: 50.0
strategy: round_robin
data_source: synthetic
household_sampling:
  pv_kw_peak: [4.0, 8.0]
  battery_kwh: [5.0, 10.0]
  rt_efficiency: 0.9
  dod_floor_frac: 0.1
"""


def _write_affil(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "s.yaml"
    p.write_text(textwrap.dedent(body))
    return p


def test_affiliations_parsed_into_nested_tuples(tmp_path: Path) -> None:
    p = _write_affil(
        tmp_path,
        _AFFIL_BASE
        + """
affiliations:
  owner:
    owner_a: [r0c0, r1c1]
""",
    )
    sc = load_scenario(p)
    assert sc.affiliations == {"owner": {"owner_a": ("r0c0", "r1c1")}}


def test_affiliations_default_empty(tmp_path: Path) -> None:
    sc = load_scenario(_write_affil(tmp_path, _AFFIL_BASE))
    assert sc.affiliations == {}


def test_affiliations_rejects_unknown_house(tmp_path: Path) -> None:
    p = _write_affil(
        tmp_path,
        _AFFIL_BASE
        + """
affiliations:
  owner:
    owner_a: [r0c0, r9c9]
""",
    )
    with pytest.raises(ValueError, match="r9c9"):
        load_scenario(p)


# --- Phase 2 failure_modes + llm YAML parsing tests ---


def test_scenario_parses_failure_modes_block(tmp_path: Path) -> None:
    body = (
        _AFFIL_BASE
        + """
failure_modes:
  defector_fraction: 0.2
  obs_noise:
    soc_std_frac: 0.05
  comm:
    per_tick_budget: 5
    drop_prob_by_circle:
      geographic: 0.1
llm:
  model: claude-haiku-4-5-20251001
  policy_refresh_every_ticks: 4
  react_max_per_tick: 3
  require_rationale: true
"""
    )
    s = load_scenario(_write_affil(tmp_path, body))
    assert s.failure_modes.defector_fraction == 0.2
    assert s.failure_modes.obs_noise.soc_std_frac == 0.05
    assert s.failure_modes.comm.per_tick_budget == 5
    assert s.failure_modes.comm.drop_prob_by_circle["geographic"] == 0.1
    assert s.llm["model"] == "claude-haiku-4-5-20251001"
    assert s.llm["policy_refresh_every_ticks"] == 4


def test_scenario_omitting_failure_modes_block_uses_defaults(tmp_path: Path) -> None:
    s = load_scenario(_write_affil(tmp_path, _AFFIL_BASE))
    assert s.failure_modes.defector_fraction == 0.0
    assert s.llm == {}
