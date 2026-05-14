"""Each household acts alone — no peer transfers."""

from __future__ import annotations

from datetime import datetime

from sim.household import Household, HouseholdState
from sim.network import Neighborhood
from sim.types import Transfer


def decide_transfers(
    t: datetime,
    states: dict[str, HouseholdState],
    households: dict[str, Household],
    solar_kw: dict[str, float],
    load_kw: dict[str, float],
    grid: dict[str, bool],
    neighborhood: Neighborhood,
    dt_hours: float,
) -> list[Transfer]:
    """Return no transfers — every house hoards its own energy."""
    del t, states, households, solar_kw, load_kw, grid, neighborhood, dt_hours
    return []
