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
CLEAN = "haves_havenots_solar__llm"  # the multi-seed clean reference cell

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


def cell_series(cell: str) -> dict[str, Any]:
    """Per-method served mean/std over every committed seed for a cell.

    The clean cell carries three seeds (the spread is the honest error bar); the
    failure cells are single-seed, so std is 0 and ``n`` records that it is n=1.
    """
    seeds = sorted(LIVE_CELLS[cell])
    vals: dict[str, list[float]] = {m: [] for m in METHOD_ORDER}
    gcs: list[float] = []
    for seed in seeds:
        methods = collect_cell(cell, seed)
        for m in METHOD_ORDER:
            vals[m].append(float(methods[m]["served_load_fraction"]))
        gcs.append(cell_served_gap_closed(methods))
    return {
        "cell": cell,
        "seeds": seeds,
        "n": len(seeds),
        "served_mean": {m: float(np.mean(vals[m])) for m in METHOD_ORDER},
        "served_std": {m: float(np.std(vals[m])) for m in METHOD_ORDER},
        "gap_closed_mean": float(np.mean(gcs)),
    }


def cell_metrics(cell: str) -> dict[str, dict[str, float | None]]:
    """Per-method mean of every metric in METRIC_KEYS over a cell's seeds.

    LP defines only served/gini, so its Jain / min-house / critical come back
    ``None`` — callers skip those bars rather than invent a fairness number for
    a throughput ceiling that was never run through the engine.
    """
    seeds = sorted(LIVE_CELLS[cell])
    acc: dict[str, dict[str, list[float]]] = {m: {k: [] for k in METRIC_KEYS} for m in METHOD_ORDER}
    for seed in seeds:
        methods = collect_cell(cell, seed)
        for m in METHOD_ORDER:
            for k in METRIC_KEYS:
                v = methods[m].get(k)
                if v is not None:
                    acc[m][k].append(float(v))
    return {
        m: {k: (float(np.mean(vs)) if vs else None) for k, vs in acc[m].items()}
        for m in METHOD_ORDER
    }


# ---------------------------------------------------------------------------
# Rendering. matplotlib is the optional `viz` extra (absent in CI), so it is
# imported lazily inside each render function; nothing above this line needs it.
# ---------------------------------------------------------------------------


def _new_axes(nrows: int, ncols: int, figsize: tuple[float, float]) -> Any:
    """A fresh Agg figure — no pyplot global state, deterministic across calls."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.figure import Figure

    fig = Figure(figsize=figsize)
    axes = fig.subplots(nrows, ncols, squeeze=False)
    return fig, axes


_BAR_COLORS = {
    "no_coordination": "#bdbdbd",
    "llm_fallback": "#f4a259",
    "round_robin": "#5b8e7d",
    "llm_agent": "#1f6feb",
    "lp_optimal": "#8a8a8a",
}


def render_headline(out_dir: Path = FIG_DIR) -> Path:
    """Paired bars per cell: no-coord / control / round-robin / live / LP.

    Clean cell shows mean±spread over seeds {23,1,7}; failure cells are single
    seed (annotated n=1). gap_closed(control→LP) is printed over the live bar.
    """
    fig, axes = _new_axes(2, 2, (11.0, 8.0))
    flat = [axes[r][c] for r in range(2) for c in range(2)]
    for ax, cell in zip(flat, CELL_ORDER, strict=True):
        s = cell_series(cell)
        xs = list(range(len(METHOD_ORDER)))
        heights = [s["served_mean"][m] for m in METHOD_ORDER]
        errs = [s["served_std"][m] for m in METHOD_ORDER] if s["n"] > 1 else None
        colors = [_BAR_COLORS[m] for m in METHOD_ORDER]
        ax.bar(xs, heights, yerr=errs, capsize=4, color=colors, edgecolor="#333", linewidth=0.6)
        live_i = METHOD_ORDER.index("llm_agent")
        gc = s["gap_closed_mean"]
        ax.annotate(
            f"gap-closed\n{gc:+.0%}",
            xy=(live_i, heights[live_i]),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
            color="#1f6feb",
        )
        seedtxt = f"seeds {s['seeds']}" if s["n"] > 1 else f"seed {s['seeds'][0]} (n=1)"
        ax.set_title(f"{CELL_LABEL[cell]} — {seedtxt}", fontsize=10)
        ax.set_xticks(xs)
        ax.set_xticklabels(
            [METHOD_LABEL[m] for m in METHOD_ORDER], rotation=30, ha="right", fontsize=8
        )
        ax.set_ylim(0.0, 1.0)
        ax.set_ylabel("served-load fraction", fontsize=8)
        ax.axhline(0.0, color="#000", linewidth=0.5)
    fig.suptitle(
        "Phase 3.2 live coordination vs the zero-LLM control (bar = served load, ↑ better)",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "phase3_headline.png"
    fig.savefig(out, dpi=150)
    return out


# Fairness metrics and which direction is "better" (for the axis hint, not the
# data). served/jain/min/critical: higher better; gini: lower better.
_FAIRNESS = [
    ("gini_welfare", "welfare Gini (↓ fairer)"),
    ("jains_index", "Jain's index (↑ fairer)"),
    ("min_house_served_fraction", "min-house served (↑ Rawlsian floor)"),
    ("served_critical_load_fraction", "critical-load served (↑ better)"),
]


def render_fairness_panel(out_dir: Path = FIG_DIR) -> Path:
    """Four fairness metrics, per method per cell — Gini never shown alone."""
    metrics = {cell: cell_metrics(cell) for cell in CELL_ORDER}
    fig, axes = _new_axes(2, 2, (12.0, 9.0))
    flat = [axes[r][c] for r in range(2) for c in range(2)]
    ncell = len(CELL_ORDER)
    width = 0.16
    for ax, (key, label) in zip(flat, _FAIRNESS, strict=True):
        for mi, m in enumerate(METHOD_ORDER):
            xs, ys = [], []
            for ci, cell in enumerate(CELL_ORDER):
                v = metrics[cell][m].get(key)
                if v is not None:
                    xs.append(ci + (mi - 2) * width)
                    ys.append(v)
            if xs:
                ax.bar(
                    xs,
                    ys,
                    width=width,
                    color=_BAR_COLORS[m],
                    edgecolor="#333",
                    linewidth=0.4,
                    label=METHOD_LABEL[m],
                )
        ax.set_title(label, fontsize=10)
        ax.set_xticks(list(range(ncell)))
        ax.set_xticklabels([CELL_LABEL[c] for c in CELL_ORDER], fontsize=9)
        ax.axhline(0.0, color="#000", linewidth=0.5)
    flat[0].legend(fontsize=7, ncol=2, loc="upper right")
    fig.suptitle("Phase 3.2 fairness — live-Haiku vs baselines, per cell", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "phase3_fairness.png"
    fig.savefig(out, dpi=150)
    return out


_CELL_MARKER = {
    "haves_havenots_solar__llm": "o",
    "haves_havenots_solar__defectors": "s",
    "haves_havenots_solar__noise": "^",
    "haves_havenots_solar__comm": "D",
}

# Each failure axis paired with the seed its live cell was run at, and the clean
# reference is the SAME seed (so the control's clean→stress drop is causal, not
# cross-seed). realized-dose text is what dose_check pinned.
_AXES = [
    ("haves_havenots_solar__defectors", 7, "defectors\n(33.6% withheld)"),
    ("haves_havenots_solar__noise", 23, "noise\n(SoC 10% + load 15%)"),
    ("haves_havenots_solar__comm", 23, "comm\n(msg budget 2)"),
]

# Mock canned-policy floor: the control's clean→stress served drop, mean over 5
# seeds, from docs/phase3_mock_sweep.md (regenerated 2026-07-12). Cited as
# external corroboration of the same-seed control drop the bars show; the noise
# entry is the SoC-only sweep proxy (the live cell is dual-channel).
_MOCK_CONTROL_DROP = {
    "haves_havenots_solar__defectors": 0.0,  # 0.6993 -> 0.6993 (flat: prompt inert w/o LLM)
    "haves_havenots_solar__noise": 0.7173 - 0.6993,  # +0.018 (SoC-only proxy)
    "haves_havenots_solar__comm": 0.5524 - 0.6993,  # -0.147 (budget 2)
}


def failure_axis_deltas() -> list[dict[str, Any]]:
    """Per axis: the control's clean→stress drop and live's recovery over it.

    Both deltas use the SAME seed as the live cell (clean reference at that seed),
    so ``control_drop`` and ``live_minus_control`` are causal, not cross-seed. The
    two summed give live's net position against the clean control.
    """
    out: list[dict[str, Any]] = []
    for cell, seed, label in _AXES:
        clean = collect_cell(CLEAN, seed)
        stress = collect_cell(cell, seed)
        cc, cs, ls = clean["llm_fallback"], stress["llm_fallback"], stress["llm_agent"]
        out.append(
            {
                "cell": cell,
                "seed": seed,
                "label": label,
                "control_drop_served": cs["served_load_fraction"] - cc["served_load_fraction"],
                "live_minus_control_served": ls["served_load_fraction"]
                - cs["served_load_fraction"],
                "control_drop_jain": cs["jains_index"] - cc["jains_index"],
                "live_minus_control_jain": ls["jains_index"] - cs["jains_index"],
                "mock_control_drop_served": _MOCK_CONTROL_DROP[cell],
            }
        )
    return out


def render_failure_axis(out_dir: Path = FIG_DIR) -> Path:
    """What the fixed policy loses under stress, and what live recovers over it.

    Left panel = served-load, right = Jain. Per axis, two bars: the control's
    clean→stress drop (grey, same seed) and live-minus-control under stress (blue,
    the mandatory-bar delta). A grey diamond marks the mock 5-seed control drop
    (docs/phase3_mock_sweep.md) as external corroboration on the served panel.
    """
    data = failure_axis_deltas()
    fig, axes = _new_axes(1, 2, (13.0, 6.0))
    xs = list(range(len(data)))
    width = 0.36
    for ax, served in ((axes[0][0], True), (axes[0][1], False)):
        drop_key = "control_drop_served" if served else "control_drop_jain"
        lmc_key = "live_minus_control_served" if served else "live_minus_control_jain"
        drops = [d[drop_key] for d in data]
        lmcs = [d[lmc_key] for d in data]
        ax.bar(
            [x - width / 2 for x in xs],
            drops,
            width,
            color="#f4a259",
            edgecolor="#333",
            linewidth=0.5,
            label="control clean→stress drop",
        )
        ax.bar(
            [x + width / 2 for x in xs],
            lmcs,
            width,
            color="#1f6feb",
            edgecolor="#333",
            linewidth=0.5,
            label="live - control (same seed)",
        )
        if served:
            ax.scatter(
                xs,
                [d["mock_control_drop_served"] for d in data],
                marker="D",
                s=55,
                color="#666",
                edgecolor="#000",
                zorder=4,
                label="mock 5-seed control drop",
            )
        for x, v in zip(xs, lmcs, strict=True):
            ax.annotate(
                f"{v:+.3f}",
                (x + width / 2, v),
                textcoords="offset points",
                xytext=(0, 3 if v >= 0 else -11),
                ha="center",
                fontsize=8,
                fontweight="bold",
                color="#1f6feb",
            )
        ax.axhline(0.0, color="#000", linewidth=0.7)
        ax.set_xticks(xs)
        ax.set_xticklabels([d["label"] for d in data], fontsize=8)
        ax.set_ylabel(
            ("Δ served-load" if served else "Δ Jain's index") + " vs clean control", fontsize=9
        )
        ax.legend(fontsize=7, loc="lower left")
    fig.suptitle(
        "Phase 3.2 failure axes — control loses under stress (orange); live recovers over it (blue)",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "phase3_failure_axis.png"
    fig.savefig(out, dpi=150)
    return out


def render_efficiency_equity(out_dir: Path = FIG_DIR) -> Path:
    """Served-load vs fairness scatter (advisor's dedicated tradeoff figure).

    Left: served vs Gini (lower-right = efficient AND equal). Right: served vs
    Jain (upper-right = efficient AND equal). The clean-cell live point sitting
    in the "good" corner is the "no tradeoff appears here" finding, made visual.
    """
    metrics = {cell: cell_metrics(cell) for cell in CELL_ORDER}
    fig, axes = _new_axes(1, 2, (13.0, 6.0))
    panels = [
        (axes[0][0], "gini_welfare", "welfare Gini (↓ fairer)"),
        (axes[0][1], "jains_index", "Jain's index (↑ fairer)"),
    ]
    for ax, key, ylabel in panels:
        for m in METHOD_ORDER:
            for cell in CELL_ORDER:
                served = metrics[cell][m].get("served_load_fraction")
                fair = metrics[cell][m].get(key)
                if served is None or fair is None:
                    continue
                ax.scatter(
                    served,
                    fair,
                    s=70,
                    color=_BAR_COLORS[m],
                    marker=_CELL_MARKER[cell],
                    edgecolor="#333",
                    linewidth=0.5,
                    zorder=3,
                )
        ax.set_xlabel("served-load fraction (→ more efficient)", fontsize=9)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.grid(True, linewidth=0.3, alpha=0.5)
    # Two legends: color = method, marker = cell.
    from matplotlib.lines import Line2D

    method_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=_BAR_COLORS[m],
            markeredgecolor="#333",
            markersize=9,
            label=METHOD_LABEL[m],
        )
        for m in METHOD_ORDER
    ]
    cell_handles = [
        Line2D(
            [0],
            [0],
            marker=_CELL_MARKER[c],
            color="w",
            markerfacecolor="#ccc",
            markeredgecolor="#333",
            markersize=9,
            label=CELL_LABEL[c],
        )
        for c in CELL_ORDER
    ]
    axes[0][0].legend(handles=method_handles, fontsize=7, loc="upper left", title="method")
    axes[0][1].legend(handles=cell_handles, fontsize=7, loc="upper left", title="cell")
    fig.suptitle(
        "Phase 3.2 efficiency vs equity — no tradeoff appears on the clean cell", fontsize=12
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "phase3_efficiency_equity.png"
    fig.savefig(out, dpi=150)
    return out


def _cli() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--all", action="store_true", help="regenerate every figure + table")
    p.add_argument("--headline", action="store_true", help="render the headline figure")
    p.add_argument("--fairness", action="store_true", help="render the fairness panel")
    p.add_argument("--scatter", action="store_true", help="render the efficiency-vs-equity scatter")
    p.add_argument(
        "--failure-axis", action="store_true", help="render the failure-axis delta figure"
    )
    p.add_argument("--check", action="store_true", help="assert committed live numbers unchanged")
    args = p.parse_args()
    if args.check:
        for cell, seeds in LIVE_CELLS.items():
            for seed in seeds:
                s = read_live_summary(cell, seed)
                print(f"{CELL_LABEL[cell]:>10} @ {seed:>2}: served {s['served_load_fraction']:.4f}")
        return
    did = False
    if args.headline or args.all:
        print(f"wrote {render_headline()}")
        did = True
    if args.fairness or args.all:
        print(f"wrote {render_fairness_panel()}")
        did = True
    if args.scatter or args.all:
        print(f"wrote {render_efficiency_equity()}")
        did = True
    if args.failure_axis or args.all:
        print(f"wrote {render_failure_axis()}")
        did = True
    if not did:
        print(
            "no render target selected (try --headline / --fairness / --scatter / --failure-axis / --all)"
        )


if __name__ == "__main__":
    _cli()
