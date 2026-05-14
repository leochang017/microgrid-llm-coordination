"""Generate the Phase 1 headline result figure.

Runs the 24h_resstock_outage scenario with both `no_coordination` and
`round_robin` strategies on real Austin 2018 NREL solar + real Texas ResStock
load. Produces a 2x2 panel comparison figure showing:

  (a) Total served-load fraction
  (b) Welfare-equality Gini coefficient
  (c) Total unmet load (kWh)
  (d) Per-house unmet load, sorted

Saves the figure to docs/figures/phase1_real_data_result.png at 150 DPI.

Usage:
  python -m scripts.plot_phase1_results
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt

from sim.engine import run
from sim.logging import JsonlLogger
from sim.scenario import load_scenario
from sim.strategies.no_coordination import decide_transfers as no_coord
from sim.strategies.round_robin import decide_transfers as round_robin

SCENARIO_PATH = Path("configs/scenarios/24h_resstock_outage.yaml")
OUT_PATH = Path("docs/figures/phase1_real_data_result.png")


def _run_strategy(strategy, out_dir: Path) -> tuple[dict, dict[str, float]]:  # type: ignore[no-untyped-def]
    """Run one strategy; return (summary, unmet_by_house)."""
    s = load_scenario(SCENARIO_PATH)
    logger = JsonlLogger(out_dir, scenario_id=s.scenario_id)
    summary = run(s, strategy, logger, strict=True)
    logger.close()
    unmet: dict[str, float] = {}
    for line in (out_dir / "state.jsonl").read_text().splitlines():
        r = json.loads(line)
        unmet[r["house_id"]] = unmet.get(r["house_id"], 0.0) + r["unmet_kwh"]
    return summary, unmet


def main() -> None:
    print("Running no_coordination…")
    with tempfile.TemporaryDirectory() as nc_dir, tempfile.TemporaryDirectory() as rr_dir:
        nc_summary, nc_unmet = _run_strategy(no_coord, Path(nc_dir))
        print("Running round_robin…")
        rr_summary, rr_unmet = _run_strategy(round_robin, Path(rr_dir))

    # Per-house unmet, sorted by no_coord values (so the redistribution shape is clear)
    houses_sorted = sorted(nc_unmet.keys(), key=lambda h: -nc_unmet[h])
    nc_vals = [nc_unmet[h] for h in houses_sorted]
    rr_vals = [rr_unmet[h] for h in houses_sorted]

    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    fig.suptitle(
        "Phase 1 headline result — 30 real Texas homes, real Austin 2018 solar,\n"
        "12-hour overnight outage (18:00 → 06:00)",
        fontsize=12,
        fontweight="bold",
    )

    nc_color = "#c44e52"
    rr_color = "#4c72b0"
    labels = ("no_coordination", "round_robin")
    colors = (nc_color, rr_color)

    # (a) Served-load fraction
    ax = axes[0, 0]
    ax.bar(
        labels,
        [nc_summary["served_load_fraction"], rr_summary["served_load_fraction"]],
        color=colors,
    )
    ax.set_title("(a) Served-load fraction")
    ax.set_ylabel("fraction")
    ax.set_ylim(0.95, 1.0)
    for i, v in enumerate([nc_summary["served_load_fraction"], rr_summary["served_load_fraction"]]):
        ax.text(i, v + 0.001, f"{v:.4f}", ha="center", fontsize=10)

    # (b) Gini welfare
    ax = axes[0, 1]
    ax.bar(labels, [nc_summary["gini_welfare"], rr_summary["gini_welfare"]], color=colors)
    ax.set_title("(b) Welfare-inequality Gini\n(lower is more equitable)")
    ax.set_ylabel("Gini coefficient")
    for i, v in enumerate([nc_summary["gini_welfare"], rr_summary["gini_welfare"]]):
        ax.text(i, v + 0.0002, f"{v:.4f}", ha="center", fontsize=10)
    delta_pct = (1 - rr_summary["gini_welfare"] / nc_summary["gini_welfare"]) * 100
    ax.annotate(
        f"-{delta_pct:.1f}%",
        xy=(1, rr_summary["gini_welfare"]),
        xytext=(0.5, max(nc_summary["gini_welfare"], rr_summary["gini_welfare"]) * 0.6),
        ha="center",
        fontsize=12,
        fontweight="bold",
        color=rr_color,
        arrowprops=dict(arrowstyle="->", color=rr_color),
    )

    # (c) Total unmet kWh
    ax = axes[1, 0]
    ax.bar(labels, [nc_summary["unmet_kwh_total"], rr_summary["unmet_kwh_total"]], color=colors)
    ax.set_title("(c) Total unmet load")
    ax.set_ylabel("kWh")
    for i, v in enumerate([nc_summary["unmet_kwh_total"], rr_summary["unmet_kwh_total"]]):
        ax.text(i, v + 0.5, f"{v:.1f}", ha="center", fontsize=10)
    saved = nc_summary["unmet_kwh_total"] - rr_summary["unmet_kwh_total"]
    ax.annotate(
        f"{saved:.1f} kWh saved",
        xy=(1, rr_summary["unmet_kwh_total"]),
        xytext=(0.5, nc_summary["unmet_kwh_total"] * 0.65),
        ha="center",
        fontsize=12,
        fontweight="bold",
        color=rr_color,
        arrowprops=dict(arrowstyle="->", color=rr_color),
    )

    # (d) Per-house unmet, sorted
    ax = axes[1, 1]
    x = list(range(len(houses_sorted)))
    width = 0.4
    ax.bar([xi - width / 2 for xi in x], nc_vals, width=width, color=nc_color, label="no_coord")
    ax.bar([xi + width / 2 for xi in x], rr_vals, width=width, color=rr_color, label="round_robin")
    ax.set_title("(d) Unmet load per household, sorted by no_coord")
    ax.set_xlabel("house (sorted)")
    ax.set_ylabel("kWh unmet")
    ax.legend(loc="upper right")
    ax.set_xticks([])

    fig.tight_layout(rect=(0, 0, 1, 0.93))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PATH, dpi=150, bbox_inches="tight")
    print(f"\nSaved: {OUT_PATH}")
    print(
        f"\nResults:\n  no_coord    served={nc_summary['served_load_fraction']:.4f} "
        f"gini={nc_summary['gini_welfare']:.4f} unmet={nc_summary['unmet_kwh_total']:.2f} kWh"
        f"\n  round_robin served={rr_summary['served_load_fraction']:.4f} "
        f"gini={rr_summary['gini_welfare']:.4f} unmet={rr_summary['unmet_kwh_total']:.2f} kWh"
    )


if __name__ == "__main__":
    main()
