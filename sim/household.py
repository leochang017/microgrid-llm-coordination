"""Household physics: solar + battery + load with constraints applied each tick."""
from __future__ import annotations

import math
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
    """Advance one tick honoring battery rate limits, SoC bounds, and RT efficiency.

    Round-trip efficiency is modeled as a sqrt(eta) factor on each leg: energy drawn
    from the grid/solar side is multiplied by sqrt(eta) when stored; energy released
    from the battery to load is also multiplied by sqrt(eta). A full charge-then-
    discharge cycle therefore returns eta * input to the load. RT loss is logged
    to wasted_kwh.

    Task 4 scope: rate clamps + SoC bounds + RT efficiency. Still ignores
    desired_net_export_kw and grid_status (Task 5 wires those up).
    """
    net_kw = solar_kw - load_kw
    net_kwh = net_kw * dt_hours
    sqrt_eff = math.sqrt(h.rt_efficiency)
    floor_kwh = h.dod_floor_frac * h.battery_kwh
    max_step_kwh = h.battery_max_rate_kw * dt_hours

    if net_kwh >= 0:
        # Charge: draw `gross_in` from surplus, store `gross_in * sqrt_eff` in battery.
        # Constraints: surplus available, battery rate, battery headroom.
        headroom_kwh = h.battery_kwh - s.soc_kwh
        max_drawable_for_storage = headroom_kwh / sqrt_eff if sqrt_eff > 0 else float("inf")
        gross_in = min(net_kwh, max_step_kwh, max_drawable_for_storage)
        stored = gross_in * sqrt_eff
        rt_loss = gross_in - stored
        surplus_overflow = net_kwh - gross_in   # solar surplus that couldn't enter the cycle
        wasted = rt_loss + surplus_overflow
        unmet = 0.0
        new_soc = s.soc_kwh + stored
    else:
        deficit_kwh = -net_kwh
        # Discharge: deliver up to deficit_kwh to the load. Drawing X delivers X*sqrt_eff.
        available_kwh = max(0.0, s.soc_kwh - floor_kwh)
        max_drawable = min(max_step_kwh, available_kwh)
        max_deliverable = max_drawable * sqrt_eff
        delivered = min(deficit_kwh, max_deliverable)
        drawn = delivered / sqrt_eff if sqrt_eff > 0 else 0.0
        rt_loss = drawn - delivered
        unmet = deficit_kwh - delivered
        wasted = rt_loss
        new_soc = s.soc_kwh - drawn

    return replace(
        s,
        soc_kwh=new_soc,
        last_solar_kw=solar_kw,
        last_load_kw=load_kw,
        grid_connected=grid_status,
        wasted_kwh=wasted,
        unmet_kwh=unmet,
    )
