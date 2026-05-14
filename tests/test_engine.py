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
