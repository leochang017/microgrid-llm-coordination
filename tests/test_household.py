"""Tests for household physics: battery dynamics, constraints, energy accounting."""

import math

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
    assert s1.wasted_kwh == 0.0
    assert s1.unmet_kwh == 0.0


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
    assert s1.wasted_kwh == 0.0
    assert s1.unmet_kwh == 0.0


def test_charge_clamps_to_battery_max_rate() -> None:
    """Solar surplus of 20 kW exceeds 5 kW battery rate → 5 kWh charged, 15 kWh wasted."""
    h = make_house(battery_max_rate_kw=5.0)
    s0 = HouseholdState(soc_kwh=5.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    s1 = step(
        h,
        s0,
        solar_kw=20.0,
        load_kw=0.0,
        desired_net_export_kw=0.0,
        grid_status=False,
        dt_hours=1.0,
    )
    assert s1.soc_kwh == pytest.approx(10.0, abs=1e-9)
    assert s1.wasted_kwh == pytest.approx(15.0, abs=1e-9)
    assert s1.unmet_kwh == pytest.approx(0.0, abs=1e-9)


def test_discharge_clamps_to_battery_max_rate() -> None:
    """Load deficit of 20 kW exceeds 5 kW battery rate → 5 kWh discharged, 15 kWh unmet."""
    h = make_house(battery_max_rate_kw=5.0)
    s0 = HouseholdState(soc_kwh=10.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    s1 = step(
        h,
        s0,
        solar_kw=0.0,
        load_kw=20.0,
        desired_net_export_kw=0.0,
        grid_status=False,
        dt_hours=1.0,
    )
    assert s1.soc_kwh == pytest.approx(5.0, abs=1e-9)
    assert s1.unmet_kwh == pytest.approx(15.0, abs=1e-9)
    assert s1.wasted_kwh == pytest.approx(0.0, abs=1e-9)


def test_soc_clamped_at_capacity() -> None:
    """Charging a full battery wastes the energy."""
    h = make_house(battery_kwh=10.0, battery_max_rate_kw=5.0)
    s0 = HouseholdState(soc_kwh=9.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    s1 = step(
        h,
        s0,
        solar_kw=5.0,
        load_kw=0.0,
        desired_net_export_kw=0.0,
        grid_status=False,
        dt_hours=1.0,
    )
    assert s1.soc_kwh == pytest.approx(10.0, abs=1e-9)
    assert s1.wasted_kwh == pytest.approx(4.0, abs=1e-9)


def test_soc_clamped_at_dod_floor() -> None:
    """Discharging past DoD floor leaves the deficit as unmet."""
    h = make_house(battery_kwh=10.0, battery_max_rate_kw=5.0, dod_floor_frac=0.1)
    s0 = HouseholdState(soc_kwh=1.5, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    s1 = step(
        h,
        s0,
        solar_kw=0.0,
        load_kw=5.0,
        desired_net_export_kw=0.0,
        grid_status=False,
        dt_hours=1.0,
    )
    assert s1.soc_kwh == pytest.approx(1.0, abs=1e-9)  # floor = 0.1 * 10
    assert s1.unmet_kwh == pytest.approx(4.5, abs=1e-9)


def test_rt_efficiency_on_charge() -> None:
    """rt_efficiency=0.9: 10 kWh solar surplus → sqrt(0.9) * 10 = ~9.487 kWh stored."""
    h = make_house(rt_efficiency=0.9, battery_max_rate_kw=20.0)
    s0 = HouseholdState(soc_kwh=0.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    s1 = step(
        h,
        s0,
        solar_kw=10.0,
        load_kw=0.0,
        desired_net_export_kw=0.0,
        grid_status=False,
        dt_hours=1.0,
    )
    expected = math.sqrt(0.9) * 10.0
    assert s1.soc_kwh == pytest.approx(expected, abs=1e-6)
    # Energy "lost" to RT inefficiency is logged as wasted.
    assert s1.wasted_kwh == pytest.approx(10.0 - expected, abs=1e-6)


def test_rt_efficiency_full_cycle() -> None:
    """Charge X kWh into the battery, drain it: end up with eta * X served to load."""
    h = make_house(rt_efficiency=0.9, battery_max_rate_kw=20.0, battery_kwh=20.0)
    s = HouseholdState(soc_kwh=0.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    # Charge for 1 hour at 10 kW
    s = step(
        h, s, solar_kw=10.0, load_kw=0.0, desired_net_export_kw=0.0, grid_status=False, dt_hours=1.0
    )
    soc_after_charge = s.soc_kwh
    # Discharge what's in the battery (large enough load to drain it fully)
    s = step(
        h, s, solar_kw=0.0, load_kw=20.0, desired_net_export_kw=0.0, grid_status=False, dt_hours=1.0
    )
    # Original input was 10 kWh; full cycle returns 0.9 * 10 = 9 kWh to the load.
    delivered_to_load = math.sqrt(0.9) * soc_after_charge
    assert delivered_to_load == pytest.approx(9.0, abs=1e-6)


def test_export_to_peers_drains_battery() -> None:
    """Solar 0, load 0, export 4 kW for 0.25 h, eta=1, dod=0 -> 1 kWh leaves battery."""
    h = make_house(rt_efficiency=1.0, dod_floor_frac=0.0)
    s0 = HouseholdState(soc_kwh=10.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    s1 = step(
        h,
        s0,
        solar_kw=0.0,
        load_kw=0.0,
        desired_net_export_kw=4.0,
        grid_status=False,
        dt_hours=0.25,
    )
    assert s1.soc_kwh == pytest.approx(9.0, abs=1e-9)
    assert s1.grid_import_kwh == 0.0
    assert s1.grid_export_kwh == 0.0


def test_grid_fills_unmet_load_when_connected() -> None:
    """No solar, load 5 kW for 1 h, battery empty, grid up -> grid_import = 5 kWh."""
    h = make_house(battery_max_rate_kw=5.0, grid_max_kw=10.0)
    s0 = HouseholdState(soc_kwh=0.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=True)
    s1 = step(
        h,
        s0,
        solar_kw=0.0,
        load_kw=5.0,
        desired_net_export_kw=0.0,
        grid_status=True,
        dt_hours=1.0,
    )
    assert s1.unmet_kwh == 0.0
    assert s1.grid_import_kwh == pytest.approx(5.0, abs=1e-9)


def test_grid_disconnected_leaves_deficit_unmet() -> None:
    """Same setup but grid down -> unmet = 5 kWh, no grid import."""
    h = make_house(battery_max_rate_kw=5.0, grid_max_kw=10.0, dod_floor_frac=0.0)
    s0 = HouseholdState(soc_kwh=0.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    s1 = step(
        h,
        s0,
        solar_kw=0.0,
        load_kw=5.0,
        desired_net_export_kw=0.0,
        grid_status=False,
        dt_hours=1.0,
    )
    assert s1.unmet_kwh == pytest.approx(5.0, abs=1e-9)
    assert s1.grid_import_kwh == 0.0


def test_household_affiliations_default_empty() -> None:
    h = Household(
        id="r0c0",
        pv_kw_peak=5.0,
        battery_kwh=10.0,
        battery_max_rate_kw=2.0,
        rt_efficiency=0.9,
        dod_floor_frac=0.1,
        grid_max_kw=10.0,
        profile=HouseholdProfile(description="x"),
    )
    assert h.affiliations == {}


def test_household_affiliations_settable() -> None:
    h = Household(
        id="r0c0",
        pv_kw_peak=5.0,
        battery_kwh=10.0,
        battery_max_rate_kw=2.0,
        rt_efficiency=0.9,
        dod_floor_frac=0.1,
        grid_max_kw=10.0,
        profile=HouseholdProfile(description="x"),
        affiliations={"owner": "owner_acme", "hoa": "hoa_north"},
    )
    assert h.affiliations["owner"] == "owner_acme"
