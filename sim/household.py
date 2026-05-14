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
    wasted_kwh: float = 0.0   # surplus that couldn't fit (curtailed solar or over-rate charge)
    unmet_kwh: float = 0.0    # deficit that couldn't be served (DoD-floor or under-rate discharge)


def step(
    h: Household,
    s: HouseholdState,
    solar_kw: float,
    load_kw: float,
    desired_net_export_kw: float,
    grid_status: bool,
    dt_hours: float,
) -> HouseholdState:
    """Advance one tick honoring battery rate limits and SoC bounds.

    Task 3 scope: rate clamping + capacity ceiling + DoD floor. Still ignores
    desired_net_export_kw, grid_status, and RT efficiency (Tasks 4-5 wire those up).
    """
    net_kw = solar_kw - load_kw
    if net_kw >= 0:
        charge_kw = min(net_kw, h.battery_max_rate_kw)
        wasted_from_rate = (net_kw - charge_kw) * dt_hours
        headroom_kwh = h.battery_kwh - s.soc_kwh
        delivered_kwh = min(charge_kw * dt_hours, headroom_kwh)
        wasted_from_capacity = max(0.0, charge_kw * dt_hours - headroom_kwh)
        new_soc = s.soc_kwh + delivered_kwh
        wasted = wasted_from_rate + wasted_from_capacity
        unmet = 0.0
    else:
        discharge_kw = min(-net_kw, h.battery_max_rate_kw)
        unmet_from_rate = (-net_kw - discharge_kw) * dt_hours
        floor_kwh = h.dod_floor_frac * h.battery_kwh
        available_kwh = max(0.0, s.soc_kwh - floor_kwh)
        drawn_kwh = min(discharge_kw * dt_hours, available_kwh)
        unmet_from_floor = max(0.0, discharge_kw * dt_hours - available_kwh)
        new_soc = s.soc_kwh - drawn_kwh
        unmet = unmet_from_rate + unmet_from_floor
        wasted = 0.0

    return replace(
        s,
        soc_kwh=new_soc,
        last_solar_kw=solar_kw,
        last_load_kw=load_kw,
        grid_connected=grid_status,
        wasted_kwh=wasted,
        unmet_kwh=unmet,
    )
