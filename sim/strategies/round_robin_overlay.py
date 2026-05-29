"""Overlay-aware naive fairness baseline.

Identical share-the-headroom logic to round_robin, but targets are the union of
ALL overlay layers (geographic + owner + manager + ...) via
neighborhood.union_neighbors, not geographic adjacency alone. Demonstrates that
the ownership/management trust-circle structure carries coordination value even
under a dumb sharing rule, before Phase 2's LLM agents exploit it.
"""

from __future__ import annotations

from datetime import datetime

from sim.household import Household, HouseholdState
from sim.network import Neighborhood
from sim.types import Transfer

SHARE_FRACTION = 0.05


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
    del t, solar_kw, load_kw
    islanded = [hid for hid, ok in grid.items() if not ok]
    if not islanded:
        return []
    fracs = {hid: states[hid].soc_kwh / households[hid].battery_kwh for hid in islanded}
    mean = sum(fracs.values()) / len(fracs)

    transfers: list[Transfer] = []
    for hid in islanded:
        if fracs[hid] <= mean:
            continue
        h = households[hid]
        available_kwh = max(0.0, states[hid].soc_kwh - h.dod_floor_frac * h.battery_kwh)
        share_kw = available_kwh * SHARE_FRACTION / dt_hours
        if share_kw <= 0:
            continue
        targets = [
            nb for nb in neighborhood.union_neighbors(hid) if nb in fracs and fracs[nb] < mean
        ]
        if not targets:
            continue
        per_target_kw = share_kw / len(targets)
        if per_target_kw <= 0:
            continue
        for target in targets:
            transfers.append(Transfer(from_id=hid, to_id=target, kw=per_target_kw))
    return transfers
