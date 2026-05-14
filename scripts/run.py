"""CLI entry point.

Usage:
  python -m scripts.run --scenario configs/scenarios/24h_uniform.yaml
"""

from __future__ import annotations

import argparse
import importlib
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from sim.engine import run
from sim.logging import JsonlLogger
from sim.scenario import load_scenario


def _resolve_strategy(name: str) -> Callable[..., Any]:
    """Import sim.strategies.<name> and return its decide_transfers callable."""
    module = importlib.import_module(f"sim.strategies.{name}")
    return module.decide_transfers  # type: ignore[no-any-return]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a microgrid simulation scenario.")
    parser.add_argument("--scenario", type=Path, required=True, help="Path to scenario YAML")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("runs"),
        help="Root directory for run outputs (default: runs/)",
    )
    parser.add_argument(
        "--no-strict",
        dest="strict",
        action="store_false",
        default=True,
        help="Disable strict-mode SoC/wasted/unmet assertions (use only while hacking)",
    )
    args = parser.parse_args()

    scenario = load_scenario(args.scenario)
    decide = _resolve_strategy(scenario.strategy)
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    run_dir = args.out_dir / scenario.scenario_id / ts
    logger = JsonlLogger(run_dir, scenario_id=scenario.scenario_id)
    try:
        summary = run(scenario, decide, logger, strict=args.strict)
    finally:
        logger.close()

    print(
        f"scenario={scenario.scenario_id} "
        f"served={summary['served_load_fraction']:.3f} "
        f"gini={summary['gini_welfare']:.3f} "
        f"wasted_kwh={summary['wasted_kwh_total']:.1f} "
        f"unmet_kwh={summary['unmet_kwh_total']:.1f} "
        f"transfers={summary['transfer_count']} "
        f"-> {run_dir}"
    )


if __name__ == "__main__":
    main()
