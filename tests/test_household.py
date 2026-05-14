"""Tests for household physics: battery dynamics, constraints, energy accounting."""
import pytest

from sim.household import Household, HouseholdState, step
from sim.types import HouseholdProfile


def make_house(**overrides: object) -> Household:
    defaults: dict[str, object] = {
        "id": "h01",
        "pv_kw_peak": 8.0,
        "battery_kwh": 13.5,
        "battery_max_rate_kw": 5.0,
        "rt_efficiency": 1.0,  # disable for early tests
        "dod_floor_frac": 0.0,
        "grid_max_kw": 10.0,
        "profile": HouseholdProfile(description="test"),
    }
    defaults.update(overrides)
    return Household(**defaults)  # type: ignore[arg-type]


def test_charge_from_surplus_no_constraints() -> None:
    """Solar 4 kW, load 1 kW, dt 1 h, no transfer, no grid → battery gains 3 kWh."""
    h = make_house()
    s0 = HouseholdState(soc_kwh=5.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=True)
    s1 = step(
        h,
        s0,
        solar_kw=4.0,
        load_kw=1.0,
        desired_net_export_kw=0.0,
        grid_status=True,
        dt_hours=1.0,
    )
    assert s1.soc_kwh == pytest.approx(8.0, abs=1e-9)


def test_discharge_to_meet_load_no_constraints() -> None:
    """Solar 0 kW, load 2 kW, dt 0.25 h, no transfer → battery loses 0.5 kWh."""
    h = make_house()
    s0 = HouseholdState(soc_kwh=5.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    s1 = step(
        h,
        s0,
        solar_kw=0.0,
        load_kw=2.0,
        desired_net_export_kw=0.0,
        grid_status=False,
        dt_hours=0.25,
    )
    assert s1.soc_kwh == pytest.approx(4.5, abs=1e-9)
