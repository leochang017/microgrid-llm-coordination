"""Simulation engine: builds households, owns the clock, drives the per-tick loop.

Task 15 ships only sample_households(scenario, rng) — the deterministic
neighborhood builder. The full run loop (run(...)) lands in Task 16.
"""

from __future__ import annotations

import numpy as np

from sim.household import Household
from sim.scenario import Scenario
from sim.types import HouseholdProfile


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
