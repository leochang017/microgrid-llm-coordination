"""Dose-response sweep driver (Phase 3 Task 9).

  python -m scripts.sweep --grid configs/sweeps/phase3_grid.yaml [--out-dir runs/sweeps]

Grid YAML shape:

  name: phase3_grid
  scenario: configs/scenarios/haves_havenots__llm.yaml
  strategies: [no_coordination, round_robin, llm_fallback]
  seeds: [23, 1, 7]
  axes:
    - name: defector_fraction
      set: failure_modes.defector_fraction
      values: [0.0, 0.2, 0.4]

Each axis is swept independently against the base scenario:
base + {set: value} x strategies x seeds. Every cell runs in ITS OWN
SUBPROCESS via `python -m scripts.run` — llm_agent-family strategies keep
module-level counter state, so in-process loops would cross-attribute
counters (see scripts/compare.py docstring).

Output: per-axis markdown dose-response tables (rows = axis values, one
column per strategy, cell = served mean over seeds with min-max range, plus
gini mean), printed and saved to <out-dir>/<name>/report.md (rewritten after
each axis; FAILED cells are recorded in-place and the sweep continues; per-cell
artifacts live under <out-dir>/<name>/cells/).

Costs nothing with mock/no-LLM strategies. Do NOT put `llm_agent` in a grid
without budgeting: every (value x seed) cell is a cold prompt cache.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


def _run_cell(
    scenario: str,
    strategy: str,
    seed: int,
    set_spec: str | None,
    out_dir: Path,
) -> dict[str, Any]:
    """Run one cell in a subprocess and return its summary.json contents."""
    cmd = [
        sys.executable,
        "-m",
        "scripts.run",
        "--scenario",
        scenario,
        "--strategy",
        strategy,
        "--seed",
        str(seed),
        "--out-dir",
        str(out_dir),
    ]
    if set_spec is not None:
        cmd += ["--set", set_spec]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"cell failed ({strategy}, seed {seed}, {set_spec}):\n{proc.stderr[-2000:]}"
        )
    # scripts/run prints "... -> <run_dir>" as the last line.
    run_dir = Path(proc.stdout.strip().splitlines()[-1].rsplit("-> ", 1)[1])
    summary: dict[str, Any] = json.loads((run_dir / "summary.json").read_text())
    return summary


def _fmt_cell(summaries: list[dict[str, Any]]) -> str:
    served = [s["served_load_fraction"] for s in summaries]
    gini = [s["gini_welfare"] for s in summaries]
    mean = sum(served) / len(served)
    return f"{mean:.4f} [{min(served):.4f},{max(served):.4f}] g={sum(gini) / len(gini):.3f}"


def run_grid(grid_path: Path, out_root: Path) -> str:
    grid = yaml.safe_load(grid_path.read_text())
    name = grid["name"]
    scenario = grid["scenario"]
    strategies: list[str] = grid["strategies"]
    seeds: list[int] = grid["seeds"]
    out_dir = out_root / name
    out_dir.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [f"# Sweep: {name}", "", f"scenario: `{scenario}`  seeds: {seeds}", ""]
    for axis in grid["axes"]:
        lines.append(f"## axis: {axis['name']} (`{axis['set']}`)")
        lines.append("")
        header = "| value | " + " | ".join(strategies) + " |"
        lines.append(header)
        lines.append("|" + "---|" * (len(strategies) + 1))
        for value in axis["values"]:
            set_spec = f"{axis['set']}={json.dumps(value)}"
            row = [str(value)]
            for strategy in strategies:
                try:
                    cell = [
                        _run_cell(scenario, strategy, seed, set_spec, out_dir / "cells")
                        for seed in seeds
                    ]
                    row.append(_fmt_cell(cell))
                except (RuntimeError, IndexError, OSError) as e:
                    # Record the failure in-place and keep sweeping — one bad
                    # cell must not discard a night of completed cells.
                    row.append("FAILED: " + str(e).splitlines()[0][:60].replace("|", "/"))
            lines.append("| " + " | ".join(row) + " |")
            print(lines[-1], flush=True)
        lines.append("")
        (out_dir / "report.md").write_text("\n".join(lines))
    report = "\n".join(lines)
    (out_dir / "report.md").write_text(report)
    return report


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--grid", type=Path, required=True, help="Sweep grid YAML")
    p.add_argument("--out-dir", type=Path, default=Path("runs/sweeps"))
    args = p.parse_args()
    report = run_grid(args.grid, args.out_dir)
    print("\n" + report)


if __name__ == "__main__":
    main()
