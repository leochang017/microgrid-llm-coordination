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
    wasted_kwh: float = 0.0  # surplus that couldn't fit (curtailed solar or over-rate charge)
    unmet_kwh: float = 0.0  # deficit that couldn't be served (DoD-floor or under-rate discharge)
    grid_import_kwh: float = 0.0
    grid_export_kwh: float = 0.0
    achieved_net_export_kw: float = 0.0  # what the network actually saw leaving this house


def step(
    h: Household,
    s: HouseholdState,
    solar_kw: float,
    load_kw: float,
    desired_net_export_kw: float,
    grid_status: bool,
    dt_hours: float,
) -> HouseholdState:
    """Advance one tick honoring desired_net_export_kw and grid_status.

    Convention: positive desired_net_export_kw means this house sends energy out
    to peers; negative means it receives. The engine has already validated the
    desired value against per-house caps before calling step(), so in normal
    operation no shortfall occurs. The shortfall branch below is a safety net.

    Local energy after meeting load AND honoring the desired export is
    `surplus_kwh = (solar - load - desired_net_export) * dt`. If positive we
    try to store it in the battery and then export to the grid (when connected);
    if negative we source the deficit from battery first, then grid (when
    connected), with anything still missing reported as unmet load.
    """
    sqrt_eff = math.sqrt(h.rt_efficiency)
    floor_kwh = h.dod_floor_frac * h.battery_kwh
    max_step_kwh = h.battery_max_rate_kw * dt_hours
    max_grid_kwh = h.grid_max_kw * dt_hours

    surplus_kwh = (solar_kw - load_kw - desired_net_export_kw) * dt_hours

    grid_import = 0.0
    grid_export = 0.0

    if surplus_kwh >= 0:
        # 1. Store as much as we can in the battery (subject to rate + headroom + RT).
        headroom_kwh = h.battery_kwh - s.soc_kwh
        max_drawable_for_storage = headroom_kwh / sqrt_eff if sqrt_eff > 0 else float("inf")
        gross_in = min(surplus_kwh, max_step_kwh, max_drawable_for_storage)
        stored = gross_in * sqrt_eff
        rt_loss = gross_in - stored
        leftover = surplus_kwh - gross_in
        # 2. Export leftover to grid (if connected); else curtailed.
        if grid_status:
            grid_export = min(leftover, max_grid_kwh)
            wasted = (leftover - grid_export) + rt_loss
        else:
            wasted = leftover + rt_loss
        unmet = 0.0
        new_soc = s.soc_kwh + stored
        achieved_net_export_kw = desired_net_export_kw
    else:
        deficit_kwh = -surplus_kwh
        # 1. Source from battery (subject to rate + DoD floor + RT).
        available_kwh = max(0.0, s.soc_kwh - floor_kwh)
        max_drawable = min(max_step_kwh, available_kwh)
        max_deliverable = max_drawable * sqrt_eff
        delivered_from_battery = min(deficit_kwh, max_deliverable)
        drawn = delivered_from_battery / sqrt_eff if sqrt_eff > 0 else 0.0
        rt_loss = drawn - delivered_from_battery
        remaining_deficit = deficit_kwh - delivered_from_battery
        # 2. Source from grid (if connected).
        if grid_status and remaining_deficit > 0:
            grid_import = min(remaining_deficit, max_grid_kwh)
            remaining_deficit -= grid_import
        # 3. Anything still unsourced is a shortfall.
        wasted = rt_loss
        if remaining_deficit > 0 and desired_net_export_kw > 0:
            # Shortfall first reduces the export (we couldn't deliver to peers).
            export_short_kwh = min(remaining_deficit, desired_net_export_kw * dt_hours)
            achieved_net_export_kw = desired_net_export_kw - export_short_kwh / dt_hours
            unmet = remaining_deficit - export_short_kwh  # remainder is unmet load
        else:
            achieved_net_export_kw = desired_net_export_kw
            unmet = remaining_deficit
        new_soc = s.soc_kwh - drawn

    return replace(
        s,
        soc_kwh=new_soc,
        last_solar_kw=solar_kw,
        last_load_kw=load_kw,
        grid_connected=grid_status,
        wasted_kwh=wasted,
        unmet_kwh=unmet,
        grid_import_kwh=grid_import,
        grid_export_kwh=grid_export,
        achieved_net_export_kw=achieved_net_export_kw,
    )
