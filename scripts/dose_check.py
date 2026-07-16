"""Preflight: does this failure cell actually DOSE the thing it claims to test?

Usage: python dose_check.py <cell> <seed>

Written 2026-07-16 after the defectors cell at seed 23 turned out to assign all
6 defectors to have-nots -- households with 0 kW PV and 2-4 kWh batteries, i.e.
no surplus to withhold. The cell would have run for $5.50 and returned ~the
clean result, and the natural write-up ("robust to 20% defectors") would have
been false: zero defectors were CAPABLE of defecting. A null that reads as good
news is the most dangerous kind, so check the realized dose before spending.

P(that draw) = C(21,6)/C(30,6) = 9.1% -- rare, but it landed on the one seed the
whole Stage 2 plan was built on.
"""

import sys
from pathlib import Path

import numpy as np

from sim.agents.failure_modes import assign_defectors
from sim.engine import sample_households
from sim.scenario import load_scenario

cell, seed = sys.argv[1], int(sys.argv[2])
sc = load_scenario(Path(f"configs/scenarios/haves_havenots_solar__{cell}.yaml"))
hh = sample_households(sc, np.random.default_rng(seed))  # engine.py:179 seeds this way
fm = sc.failure_modes

print(f"=== dose check: {cell}, seed {seed} ===")
haves = {k for k, v in hh.items() if v.pv_kw_peak > 1.0}
print(f"population: {len(hh)} houses = {len(haves)} haves / {len(hh) - len(haves)} have-nots")

ok = True

if fm.defector_fraction > 0:
    d = assign_defectors(list(hh), fm, seed)
    dh = d & haves
    tot = sum(hh[k].pv_kw_peak for k in haves)
    wit = sum(hh[k].pv_kw_peak for k in dh)
    frac = wit / tot if tot else 0.0
    print(f"\ndefectors ({fm.defector_realization}): {len(d)} assigned, {len(dh)} are haves")
    print(f"  withheld generation: {frac:.1%} of {tot:.1f} kW")
    if not dh:
        print("  *** INERT: no defector holds surplus. This cell cannot show defection. ***")
        ok = False
    elif frac < 0.10:
        print(f"  *** WEAK: {frac:.1%} dose is unlikely to move served_load. ***")
        ok = False
    # Only haves can withhold, so the have-side dose is the real dose.
    print(f"  realized dose on surplus-holders: {len(dh)}/{len(haves)} = {len(dh)/len(haves):.0%}")

n = fm.obs_noise
if n.soc_std_frac > 0 or n.load_std_frac > 0:
    print(f"\nobs_noise: soc_std_frac={n.soc_std_frac} load_std_frac={n.load_std_frac}")
    print("  (measured 2026-07-16: load bias +0.048%, SoC clamp mean-reverting ->")
    print("   both REDUCE sharing; neither can systematically help)")

c = fm.comm
if c.per_tick_budget is not None or c.drop_prob_by_circle:
    print(f"\ncomm: per_tick_budget={c.per_tick_budget} drops={c.drop_prob_by_circle}")
    print("  (INFORMs emit last -> budget starves them -> eligibility collapse)")

print(f"\n=> {'OK to spend' if ok else 'DO NOT SPEND — cell is inert/weak at this seed'}")
sys.exit(0 if ok else 2)
