"""Naive fairness baseline.

Each tick, islanded houses with above-mean state-of-charge share a small
fraction of their above-floor headroom with each of their spatial-graph
neighbors that have below-mean state-of-charge. This is not optimal — it's
the "is coordination doing anything at all?" check that Phase 3's integration
test exercises.
"""

from __future__ import annotations

from datetime import datetime

from sim.household import Household, HouseholdState
from sim.network import Neighborhood
from sim.types import Transfer

# How much of a sender's above-floor headroom to share per tick. Tuned so that
# round_robin produces a measurably more-even SoC distribution than
# no_coordination on the standard 24h_uniform scenario without bus-saturating.
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
    del t, solar_kw, load_kw  # not used; strategy looks at current state only
    # Compute mean SoC fraction across islanded houses only — sharing during
    # normal grid-up operation is the grid's job, not the coordinator's.
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
        share_kwh = available_kwh * SHARE_FRACTION
        share_kw = share_kwh / dt_hours
        if share_kw <= 0:
            continue
        targets = [nb for nb in neighborhood.comm_graph[hid] if nb in fracs and fracs[nb] < mean]
        if not targets:
            continue
        per_target_kw = share_kw / len(targets)
        if per_target_kw <= 0:
            continue
        for target in targets:
            transfers.append(Transfer(from_id=hid, to_id=target, kw=per_target_kw))
    return transfers
