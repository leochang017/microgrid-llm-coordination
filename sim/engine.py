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

from sim.agents.protocol import MessageBus
from sim.data import LoadProfile, SolarProfile, SyntheticLoad, SyntheticSolar
from sim.household import Household, HouseholdState, step
from sim.logging import JsonlLogger
from sim.network import Neighborhood, build_overlay_neighborhood, settle_transfers
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

PrepareFn = Callable[..., DecideFn]


def sample_households(scenario: Scenario, rng: np.random.Generator) -> dict[str, Household]:
    """Build the rows by cols Household objects from the scenario's sampling config.

    Deterministic given the same scenario.seed: PV size, battery capacity, and
    derived charge rate are drawn from uniform distributions parameterized by
    `scenario.household_sampling`.
    """
    sampling = scenario.household_sampling
    rt_eff = float(sampling["rt_efficiency"])
    dod = float(sampling["dod_floor_frac"])
    grid_max = float(sampling.get("grid_max_kw", 10.0))
    mode = str(sampling.get("mode", "uniform"))

    def _draw_pv_batt() -> tuple[float, float]:
        if mode == "bimodal":
            cluster = (
                sampling["have"]
                if rng.random() < float(sampling["have_fraction"])
                else sampling["havenot"]
            )
            return (
                float(rng.uniform(*cluster["pv_kw_peak"])),
                float(rng.uniform(*cluster["battery_kwh"])),
            )
        return (
            float(rng.uniform(*sampling["pv_kw_peak"])),
            float(rng.uniform(*sampling["battery_kwh"])),
        )

    # Invert scenario.affiliations (type -> group -> houses) to per-house (type -> group).
    house_affil: dict[str, dict[str, str]] = {}
    for atype, groups in scenario.affiliations.items():
        for gid, members in groups.items():
            for member in members:
                house_affil.setdefault(member, {})[atype] = gid

    households: dict[str, Household] = {}
    for r in range(scenario.rows):
        for c in range(scenario.cols):
            hid = f"r{r}c{c}"
            pv, batt = _draw_pv_batt()
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
                affiliations=house_affil.get(hid, {}),
            )
    return households


def _transfer_caps(
    h: Household,
    s: HouseholdState,
    *,
    solar_kw: float,
    load_kw: float,
    connected: bool,
    dt_hours: float,
) -> tuple[float, float]:
    """Max export / useful-import power (kW) this house can honor in step().

    Mirrors household.step()'s DC-bypass model exactly (fixed 2026-07-06 —
    the old caps ignored the sender's own load and clipped receivers to
    battery absorption, which let settlement book transfers step() could not
    physically execute):

      sender:   solar surplus passes through directly; the battery adds
                min(rate, avail/dt) * sqrt(eta) of deliverable power, which
                must first cover any load deficit; grid import backs a
                connected sender.
      receiver: energy serving the load deficit needs no battery headroom
                (DC bypass); beyond that the battery absorbs at
                min(rate, headroom/(sqrt(eta)*dt)).
    """
    sqrt_eff = math.sqrt(h.rt_efficiency)
    if dt_hours <= 0:
        return 0.0, 0.0
    available_kwh = max(0.0, s.soc_kwh - h.dod_floor_frac * h.battery_kwh)
    deliverable_batt_kw = min(h.battery_max_rate_kw, available_kwh / dt_hours) * sqrt_eff
    sender_cap = (solar_kw - load_kw) + deliverable_batt_kw
    if connected:
        sender_cap += h.grid_max_kw
    headroom_kwh = h.battery_kwh - s.soc_kwh
    absorb_batt_kw = (
        min(h.battery_max_rate_kw, headroom_kwh / (sqrt_eff * dt_hours)) if sqrt_eff > 0 else 0.0
    )
    receiver_cap = max(0.0, load_kw - solar_kw) + absorb_batt_kw
    return max(0.0, sender_cap), max(0.0, receiver_cap)


def run(
    scenario: Scenario,
    decide_transfers: DecideFn | None,
    logger: JsonlLogger,
    *,
    strict: bool = True,
    prepare: PrepareFn | None = None,
    message_bus: MessageBus | None = None,
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
    neighborhood = build_overlay_neighborhood(
        rows=scenario.rows,
        cols=scenario.cols,
        affiliations=scenario.affiliations,
        bus_max_kw=scenario.bus_max_kw,
        bus_loss_factor=scenario.bus_loss_factor,
    )

    solar_profile, load_profiles = _build_data(scenario, households)

    if prepare is not None:
        decide_transfers = prepare(
            scenario,
            households,
            solar_profile,
            load_profiles,
            neighborhood,
            message_bus=message_bus,
            run_dir=logger.run_dir,
        )
    if decide_transfers is None:
        raise ValueError("run() requires either decide_transfers or a prepare hook")

    # Initialize states: every battery starts at 50% capacity, every house
    # presumed grid-connected at t=0 unless the outage schedule says otherwise.
    # The transition tracker starts at True (pre-sim = grid up) so an outage
    # already active at t=0 emits OUTAGE_STARTED on the first tick.
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
        last_grid_status[hid] = True

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

        # Per-house caps mirroring step()'s physics exactly (see _transfer_caps).
        sender_caps_kw: dict[str, float] = {}
        receiver_caps_kw: dict[str, float] = {}
        for hid, h in households.items():
            sender_caps_kw[hid], receiver_caps_kw[hid] = _transfer_caps(
                h,
                states[hid],
                solar_kw=solar_kw[hid],
                load_kw=load_kw[hid],
                connected=grid[hid],
                dt_hours=scenario.dt_hours,
            )

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
                # Conservation invariant: settlement already validated the
                # export against _transfer_caps, so step() must achieve it
                # exactly. A mismatch means receivers were credited energy
                # this house never sourced (the pre-2026-07-06 bug).
                assert abs(new_s.achieved_net_export_kw - net_export_kw) <= 1e-9, (
                    f"export shortfall at {t} for {hid}: "
                    f"desired {net_export_kw}, achieved {new_s.achieved_net_export_kw}"
                )
            new_states[hid] = new_s
        states = new_states

        logger.write_state(t, states, solar_kw, load_kw, grid)
        logger.write_events(outage_events + settlement.events, t=t)

    if message_bus is not None:
        message_bus.write_jsonl(logger.run_dir / "messages.jsonl")

    return logger.finalize(dt_hours=scenario.dt_hours)


def _build_data(
    scenario: Scenario, households: dict[str, Household]
) -> tuple[SolarProfile, dict[str, LoadProfile]]:
    """Dispatch on scenario.data_source to build the solar + per-house load adapters.

    Returns (solar_profile, load_profiles_by_house_id). The engine scales solar
    per-house by pv_kw_peak.
    """
    if scenario.data_source == "synthetic":
        # Per-house synthetic load level is configurable via household_sampling.
        # Default 1.5 kW for back-compat with scenarios that don't specify it.
        base_load_kw = float(scenario.household_sampling.get("synthetic_load_kw", 1.5))
        solar: SolarProfile = SyntheticSolar(peak_kw=1.0)
        loads: dict[str, LoadProfile] = {
            hid: SyntheticLoad(base_kw=base_load_kw) for hid in households
        }
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

    if scenario.data_source == "resstock":
        from pathlib import Path

        from sim.adapters.nrel_solar import NRELSolar
        from sim.adapters.resstock import ResStockLoad

        if "solar_csv" not in scenario.data_paths or "load_dir" not in scenario.data_paths:
            raise ValueError(
                "data_source=resstock requires scenario.data_paths.solar_csv "
                "and scenario.data_paths.load_dir"
            )
        if len(scenario.house_building_files) != scenario.rows * scenario.cols:
            raise ValueError(
                f"house_building_files has {len(scenario.house_building_files)} "
                f"entries, need {scenario.rows * scenario.cols}"
            )
        nrel = NRELSolar(csv_path=scenario.data_paths["solar_csv"], seed=scenario.seed)
        load_dir = Path(scenario.data_paths["load_dir"])
        rs_load_map: dict[str, LoadProfile] = {}
        for (hid, _), fname in zip(households.items(), scenario.house_building_files, strict=True):
            rs_load_map[hid] = ResStockLoad(path=load_dir / fname, dt_hours=scenario.dt_hours)
        return nrel, rs_load_map

    raise ValueError(f"unknown data_source: {scenario.data_source!r}")
