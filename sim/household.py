"""Household physics: solar + battery + load with constraints applied each tick."""
from __future__ import annotations

from dataclasses import dataclass, replace

from sim.types import HouseholdProfile


@dataclass(frozen=True, slots=True)
class Household:
    """Static properties of one household."""

    id: str
    pv_kw_peak: float
    battery_kwh: float
    battery_max_rate_kw: float
    rt_efficiency: float
    dod_floor_frac: float
    grid_max_kw: float
    profile: HouseholdProfile


@dataclass(frozen=True, slots=True)
class HouseholdState:
    """Mutable state of one household at a point in time."""

    soc_kwh: float
    last_solar_kw: float
    last_load_kw: float
    grid_connected: bool


def step(
    h: Household,
    s: HouseholdState,
    solar_kw: float,
    load_kw: float,
    desired_net_export_kw: float,
    grid_status: bool,
    dt_hours: float,
) -> HouseholdState:
    """Advance one tick. Returns the new state.

    For Task 2, we ignore desired_net_export_kw, grid_status, rate limits, RT
    efficiency, and DoD floor. Pure solar-vs-load battery bookkeeping.
    """
    net_kw = solar_kw - load_kw
    new_soc = s.soc_kwh + net_kw * dt_hours
    return replace(
        s,
        soc_kwh=new_soc,
        last_solar_kw=solar_kw,
        last_load_kw=load_kw,
        grid_connected=grid_status,
    )
