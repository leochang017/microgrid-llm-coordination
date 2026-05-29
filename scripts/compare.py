"""Tabulate served-load, unmet, welfare Gini, and gap-closed across strategies.

  python -m scripts.compare --scenario configs/scenarios/haves_havenots.yaml

Runs each heuristic strategy through the engine, computes the LP optimum (the
ceiling) directly from lp_optimal, and prints a markdown comparison table.

gap_closed(strategy) = (served(strategy) - served(round_robin))
                       / (served(lp_optimal) - served(round_robin))

The LP ceiling is the LP *objective* (lp_optimal.optimal_served_fraction), not an
engine-realized run — see sim/strategies/lp_optimal.py for why.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
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
    """Fraction of the round_robin -> LP-optimal served-load gap that `served` closes."""
    gap = lp - rr
    if gap <= 1e-12:
        return 0.0
    return max(0.0, min(1.0, (served - rr) / gap))


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
            f"| {d.get('gini_welfare', 0.0):.4f} | {gc:.2%} |"
        )
    return "\n".join(rows)


def _collect(scenario_path: Path) -> dict[str, dict[str, float]]:
    metrics: dict[str, dict[str, float]] = {}
    base = load_scenario(scenario_path)
    with tempfile.TemporaryDirectory() as td:
        for strategy in _HEURISTICS:
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
    args = p.parse_args()
    print(format_table(_collect(args.scenario)))


if __name__ == "__main__":
    main()
