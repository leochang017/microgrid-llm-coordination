"""Tabulate served-load, unmet, welfare Gini, and gap-closed across strategies.

  python -m scripts.compare --scenario configs/scenarios/haves_havenots.yaml
  python -m scripts.compare --scenario ... --seeds 23,1,7,42

Runs each strategy through the engine, computes the LP optimum (the ceiling)
directly from lp_optimal, and prints a markdown comparison table — one per
seed, plus a mean/min/max aggregate when several seeds are given. Each seed is
a fresh household draw, so multi-seed spreads are the honest error bars for
every headline claim (single-seed differences of a point or two are noise:
round_robin alone varies by ~20+ points across seeds on the showcase family).

gap_closed(strategy) = (served(strategy) - served(round_robin))
                       / (served(lp_optimal) - served(round_robin))

Reported UNCLAMPED (2026-07-06): a strategy below round_robin shows a negative
percentage, and a zero rr->LP gap shows "n/a" — the old version clamped both
to 0.00%, which silently converted "worse than the baseline" and "no headroom
to measure" into "no progress".

The LP ceiling is the LP *objective* (lp_optimal.optimal_metrics), not an
engine-realized run — see sim/strategies/lp_optimal.py for why.

NOTE for sweep drivers: strategies that keep module-level state (llm_agent's
counter registry) are only safe one-run-per-process; run those cells via
`python -m scripts.run` subprocesses, not by looping _collect in-process.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from sim.engine import _build_data, run, sample_households
from sim.logging import JsonlLogger
from sim.network import build_overlay_neighborhood
from sim.scenario import load_scenario
from sim.strategies import lp_optimal

_HEURISTICS = ["no_coordination", "round_robin", "round_robin_overlay"]
_ORDER = ["no_coordination", "round_robin", "round_robin_overlay", "lp_optimal"]


def gap_closed(*, served: float, rr: float, lp: float) -> float:
    """Fraction of the round_robin -> LP-optimal served-load gap that `served` closes.

    Unclamped: negative means worse than round_robin; NaN means the gap is too
    small to measure against (lp ~= rr).
    """
    gap = lp - rr
    if abs(gap) <= 1e-12:
        return float("nan")
    return (served - rr) / gap


def _fmt_gc(gc: float) -> str:
    return "n/a" if math.isnan(gc) else f"{gc:.2%}"


def format_table(metrics: dict[str, dict[str, float]]) -> str:
    """Render a markdown table. `metrics` maps strategy -> summary-like dict.

    The "lp_optimal" entry's served_load_fraction is treated as the ceiling and
    "round_robin" as the reference baseline for gap_closed.
    """
    rr = metrics.get("round_robin", {}).get("served_load_fraction", 0.0)
    lp = metrics.get("lp_optimal", {}).get("served_load_fraction", rr)
    header = "| strategy | served | unmet_kwh | gini | gap_closed |"
    sep = "|---|---|---|---|---|"
    rows = [header, sep]
    ordered = [s for s in _ORDER if s in metrics] + [s for s in metrics if s not in _ORDER]
    for s in ordered:
        d = metrics[s]
        served = d.get("served_load_fraction", 0.0)
        gc = gap_closed(served=served, rr=rr, lp=lp)
        rows.append(
            f"| {s} | {served:.4f} | {d.get('unmet_kwh_total', 0.0):.1f} "
            f"| {d.get('gini_welfare', 0.0):.4f} | {_fmt_gc(gc)} |"
        )
    return "\n".join(rows)


def format_aggregate(per_seed: dict[int, dict[str, dict[str, float]]]) -> str:
    """Mean/min/max served + mean gini + mean gap_closed across seeds.

    gap_closed is computed per seed (paired: all strategies share the seed's
    household draw) and averaged over seeds where it is defined.
    """
    seeds = sorted(per_seed)
    strategies = [s for s in _ORDER if s in per_seed[seeds[0]]] + [
        s for s in per_seed[seeds[0]] if s not in _ORDER
    ]
    header = f"| strategy | served mean | served min | served max | gini mean | gap_closed mean ({len(seeds)} seeds) |"
    sep = "|---|---|---|---|---|---|"
    rows = [header, sep]
    for s in strategies:
        served = [per_seed[k][s]["served_load_fraction"] for k in seeds]
        gini = [per_seed[k][s]["gini_welfare"] for k in seeds]
        gcs = []
        for k in seeds:
            rr = per_seed[k].get("round_robin", {}).get("served_load_fraction", 0.0)
            lp = per_seed[k].get("lp_optimal", {}).get("served_load_fraction", rr)
            gc = gap_closed(served=per_seed[k][s]["served_load_fraction"], rr=rr, lp=lp)
            if not math.isnan(gc):
                gcs.append(gc)
        gc_mean = sum(gcs) / len(gcs) if gcs else float("nan")
        rows.append(
            f"| {s} | {sum(served) / len(served):.4f} | {min(served):.4f} | {max(served):.4f} "
            f"| {sum(gini) / len(gini):.4f} | {_fmt_gc(gc_mean)} |"
        )
    return "\n".join(rows)


def _collect(
    scenario_path: Path, *, seed: int | None = None, strategies: list[str] | None = None
) -> dict[str, dict[str, float]]:
    metrics: dict[str, dict[str, float]] = {}
    base = load_scenario(scenario_path)
    if seed is not None:
        base = dataclasses.replace(base, seed=seed)
    with tempfile.TemporaryDirectory() as td:
        for strategy in strategies or _HEURISTICS:
            sc = dataclasses.replace(base, strategy=strategy)
            mod = importlib.import_module(f"sim.strategies.{strategy}")
            logger = JsonlLogger(run_dir=f"{td}/{strategy}", scenario_id=sc.scenario_id)
            summary: dict[str, Any] = run(
                sc,
                getattr(mod, "decide_transfers", None),
                logger,
                prepare=getattr(mod, "prepare", None),
            )
            metrics[strategy] = {
                "served_load_fraction": summary["served_load_fraction"],
                "unmet_kwh_total": summary["unmet_kwh_total"],
                "gini_welfare": summary["gini_welfare"],
            }

    # LP ceiling: the objective, computed directly (not an engine run).
    households = sample_households(base, np.random.default_rng(base.seed))
    nbhd = build_overlay_neighborhood(
        base.rows,
        base.cols,
        base.affiliations,
        bus_max_kw=base.bus_max_kw,
        bus_loss_factor=base.bus_loss_factor,
    )
    solar, loads = _build_data(base, households)
    metrics["lp_optimal"] = lp_optimal.optimal_metrics(base, households, solar, loads, nbhd)
    return metrics


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--scenario", type=Path, required=True, help="Scenario YAML to compare over")
    p.add_argument(
        "--seeds",
        type=str,
        default=None,
        help="Comma-separated seed list (default: the scenario's own seed). "
        "Multiple seeds print per-seed tables plus a mean/min/max aggregate.",
    )
    p.add_argument(
        "--strategies",
        type=str,
        default=None,
        help=f"Comma-separated engine strategies (default: {','.join(_HEURISTICS)}). "
        "lp_optimal is always added as the ceiling row.",
    )
    args = p.parse_args()
    strategies = args.strategies.split(",") if args.strategies else None
    if args.seeds is None:
        print(format_table(_collect(args.scenario, strategies=strategies)))
        return
    seeds = [int(s) for s in args.seeds.split(",")]
    per_seed: dict[int, dict[str, dict[str, float]]] = {}
    for seed in seeds:
        per_seed[seed] = _collect(args.scenario, seed=seed, strategies=strategies)
        print(f"\n### seed {seed}\n")
        print(format_table(per_seed[seed]))
    if len(seeds) > 1:
        print(f"\n### aggregate over seeds {seeds}\n")
        print(format_aggregate(per_seed))


if __name__ == "__main__":
    main()
