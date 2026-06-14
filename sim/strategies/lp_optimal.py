"""Centralized full-horizon LP oracle — the achievable-served-load ceiling.

Solved once via prepare(): a single linear program over the whole scenario
horizon with perfect foresight and full-bus access (ignores the comm graph).
Objective: maximize total served load power. No fairness tiebreak (documented
future refinement). HiGHS is deterministic, so the result is reproducible.

Two ways to consume the solution:
  - `optimal_served_fraction(...)` returns the LP objective as a served-load
    fraction. **This is the reported ceiling** for the "% of gap closed between
    round_robin and LP-optimal" framing — the true theoretical upper bound.
  - `prepare(...)` returns a per-tick transfer schedule so the LP can also be
    run as a strategy through the engine (for visualization / state logs). Note
    the engine's greedy per-tick `step()` dispatch will NOT faithfully execute
    the LP's planned battery schedule, so the engine-realized served-load can
    fall below the LP optimum (and even below round_robin). Always use
    `optimal_served_fraction` for the ceiling figure, never the realized run.
"""

from __future__ import annotations

import math
from datetime import datetime

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

from sim.data import LoadProfile, SolarProfile
from sim.engine import DecideFn
from sim.household import Household, HouseholdState
from sim.network import Neighborhood
from sim.scenario import Scenario
from sim.types import Transfer

_VAR_KINDS = ("ch", "dis", "imp", "exp", "send", "recv", "served")
_TINY = 1e-9


def prepare(
    scenario: Scenario,
    households: dict[str, Household],
    solar_profile: SolarProfile,
    load_profiles: dict[str, LoadProfile],
    neighborhood: Neighborhood,
    **_: object,
) -> DecideFn:
    schedule = _solve(scenario, households, solar_profile, load_profiles, neighborhood)

    def decide_transfers(
        t: datetime,
        states: dict[str, HouseholdState],
        hh: dict[str, Household],
        solar_kw: dict[str, float],
        load_kw: dict[str, float],
        grid: dict[str, bool],
        nbhd: Neighborhood,
        dt_hours: float,
    ) -> list[Transfer]:
        return schedule.get(t, [])

    return decide_transfers


def _solve_lp(
    scenario: Scenario,
    households: dict[str, Household],
    solar_profile: SolarProfile,
    load_profiles: dict[str, LoadProfile],
    neighborhood: Neighborhood,
) -> tuple[
    np.ndarray,
    dict[tuple[str, str, int], int],
    list[str],
    list[datetime],
    dict[tuple[str, int], bool],
    dict[tuple[str, int], float],
]:
    """Build and solve the full-horizon LP; return raw solution + index maps.

    Returns (x, col, ids, ticks, grid_at, load_at). Callers derive either the
    per-tick transfer schedule (_solve) or the optimal served fraction
    (optimal_served_fraction) from this.
    """
    ids = sorted(households)
    ticks = list(scenario.timesteps())
    nT = len(ticks)
    dt = scenario.dt_hours
    loss = neighborhood.bus_loss_factor

    # --- variable registry --------------------------------------------------
    col: dict[tuple[str, str, int], int] = {}

    def reg(kind: str, hid: str, k: int) -> int:
        key = (kind, hid, k)
        if key not in col:
            col[key] = len(col)
        return col[key]

    for hid in ids:
        for k in range(nT):
            for kind in _VAR_KINDS:
                reg(kind, hid, k)
        for k in range(nT + 1):
            reg("soc", hid, k)
    n = len(col)

    c = np.zeros(n)
    for hid in ids:
        for k in range(nT):
            c[col[("served", hid, k)]] = -1.0  # maximize served -> minimize -served

    bounds: list[tuple[float, float | None]] = [(0.0, None)] * n
    solar_at = {
        (hid, k): solar_profile.get_kw(ticks[k]) * households[hid].pv_kw_peak
        for hid in ids
        for k in range(nT)
    }
    load_at = {(hid, k): load_profiles[hid].get_kw(ticks[k]) for hid in ids for k in range(nT)}
    grid_at = {(hid, k): scenario.grid_status_at(ticks[k], hid) for hid in ids for k in range(nT)}

    for hid in ids:
        h = households[hid]
        cap = h.battery_kwh
        floor = h.dod_floor_frac * cap
        rate = h.battery_max_rate_kw
        gmax = h.grid_max_kw
        for k in range(nT):
            bounds[col[("ch", hid, k)]] = (0.0, rate)
            bounds[col[("dis", hid, k)]] = (0.0, rate)
            connected = grid_at[(hid, k)]
            bounds[col[("imp", hid, k)]] = (0.0, gmax if connected else 0.0)
            bounds[col[("exp", hid, k)]] = (0.0, gmax if connected else 0.0)
            bounds[col[("send", hid, k)]] = (0.0, neighborhood.bus_max_kw)
            bounds[col[("recv", hid, k)]] = (0.0, neighborhood.bus_max_kw)
            bounds[col[("served", hid, k)]] = (0.0, max(0.0, load_at[(hid, k)]))
        bounds[col[("soc", hid, 0)]] = (0.5 * cap, 0.5 * cap)
        for k in range(1, nT + 1):
            bounds[col[("soc", hid, k)]] = (floor, cap)

    # --- equality constraints -----------------------------------------------
    er: list[int] = []
    ec: list[int] = []
    ev: list[float] = []
    beq: list[float] = []
    sqrt_eff = {hid: math.sqrt(households[hid].rt_efficiency) for hid in ids}

    def eq_row(terms: list[tuple[int, float]], rhs: float) -> None:
        row = len(beq)
        for cidx, val in terms:
            er.append(row)
            ec.append(cidx)
            ev.append(val)
        beq.append(rhs)

    # power balance: solar + dis + imp + recv - served - ch - exp - send = 0
    for hid in ids:
        for k in range(nT):
            eq_row(
                [
                    (col[("dis", hid, k)], 1.0),
                    (col[("imp", hid, k)], 1.0),
                    (col[("recv", hid, k)], 1.0),
                    (col[("served", hid, k)], -1.0),
                    (col[("ch", hid, k)], -1.0),
                    (col[("exp", hid, k)], -1.0),
                    (col[("send", hid, k)], -1.0),
                ],
                -solar_at[(hid, k)],
            )
    # soc recurrence: soc[k+1] - soc[k] - dt*sqrt*ch + dt*dis/sqrt = 0
    for hid in ids:
        se = sqrt_eff[hid]
        for k in range(nT):
            eq_row(
                [
                    (col[("soc", hid, k + 1)], 1.0),
                    (col[("soc", hid, k)], -1.0),
                    (col[("ch", hid, k)], -dt * se),
                    (col[("dis", hid, k)], dt / se),
                ],
                0.0,
            )
    # per-grid-group bus balance: sum recv - (1-loss)*sum send = 0
    for k in range(nT):
        for status in (True, False):
            members = [hid for hid in ids if grid_at[(hid, k)] is status]
            if len(members) < 2:
                for hid in members:
                    eq_row([(col[("send", hid, k)], 1.0)], 0.0)
                    eq_row([(col[("recv", hid, k)], 1.0)], 0.0)
                continue
            terms = [(col[("recv", hid, k)], 1.0) for hid in members]
            terms += [(col[("send", hid, k)], -(1.0 - loss)) for hid in members]
            eq_row(terms, 0.0)

    a_eq = coo_matrix((ev, (er, ec)), shape=(len(beq), n))

    # --- inequality: per-group bus throughput sum send <= bus_max -----------
    ur: list[int] = []
    uc: list[int] = []
    uv: list[float] = []
    bub: list[float] = []
    for k in range(nT):
        for status in (True, False):
            members = [hid for hid in ids if grid_at[(hid, k)] is status]
            if len(members) < 2:
                continue
            row = len(bub)
            for hid in members:
                ur.append(row)
                uc.append(col[("send", hid, k)])
                uv.append(1.0)
            bub.append(neighborhood.bus_max_kw)
    a_ub = coo_matrix((uv, (ur, uc)), shape=(len(bub), n)) if bub else None
    b_ub = np.array(bub) if bub else None

    res = linprog(
        c,
        A_ub=a_ub,
        b_ub=b_ub,
        A_eq=a_eq,
        b_eq=np.array(beq),
        bounds=bounds,
        method="highs",
    )
    if not res.success:
        raise RuntimeError(f"LP failed: {res.message}")

    return res.x, col, ids, ticks, grid_at, load_at


def _solve(
    scenario: Scenario,
    households: dict[str, Household],
    solar_profile: SolarProfile,
    load_profiles: dict[str, LoadProfile],
    neighborhood: Neighborhood,
) -> dict[datetime, list[Transfer]]:
    x, col, ids, ticks, grid_at, _load_at = _solve_lp(
        scenario, households, solar_profile, load_profiles, neighborhood
    )
    return _schedule_from_solution(x, col, ids, ticks, grid_at, neighborhood.bus_loss_factor)


def optimal_metrics(
    scenario: Scenario,
    households: dict[str, Household],
    solar_profile: SolarProfile,
    load_profiles: dict[str, LoadProfile],
    neighborhood: Neighborhood,
) -> dict[str, float]:
    """The LP optimum expressed as engine-comparable summary metrics.

    Returns served_load_fraction (the reported ceiling), unmet_kwh_total, and
    gini_welfare — all computed directly from the LP solution, the same way the
    engine's summary.json defines them, so the LP row is honest in comparisons.
    The LP is NOT run through the engine for these figures, because the engine's
    greedy per-tick dispatch would not faithfully execute the LP's planned
    battery schedule (see module docstring).
    """
    from sim.logging import _gini

    x, col, ids, ticks, _grid_at, load_at = _solve_lp(
        scenario, households, solar_profile, load_profiles, neighborhood
    )
    served_by_house = {
        hid: sum(float(x[col[("served", hid, k)]]) for k in range(len(ticks))) for hid in ids
    }
    load_by_house = {hid: sum(load_at[(hid, k)] for k in range(len(ticks))) for hid in ids}
    total_served = sum(served_by_house.values())
    total_load = sum(load_by_house.values())
    per_house_frac = [
        served_by_house[hid] / load_by_house[hid] for hid in ids if load_by_house[hid] > 0
    ]
    return {
        "served_load_fraction": total_served / total_load if total_load > 0 else 1.0,
        "unmet_kwh_total": (total_load - total_served) * scenario.dt_hours,
        "gini_welfare": _gini(per_house_frac),
    }


def optimal_served_fraction(
    scenario: Scenario,
    households: dict[str, Household],
    solar_profile: SolarProfile,
    load_profiles: dict[str, LoadProfile],
    neighborhood: Neighborhood,
) -> float:
    """The LP's optimal served-load fraction — the theoretical ceiling.

    Thin wrapper over optimal_metrics for callers that only need the headline
    fraction (e.g. the stress-scenario acceptance test).
    """
    return optimal_metrics(scenario, households, solar_profile, load_profiles, neighborhood)[
        "served_load_fraction"
    ]


def _schedule_from_solution(
    x: np.ndarray,
    col: dict[tuple[str, str, int], int],
    ids: list[str],
    ticks: list[datetime],
    grid_at: dict[tuple[str, int], bool],
    loss: float,
) -> dict[datetime, list[Transfer]]:
    """Convert per-house send/recv aggregates into pairwise Transfers per tick.

    Within each grid-status group, distribute each receiver's required gross
    inflow across senders proportionally to their send share.
    """
    schedule: dict[datetime, list[Transfer]] = {}
    for k, t in enumerate(ticks):
        transfers: list[Transfer] = []
        for status in (True, False):
            members = [hid for hid in ids if grid_at[(hid, k)] is status]
            senders = [
                (hid, float(x[col[("send", hid, k)]]))
                for hid in members
                if x[col[("send", hid, k)]] > _TINY
            ]
            receivers = [
                (hid, float(x[col[("recv", hid, k)]]))
                for hid in members
                if x[col[("recv", hid, k)]] > _TINY
            ]
            total_send = sum(s for _, s in senders)
            if total_send <= _TINY:
                continue
            for r_id, r_recv in receivers:
                gross_needed = r_recv / (1.0 - loss) if loss < 1.0 else r_recv
                for s_id, s_send in senders:
                    share = gross_needed * (s_send / total_send)
                    if share > _TINY and s_id != r_id:
                        transfers.append(Transfer(from_id=s_id, to_id=r_id, kw=share))
        if transfers:
            schedule[t] = transfers
    return schedule
