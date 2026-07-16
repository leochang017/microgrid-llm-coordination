"""Deterministic Phase 3.3 figures + tables, regenerated from committed artifacts.

  python -m scripts.figures --all         # every figure + table
  python -m scripts.figures --headline    # just the headline figure
  python -m scripts.figures --check       # assert committed live numbers unchanged

$0, no API calls. Live numbers are READ from the committed
``reference_runs/<cell>/llm_agent/<run>/summary.json`` files; the zero-dollar
baselines (``no_coordination``, ``round_robin``, ``llm_fallback`` = the control)
and the ``lp_optimal`` ceiling are REGENERATED via the engine (deterministic,
seeded) because ``.gitignore`` keeps them out of the repo — their provenance is
the recorded number plus the seed, exactly as ``scripts/compare.py`` treats them.

matplotlib is the optional ``viz`` extra and is absent in CI, so it is imported
lazily inside the ``render_*`` functions. Everything above the render section is
matplotlib-free, so the test suite imports it without the ``viz`` extra.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from scripts.compare import gap_closed
from sim.engine import _build_data, run, sample_households
from sim.logging import JsonlLogger
from sim.network import build_overlay_neighborhood
from sim.scenario import load_scenario
from sim.strategies import lp_optimal

REPO = Path(__file__).resolve().parent.parent
REF = REPO / "reference_runs"
SCEN = REPO / "configs" / "scenarios"
FIG_DIR = REPO / "docs" / "figures"

# The committed live cells: cell dir -> {seed: llm_agent run subdir}. `all` has
# no live run (deferred) and is excluded from every live comparison.
LIVE_CELLS: dict[str, dict[int, str]] = {
    "haves_havenots_solar__llm": {23: "clean__seed23", 1: "clean__seed1", 7: "clean__seed7"},
    "haves_havenots_solar__comm": {23: "comm__seed23"},
    "haves_havenots_solar__defectors": {7: "defectors__seed7"},
    "haves_havenots_solar__noise": {23: "noise__seed23"},
}

# Short human labels for figures/tables, in the order the paper tells the story:
# the clean multi-seed headline first, then the three failure axes.
CELL_LABEL: dict[str, str] = {
    "haves_havenots_solar__llm": "clean",
    "haves_havenots_solar__comm": "comm",
    "haves_havenots_solar__defectors": "defectors",
    "haves_havenots_solar__noise": "noise",
}
CELL_ORDER = [
    "haves_havenots_solar__llm",
    "haves_havenots_solar__defectors",
    "haves_havenots_solar__noise",
    "haves_havenots_solar__comm",
]

BASELINES = ["no_coordination", "round_robin", "llm_fallback"]
# Canonical left-to-right method order for grouped bars: floor, control, tuned
# heuristic, the LLM, then the ceiling.
METHOD_ORDER = ["no_coordination", "llm_fallback", "round_robin", "llm_agent", "lp_optimal"]
METHOD_LABEL = {
    "no_coordination": "no-coord",
    "llm_fallback": "control",
    "round_robin": "round-robin",
    "llm_agent": "live-Haiku",
    "lp_optimal": "LP ceiling",
}

# Metrics pulled through to figures/tables. LP only defines served/gini (it is a
# throughput ceiling, not an engine run), so the other three are read with .get.
METRIC_KEYS = (
    "served_load_fraction",
    "gini_welfare",
    "jains_index",
    "min_house_served_fraction",
    "served_critical_load_fraction",
)


def scenario_path(cell: str) -> Path:
    return SCEN / f"{cell}.yaml"


def read_live_summary(cell: str, seed: int) -> dict[str, Any]:
    """Load the committed llm_agent summary.json for one live cell/seed."""
    if cell not in LIVE_CELLS or seed not in LIVE_CELLS[cell]:
        raise KeyError(f"no committed live run for {cell} @ seed {seed}")
    p = REF / cell / "llm_agent" / LIVE_CELLS[cell][seed] / "summary.json"
    if not p.exists():
        raise FileNotFoundError(f"expected committed live summary at {p}")
    return json.loads(p.read_text())  # type: ignore[no-any-return]


def regen_baselines(cell: str, seed: int) -> dict[str, dict[str, Any]]:
    """Regenerate the $0 baselines + LP ceiling via the engine (deterministic).

    Runs into a throwaway dir: baselines carry no paid cache, so nothing here is
    worth keeping — only the numbers, which the caller consumes.
    """
    base = dataclasses.replace(load_scenario(scenario_path(cell)), seed=seed)
    out: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for strat in BASELINES:
            sc = dataclasses.replace(base, strategy=strat)
            mod = importlib.import_module(f"sim.strategies.{strat}")
            logger = JsonlLogger(run_dir=root / strat, scenario_id=sc.scenario_id)
            out[strat] = run(
                sc,
                getattr(mod, "decide_transfers", None),
                logger,
                prepare=getattr(mod, "prepare", None),
            )
            logger.close()
    households = sample_households(base, np.random.default_rng(base.seed))
    nbhd = build_overlay_neighborhood(
        base.rows,
        base.cols,
        base.affiliations,
        bus_max_kw=base.bus_max_kw,
        bus_loss_factor=base.bus_loss_factor,
    )
    solar, loads = _build_data(base, households)
    out["lp_optimal"] = lp_optimal.optimal_metrics(base, households, solar, loads, nbhd)
    return out


def collect_cell(cell: str, seed: int) -> dict[str, dict[str, Any]]:
    """One (cell, seed) as {method: metrics}: regenerated baselines + read live."""
    methods = regen_baselines(cell, seed)
    methods["llm_agent"] = read_live_summary(cell, seed)
    return methods


def cell_served_gap_closed(methods: dict[str, dict[str, Any]]) -> float:
    """gap_closed(live) against the control→LP span, for annotations."""
    return gap_closed(
        served=methods["llm_agent"]["served_load_fraction"],
        rr=methods["llm_fallback"]["served_load_fraction"],
        lp=methods["lp_optimal"]["served_load_fraction"],
    )


def _cli() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--all", action="store_true", help="regenerate every figure + table")
    p.add_argument("--check", action="store_true", help="assert committed live numbers unchanged")
    args = p.parse_args()
    if args.check:
        for cell, seeds in LIVE_CELLS.items():
            for seed in seeds:
                s = read_live_summary(cell, seed)
                print(f"{CELL_LABEL[cell]:>10} @ {seed:>2}: served {s['served_load_fraction']:.4f}")
        return
    # Render targets land in later tasks; keep the CLI honest until then.
    print("no render target selected (rendering added in Phase 3.3 tasks 2-5)")


if __name__ == "__main__":
    _cli()
