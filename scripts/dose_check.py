"""Preflight: does this failure cell actually DOSE the thing it claims to test?

  python -m scripts.dose_check <cell> <seed>

Exits 2 on an inert or weak cell, so it can gate spending.

Written 2026-07-16 after the defectors cell at seed 23 reached a paid live run
before anyone checked *which* houses were assigned to defect. All 6 landed on
have-nots -- 0 kW PV, 2-4 kWh batteries -- so the cell withheld 0.0% of
generation: the agents told to hoard had nothing to hoard. It would have
returned ~the clean result, and the obvious write-up ("robust to 20% defectors")
would have been false, because no defector was CAPABLE of defecting. A null that
reads as good news is the most dangerous kind of wrong result.

P(that draw) = C(21,6)/C(30,6) = 9.1% -- rare, and it landed on the one seed the
Stage 2 plan was built on. Seeds 1/7/2/3/11/42 all deliver a real 16-34% dose,
so the design is sound; that seed was not.

The root cause is scenario design, not a bug: defectors are drawn uniformly over
ALL households, but only haves can withhold, so ~60% of every draw is inert by
construction and the have-side dose swings 0-34% across seeds. Any defector
result must report its realized dose -- a single-seed defector number means
nothing on its own.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from sim.agents.failure_modes import assign_defectors
from sim.engine import sample_households
from sim.scenario import Scenario, load_scenario

# Haves draw pv_kw_peak from [5.0, 7.0]; have-nots draw exactly [0.0, 0.0]. Any
# threshold in between separates them; 1.0 leaves room if the bands are retuned.
_HAVE_PV_KW = 1.0

# Below this share of generation a defector cell cannot plausibly move
# served_load out of the noise floor (cross-seed spread is ~16 pts).
_WEAK_DOSE_FRAC = 0.10


@dataclass(frozen=True)
class DoseReport:
    n_houses: int
    n_haves: int
    n_defectors: int
    n_have_defectors: int
    withheld_generation_frac: float
    defector_ids: tuple[str, ...]
    have_defector_ids: tuple[str, ...]

    @property
    def is_inert(self) -> bool:
        """No defector holds surplus -> the cell cannot show defection at all."""
        return self.n_have_defectors == 0

    @property
    def is_weak(self) -> bool:
        return not self.is_inert and self.withheld_generation_frac < _WEAK_DOSE_FRAC


def realized_defector_dose(scenario: Scenario, seed: int) -> DoseReport:
    """What share of generation do this cell's defectors actually withhold?

    Only haves hold surplus, so have-defectors are the entire dose; have-not
    defectors are inert by construction. ``seed`` is passed explicitly rather
    than read off the scenario because a run may override it via --seed.
    """
    households = sample_households(scenario, np.random.default_rng(seed))  # cf. engine.py:179
    defectors = assign_defectors(list(households), scenario.failure_modes, seed)
    haves = {hid for hid, h in households.items() if h.pv_kw_peak > _HAVE_PV_KW}
    have_defectors = defectors & haves

    total_pv = sum(households[h].pv_kw_peak for h in haves)
    withheld_pv = sum(households[h].pv_kw_peak for h in have_defectors)
    return DoseReport(
        n_houses=len(households),
        n_haves=len(haves),
        n_defectors=len(defectors),
        n_have_defectors=len(have_defectors),
        withheld_generation_frac=(withheld_pv / total_pv) if total_pv else 0.0,
        defector_ids=tuple(sorted(defectors)),
        have_defector_ids=tuple(sorted(have_defectors)),
    )


def main() -> int:
    cell, seed = sys.argv[1], int(sys.argv[2])
    scenario = load_scenario(Path(f"configs/scenarios/haves_havenots_solar__{cell}.yaml"))
    fm = scenario.failure_modes
    d = realized_defector_dose(scenario, seed)

    print(f"=== dose check: {cell}, seed {seed} ===")
    print(
        f"population: {d.n_houses} houses = {d.n_haves} haves / {d.n_houses - d.n_haves} have-nots"
    )

    ok = True
    if fm.defector_fraction > 0:
        print(
            f"\ndefectors ({fm.defector_realization}): {d.n_defectors} assigned, "
            f"{d.n_have_defectors} are haves"
        )
        print(f"  withheld generation: {d.withheld_generation_frac:.1%}")
        print(f"  dose on surplus-holders: {d.n_have_defectors}/{d.n_haves}")
        print(f"  defector ids: {', '.join(d.defector_ids)}")
        if d.is_inert:
            print("  *** INERT: no defector holds surplus. This cell cannot show defection. ***")
            ok = False
        elif d.is_weak:
            print(f"  *** WEAK: {d.withheld_generation_frac:.1%} is inside the noise floor. ***")
            ok = False

    n = fm.obs_noise
    if n.soc_std_frac > 0 or n.load_std_frac > 0:
        print(f"\nobs_noise: soc_std_frac={n.soc_std_frac} load_std_frac={n.load_std_frac}")
        print("  (measured 2026-07-16: load bias +0.048%; SoC clamp is mean-reverting ->")
        print("   both REDUCE sharing, so neither can systematically help)")

    c = fm.comm
    if c.per_tick_budget is not None or c.drop_prob_by_circle:
        print(f"\ncomm: per_tick_budget={c.per_tick_budget} drops={c.drop_prob_by_circle}")
        print("  (INFORMs emit last -> budget starves them -> eligibility collapse)")

    print(f"\n=> {'OK to spend' if ok else 'DO NOT SPEND — cell is inert/weak at this seed'}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
