"""Simulation engine: builds households, owns the clock, drives the per-tick loop.

sample_households builds the deterministic neighborhood; run() drives the
per-tick simulation loop.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime
from typing import Any

import numpy as np

from sim.data import LoadProfile, SolarProfile, SyntheticLoad, SyntheticSolar
from sim.household import Household, HouseholdState, step
from sim.logging import JsonlLogger
from sim.network import Neighborhood, build_grid_neighborhood, settle_transfers
from sim.scenario import Scenario
from sim.types import Event, EventKind, HouseholdProfile, Transfer

DecideFn = Callable[
    [
        datetime,
        dict[str, HouseholdState],
        dict[str, Household],
        dict[str, float],
        dict[str, float],
        dict[str, bool],
        Neighborhood,
        float,
    ],
    list[Transfer],
]


def sample_households(scenario: Scenario, rng: np.random.Generator) -> dict[str, Household]:
    """Build the rows by cols Household objects from the scenario's sampling config.

    Deterministic given the same scenario.seed: PV size, battery capacity, and
    derived charge rate are drawn from uniform distributions parameterized by
    `scenario.household_sampling`.
    """
    sampling = scenario.household_sampling
    pv_lo, pv_hi = sampling["pv_kw_peak"]
    bat_lo, bat_hi = sampling["battery_kwh"]
    rt_eff = float(sampling["rt_efficiency"])
    dod = float(sampling["dod_floor_frac"])
    grid_max = float(sampling.get("grid_max_kw", 10.0))

    households: dict[str, Household] = {}
    for r in range(scenario.rows):
        for c in range(scenario.cols):
            hid = f"r{r}c{c}"
            pv = float(rng.uniform(pv_lo, pv_hi))
            batt = float(rng.uniform(bat_lo, bat_hi))
            rate = batt / 5.0  # standard residential ratio: full charge in ~5 h
            households[hid] = Household(
                id=hid,
                pv_kw_peak=pv,
                battery_kwh=batt,
                battery_max_rate_kw=rate,
                rt_efficiency=rt_eff,
                dod_floor_frac=dod,
                grid_max_kw=grid_max,
                profile=HouseholdProfile(description=f"household {hid}"),
            )
    return households


def run(
    scenario: Scenario,
    decide_transfers: DecideFn,
    logger: JsonlLogger,
    *,
    strict: bool = True,
) -> dict[str, Any]:
    """Drive the simulation: per-tick lookup -> decide -> settle -> step -> log.

    Steps per tick:
      1. Look up solar(t) and load(t) per house from the data adapters.
      2. Look up grid status per house from the outage schedule.
      3. Emit OUTAGE_STARTED / OUTAGE_ENDED events on transitions.
      4. Call decide_transfers to get the strategy's requested transfers.
      5. Compute per-house sender_caps_kw / receiver_caps_kw from current state.
      6. Call settle_transfers to clip to physical limits + get events.
      7. Call step() per house with the actual achieved net export.
      8. In strict mode, assert SoC bounds + non-negative wasted/unmet.
      9. Log state + events.

    Returns the summary dict from logger.finalize().
    """
    rng = np.random.default_rng(scenario.seed)
    households = sample_households(scenario, rng)
    neighborhood = build_grid_neighborhood(
        rows=scenario.rows,
        cols=scenario.cols,
        bus_max_kw=scenario.bus_max_kw,
        bus_loss_factor=scenario.bus_loss_factor,
    )

    solar_profile, load_profiles = _build_data(scenario, households)

    # Initialize states: every battery starts at 50% capacity, every house
    # presumed grid-connected at t=0 unless the outage schedule says otherwise.
    states: dict[str, HouseholdState] = {}
    last_grid_status: dict[str, bool] = {}
    for hid, h in households.items():
        initial_grid = scenario.grid_status_at(scenario.start, hid)
        states[hid] = HouseholdState(
            soc_kwh=0.5 * h.battery_kwh,
            last_solar_kw=0.0,
            last_load_kw=0.0,
            grid_connected=initial_grid,
        )
        last_grid_status[hid] = initial_grid

    logger.write_config(
        {
            "scenario_id": scenario.scenario_id,
            "start": scenario.start.isoformat(),
            "end": scenario.end.isoformat(),
            "dt_hours": scenario.dt_hours,
            "seed": scenario.seed,
            "rows": scenario.rows,
            "cols": scenario.cols,
            "bus_max_kw": scenario.bus_max_kw,
            "bus_loss_factor": scenario.bus_loss_factor,
            "strategy": scenario.strategy,
            "data_source": scenario.data_source,
            "household_sampling": scenario.household_sampling,
            "outages": [
                {
                    "start": o.start.isoformat(),
                    "end": o.end.isoformat(),
                    "affected_houses": list(o.affected_houses),
                }
                for o in scenario.outages
            ],
            "strict": strict,
        }
    )

    for t in scenario.timesteps():
        solar_kw = {hid: solar_profile.get_kw(t) * h.pv_kw_peak for hid, h in households.items()}
        load_kw = {hid: load_profiles[hid].get_kw(t) for hid in households}
        grid = {hid: scenario.grid_status_at(t, hid) for hid in households}

        outage_events: list[Event] = []
        for hid in households:
            if last_grid_status[hid] != grid[hid]:
                outage_events.append(
                    Event(
                        kind=EventKind.OUTAGE_ENDED if grid[hid] else EventKind.OUTAGE_STARTED,
                        house_ids=(hid,),
                    )
                )
            last_grid_status[hid] = grid[hid]

        requested = decide_transfers(
            t, states, households, solar_kw, load_kw, grid, neighborhood, scenario.dt_hours
        )

        # Per-house caps. Sender cap (kW out) is limited by battery rate AND
        # the energy available above the DoD floor (accounting for the sqrt(eta)
        # discharge leg). Receiver cap (kW in) is limited by battery rate AND
        # the headroom to capacity (accounting for the sqrt(eta) charge leg).
        sender_caps_kw: dict[str, float] = {}
        receiver_caps_kw: dict[str, float] = {}
        for hid, h in households.items():
            s = states[hid]
            sqrt_eff = math.sqrt(h.rt_efficiency)
            available_kwh = max(0.0, s.soc_kwh - h.dod_floor_frac * h.battery_kwh)
            sender_caps_kw[hid] = min(
                h.battery_max_rate_kw,
                available_kwh * sqrt_eff / scenario.dt_hours if scenario.dt_hours > 0 else 0.0,
            )
            headroom_kwh = h.battery_kwh - s.soc_kwh
            receiver_cap_rate = h.battery_max_rate_kw
            receiver_cap_headroom = (
                headroom_kwh / (sqrt_eff * scenario.dt_hours)
                if sqrt_eff > 0 and scenario.dt_hours > 0
                else 0.0
            )
            receiver_caps_kw[hid] = min(receiver_cap_rate, receiver_cap_headroom)

        settlement = settle_transfers(
            neighborhood, requested, grid, sender_caps_kw, receiver_caps_kw
        )

        new_states: dict[str, HouseholdState] = {}
        for hid, h in households.items():
            net_export_kw = settlement.actual_sent[hid] - settlement.actual_received[hid]
            new_s = step(
                h,
                states[hid],
                solar_kw[hid],
                load_kw[hid],
                desired_net_export_kw=net_export_kw,
                grid_status=grid[hid],
                dt_hours=scenario.dt_hours,
            )
            if strict:
                floor = h.dod_floor_frac * h.battery_kwh
                assert (
                    floor - 1e-6 <= new_s.soc_kwh <= h.battery_kwh + 1e-6
                ), f"SoC out of bounds at {t} for {hid}: {new_s.soc_kwh}"
                assert new_s.wasted_kwh >= -1e-9
                assert new_s.unmet_kwh >= -1e-9
            new_states[hid] = new_s
        states = new_states

        logger.write_state(t, states, solar_kw, load_kw, grid)
        logger.write_events(outage_events + settlement.events, t=t)

    return logger.finalize(dt_hours=scenario.dt_hours)


def _build_data(
    scenario: Scenario, households: dict[str, Household]
) -> tuple[SolarProfile, dict[str, LoadProfile]]:
    """Dispatch on scenario.data_source to build the solar + per-house load adapters.

    Returns (solar_profile, load_profiles_by_house_id). The engine scales solar
    per-house by pv_kw_peak.
    """
    if scenario.data_source == "synthetic":
        solar: SolarProfile = SyntheticSolar(peak_kw=1.0)
        loads: dict[str, LoadProfile] = {hid: SyntheticLoad(base_kw=1.5) for hid in households}
        return solar, loads

    if scenario.data_source == "pecan_street":
        # Local imports keep the synthetic-only path from depending on pandas.
        from sim.adapters.nrel_solar import NRELSolar
        from sim.adapters.pecan_street import PecanStreetLoad

        if "solar_csv" not in scenario.data_paths or "load_csv" not in scenario.data_paths:
            raise ValueError(
                "data_source=pecan_street requires scenario.data_paths.solar_csv "
                "and scenario.data_paths.load_csv"
            )
        if len(scenario.house_dataids) != scenario.rows * scenario.cols:
            raise ValueError(
                f"house_dataids has {len(scenario.house_dataids)} entries, "
                f"need {scenario.rows * scenario.cols}"
            )
        nrel = NRELSolar(csv_path=scenario.data_paths["solar_csv"], seed=scenario.seed)
        load_map: dict[str, LoadProfile] = {}
        for (hid, _), dataid in zip(households.items(), scenario.house_dataids, strict=True):
            load_map[hid] = PecanStreetLoad(csv_path=scenario.data_paths["load_csv"], dataid=dataid)
        return nrel, load_map

    raise ValueError(f"unknown data_source: {scenario.data_source!r}")
