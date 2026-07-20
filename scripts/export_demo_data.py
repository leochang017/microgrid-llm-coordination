"""Export committed live runs into compact per-cell JSON for the Phase 4b web demo.

  python -m scripts.export_demo_data --out web/static/data
  python -m scripts.export_demo_data --cells clean,comm

$0, no API calls. The live numbers are READ from the committed
``reference_runs/<cell>/llm_agent/<run>/summary.json`` (never re-run, never
rounded); the $0 baselines + LP ceiling come from ``scripts.figures.collect_cell``,
which also runs the C6-3 frozen-config drift guard. Household attributes are
re-derived deterministically from the scenario seed via
``sim.engine.sample_households`` and cross-checked against the logged state, so a
scenario edit that silently changed the population fails loudly here.

The per-run ``llm_cache/`` and ``judge_cache/`` directories are NEVER read: the
export touches only ``state.jsonl``, ``events.jsonl``, ``messages.jsonl``,
``summary.json``, ``config.json``, and (when present) ``explanations_eval.json``.
No credential can therefore reach the emitted files.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path
from typing import Any

import numpy as np

from scripts import figures
from sim.agents.failure_modes import assign_defectors
from sim.engine import sample_households
from sim.scenario import Scenario, load_scenario

REPO = figures.REPO
REF = figures.REF

# The four cells the demo replays: slug -> (scenario cell, seed). Mirrors the
# committed (cell, seed) pairs in ``figures.LIVE_CELLS``; the clean cell's other
# two seeds (1, 7) ship only as the headline spread in meta.json.
DEMO_CELLS: dict[str, tuple[str, int]] = {
    "clean": ("haves_havenots_solar__llm", 23),
    "defectors": ("haves_havenots_solar__defectors", 7),
    "noise": ("haves_havenots_solar__noise", 23),
    "comm": ("haves_havenots_solar__comm", 23),
}


def scenario_blurb(scenario: Scenario, houses: list[dict[str, Any]]) -> str:
    """One-sentence framing of THIS cell's population, derived from its own houses.

    The have/have-not split is re-derived per SEED, so it genuinely differs across
    the demo cells (clean/noise/comm are seed 23 -> 9 haves / 21 have-nots;
    defectors is seed 7 -> 12 / 18). A shared hardcoded sentence was wrong on three
    of the four cards, so the counts are computed here and can never drift from the
    ``houses`` list they describe. The battery ranges below DO hold for every
    committed cell (haves 35.0-39.8 kWh, have-nots 2.07-3.96 kWh, measured).
    """
    n_have = sum(1 for h in houses if h["have"])
    n_not = len(houses) - n_have
    return (
        f"{len(houses)} households on a {scenario.rows}x{scenario.cols} distribution bus "
        f"ride out a 24 h full outage. {n_have} 'haves' own rooftop PV and 35-40 kWh "
        f"batteries; {n_not} 'have-nots' have no PV and 2-4 kWh. Energy is abundant but "
        "misplaced, so the whole game is whether the agents move the haves' midday solar "
        "into have-not batteries before nightfall."
    )


FAILURE_DESCRIPTIONS: dict[str, str] = {
    "clean": ("No failure modes; hardest of three committed seeds (23; seeds 1/7 shown as spread)"),
    # The selfish PLAN prompt (`sim/agents/agent.py:44-52`) does license misreporting
    # verbatim, so the blurb must not claim otherwise. It stays inert because
    # `emit_informs` (agent.py:905-934) is pure Python emitting the agent's own
    # `last_visible_own`, and `peer_beliefs` is fed ONLY by INFORMs (agent.py:245-247)
    # — the payload-mutating corruption wrapper is off in this cell
    # (`defector_realization: prompt`). Withholding is the only mechanism that operates.
    "defectors": (
        "6 of 30 households (seed 7) are prompted to put their own survival first — "
        "hoarding charge and declining requests. The prompt also permits misreporting, "
        "but state broadcasts are pure Python and unaffected, so withholding is the "
        "mechanism that actually operates. Realized dose: 33.6% of generation withheld."
    ),
    "noise": "Agents observe SoC with 10% and load with 15% Gaussian noise",
    "comm": (
        "2-msg/tick send budget + per-circle drops (geo 30%, owner 5%, DR 10%) "
        "— most INFORMs never arrive"
    ),
}

_MAX_FILE_BYTES = 15_000_000
_JUDGE_AXES = ("state_accuracy", "actionability", "consistency")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL artifact into a list of dicts."""
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def scenario_for(slug: str) -> Scenario:
    """The demo cell's scenario, seeded exactly as the committed live run was."""
    cell, seed = DEMO_CELLS[slug]
    return dataclasses.replace(load_scenario(figures.scenario_path(cell)), seed=seed)


def tick_times(state_rows: list[dict[str, Any]]) -> list[str]:
    """Sorted unique ISO timestamps, one per simulation tick."""
    return sorted({str(r["t"]) for r in state_rows})


def _r(x: float, nd: int) -> float:
    return round(float(x), nd)


def build_houses(scenario: Scenario, state_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Re-derive the household population and cross-check it against the run log.

    ``sample_households`` is deterministic in ``scenario.seed`` (same call the
    engine and ``figures.regen_baselines`` make), so this reconstructs exactly the
    population the committed run used. Two tripwires guard against silent scenario
    drift: no house may hold more energy than its battery capacity, and a house
    with PV must have generated at some tick while a house without must never
    have. Either mismatch raises rather than shipping a mislabeled demo.
    """
    households = sample_households(scenario, np.random.default_rng(scenario.seed))
    defectors = assign_defectors(sorted(households), scenario.failure_modes, scenario.seed)

    max_soc: dict[str, float] = {}
    max_solar: dict[str, float] = {}
    for row in state_rows:
        hid = str(row["house_id"])
        max_soc[hid] = max(max_soc.get(hid, 0.0), float(row["soc_kwh"]))
        max_solar[hid] = max(max_solar.get(hid, 0.0), float(row["solar_kw"]))

    houses: list[dict[str, Any]] = []
    for r in range(scenario.rows):
        for c in range(scenario.cols):
            hid = f"r{r}c{c}"
            h = households[hid]
            have = h.pv_kw_peak > 0.0
            if hid in max_soc and h.battery_kwh < max_soc[hid] - 1e-9:
                raise ValueError(
                    f"{hid}: logged soc_kwh {max_soc[hid]!r} exceeds re-derived battery "
                    f"capacity {h.battery_kwh!r} — the scenario YAML has drifted from the "
                    "committed run"
                )
            if hid in max_solar and have != (max_solar[hid] > 0.0):
                raise ValueError(
                    f"{hid}: re-derived pv_kw_peak {h.pv_kw_peak!r} disagrees with the logged "
                    f"peak solar {max_solar[hid]!r} — the scenario YAML has drifted from the "
                    "committed run"
                )
            houses.append(
                {
                    "id": hid,
                    "row": r,
                    "col": c,
                    "have": have,
                    "pvKwPeak": _r(h.pv_kw_peak, 3),
                    "batteryKwh": _r(h.battery_kwh, 3),
                    "criticalLoadFrac": _r(h.profile.critical_load_frac, 3),
                    "circles": dict(h.affiliations),
                    "defector": hid in defectors,
                }
            )
    return houses


def keep_message(m: dict[str, Any]) -> bool:
    """Downsample rule: keep everything except templated INFORM broadcasts.

    Templated INFORMs are ~half of every run's traffic and carry no negotiation
    content — their story (how many were sent, delivered, dropped per tick) is
    preserved losslessly by the per-tick ``informCounts`` aggregate in
    ``build_ticks``, which IS the comm-cell finding.
    """
    return m["performative"] != "INFORM" or not m["templated"]


def _msg_kwh(payload: dict[str, Any]) -> float | None:
    for key in ("kwh", "deficit_estimate"):
        if payload.get(key) is not None:
            return _r(payload[key], 2)
    return None


def build_messages(rows: list[dict[str, Any]], tick_of: dict[str, int]) -> dict[str, Any]:
    """Slim the kept messages down to the fields the demo's message panel renders.

    Two distinct ids ship per row, and they are NOT interchangeable:

    * ``id`` is unique per message (a zero-padded index over the built list) — it
      is what a keyed ``{#each}`` in the UI must use.
    * ``cid`` is the THREAD id: a REQUEST and its ACCEPT/COUNTER/REJECT reply
      deliberately share one ``correlation_id``, which is how a negotiation
      thread is tracked. On clean@23 that makes 12,258 rows carry only 8,210
      distinct ``cid`` values, so ``cid`` must never be used as a unique key.

    ``t_sent`` is looked up with ``[]``, not ``.get``: an out-of-horizon message
    would silently vanish and understate the message counts the demo reports, so
    the drift fails loudly instead (there are 0 such messages in all four cells).
    """
    out: list[dict[str, Any]] = []
    for m in rows:
        if not keep_message(m):
            continue
        payload = m.get("payload") or {}
        row: dict[str, Any] = {
            "id": f"m{len(out):05d}",
            "cid": m["correlation_id"],
            "t": tick_of[str(m["t_sent"])],
            "perf": m["performative"],
            "from": m["sender"],
            "to": m["recipient"],
            "outcome": m["outcome"],
            "reason": m.get("reason"),
            "why": m.get("rationale_nl"),
            "authored": not m["templated"],
        }
        kwh = _msg_kwh(payload)
        if kwh is not None:
            row["kwh"] = kwh
        if m["performative"] == "INFORM" and payload.get("soc_kwh") is not None:
            row["soc"] = _r(payload["soc_kwh"], 2)
        out.append(row)
    return {"messages": out}


def _capacities(
    state_rows: list[dict[str, Any]],
    messages_rows: list[dict[str, Any]],
    house_order: list[str],
) -> dict[str, float]:
    """Battery capacity per house, for the SoC-fraction grid.

    ``state.jsonl`` does not log capacity, so it is taken from the exact
    ``soc_capacity`` an INFORM payload carries. ``export_cell`` overrides this
    with the re-derived household capacities; the fallback exists so
    ``build_ticks`` stays usable (and testable) on the raw artifacts alone.

    A house with no INFORM-derived capacity raises rather than falling back to
    its largest observed ``soc_kwh`` — that fallback produced a plausible-looking
    but wrong curve peaking at exactly 1.0. Every house emits an INFORM in every
    committed cell, so this is a drift tripwire, matching ``build_houses``.
    """
    caps: dict[str, float] = {}
    for m in messages_rows:
        payload = m.get("payload") or {}
        cap = payload.get("soc_capacity")
        if cap is not None:
            hid = str(m["sender"])
            caps[hid] = max(caps.get(hid, 0.0), float(cap))
    missing = [hid for hid in house_order if caps.get(hid, 0.0) <= 0.0]
    if missing:
        raise ValueError(
            f"no INFORM-derived soc_capacity for {missing} — refusing to fall back to "
            "max-observed SoC, which would render a socFrac curve that wrongly peaks at 1.0"
        )
    # state.jsonl is still consulted, purely as a floor sanity check.
    for row in state_rows:
        hid = str(row["house_id"])
        if hid in caps and float(row["soc_kwh"]) > caps[hid] + 1e-9:
            raise ValueError(
                f"{hid}: logged soc_kwh {row['soc_kwh']!r} exceeds INFORM-derived capacity "
                f"{caps[hid]!r} — the artifacts have drifted"
            )
    return {hid: caps[hid] for hid in house_order}


def build_ticks(
    state_rows: list[dict[str, Any]],
    events_rows: list[dict[str, Any]],
    messages_rows: list[dict[str, Any]],
    tick_of: dict[str, int],
    house_order: list[str],
    dt_hours: float,
    capacities: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Columnar per-tick arrays: ``[tick][house]`` physics plus per-tick activity.

    ``servedFracCum[k]`` is the cumulative served-load fraction through tick k, so
    its last entry reproduces the run's headline ``served_load_fraction``.
    """
    n_t = len(tick_of)
    n_h = len(house_order)
    hidx = {hid: i for i, hid in enumerate(house_order)}
    caps = (
        capacities
        if capacities is not None
        else _capacities(state_rows, messages_rows, house_order)
    )

    soc = [[0.0] * n_h for _ in range(n_t)]
    solar = [[0.0] * n_h for _ in range(n_t)]
    load = [[0.0] * n_h for _ in range(n_t)]
    unmet = [[0.0] * n_h for _ in range(n_t)]
    load_kwh = [0.0] * n_t
    served_kwh = [0.0] * n_t
    for row in state_rows:
        k = tick_of[str(row["t"])]
        j = hidx[str(row["house_id"])]
        cap = caps.get(str(row["house_id"]), 0.0)
        soc[k][j] = _r(float(row["soc_kwh"]) / cap if cap > 0 else 0.0, 3)
        solar[k][j] = _r(row["solar_kw"], 3)
        load[k][j] = _r(row["load_kw"], 3)
        unmet[k][j] = _r(row["unmet_kwh"], 3)
        lk = float(row["load_kw"]) * dt_hours
        load_kwh[k] += lk
        served_kwh[k] += lk - float(row["unmet_kwh"])

    served_cum: list[float] = []
    num = 0.0
    den = 0.0
    for k in range(n_t):
        num += served_kwh[k]
        den += load_kwh[k]
        served_cum.append(_r(num / den if den > 0 else 0.0, 4))

    transfers: list[list[dict[str, Any]]] = [[] for _ in range(n_t)]
    events: list[list[dict[str, Any]]] = [[] for _ in range(n_t)]
    # ``[]`` not ``.get``: an out-of-horizon row would silently vanish and
    # understate what the demo reports, so drift fails loudly instead (there are
    # 0 such events/messages in all four committed cells).
    for e in events_rows:
        k = tick_of[str(e["t"])]
        kind = str(e["kind"])
        if kind == "transfer_executed":
            ids = list(e["house_ids"])
            transfers[k].append({"from": ids[0], "to": ids[1], "kw": _r(e["kw"], 2)})
        elif kind != "outage_started":
            events[k].append({"kind": kind, "houses": list(e["house_ids"]), "kw": _r(e["kw"], 2)})

    inform: list[dict[str, int]] = [{"sent": 0, "delivered": 0, "dropped": 0} for _ in range(n_t)]
    for m in messages_rows:
        if m["performative"] != "INFORM":
            continue
        k = tick_of[str(m["t_sent"])]
        inform[k]["sent"] += 1
        if m["outcome"] == "delivered":
            inform[k]["delivered"] += 1
        elif m["outcome"] == "dropped":
            inform[k]["dropped"] += 1

    return {
        "houseIds": list(house_order),
        "socFrac": soc,
        "solarKw": solar,
        "loadKw": load,
        "unmetKwh": unmet,
        "servedFracCum": served_cum,
        "transfers": transfers,
        "events": events,
        "informCounts": inform,
    }


def build_explanations(obj: dict[str, Any], tick_of: dict[str, int]) -> dict[str, Any]:
    """Reshape a committed ``explanations_eval.json`` into the demo's why-panel feed."""
    return {
        "rubricVariant": obj.get("rubric_variant", "default"),
        "means": dict(obj["means"]),
        "nScored": obj["n_scored"],
        "nAuthored": obj["n_llm_authored"],
        "nTemplated": obj["n_templated"],
        "samples": [
            {
                "sender": s["sender"],
                "t": tick_of[str(s["t_sent"])],
                "stateAccuracy": s["state_accuracy"],
                "actionability": s["actionability"],
                "consistency": s["consistency"],
            }
            for s in obj["samples"]
        ],
    }


def build_meta(
    slug: str,
    scenario: Scenario,
    houses: list[dict[str, Any]],
    methods: dict[str, dict[str, Any]],
    summary: dict[str, Any],
    tick_ts: list[str],
    expl: dict[str, Any] | None,
) -> dict[str, Any]:
    """Everything the demo needs that is not per-tick: labels, geometry, headline numbers.

    ``live`` and ``baselines`` are copied UNROUNDED so the demo can never disagree
    with the paper's golden pins (``figures.EXPECTED_LIVE``).
    """
    cell, seed = DEMO_CELLS[slug]
    run = figures.LIVE_CELLS[cell][seed]
    detailed = summary.get("llm_call_counts_detailed", {})
    outage = scenario.outages[0]
    meta: dict[str, Any] = {
        "cell": cell,
        "label": figures.CELL_LABEL[cell],
        "slug": slug,
        "seed": seed,
        "runDir": f"reference_runs/{cell}/llm_agent/{run}",
        "model": scenario.llm.get("model"),
        "scenarioBlurb": scenario_blurb(scenario, houses),
        "failureDescription": FAILURE_DESCRIPTIONS[slug],
        "dtHours": scenario.dt_hours,
        "tickCount": len(tick_ts),
        "tickTimes": tick_ts,
        "outage": {"start": outage.start.isoformat(), "end": outage.end.isoformat()},
        "rows": scenario.rows,
        "cols": scenario.cols,
        "busMaxKw": scenario.bus_max_kw,
        "houses": houses,
        "circles": {
            atype: {gid: list(members) for gid, members in groups.items()}
            for atype, groups in scenario.affiliations.items()
        },
        "defectors": [h["id"] for h in houses if h["defector"]],
        "live": {k: summary[k] for k in figures.METRIC_KEYS},
        "baselines": {
            m: {k: methods[m].get(k) for k in figures.METRIC_KEYS}
            for m in ("no_coordination", "llm_fallback", "round_robin", "lp_optimal")
        },
        "gapClosedControlToLp": figures.cell_served_gap_closed(methods),
        "messageCounts": summary["message_counts"],
        "negotiation": {
            "commitmentsMade": detailed.get("commitments_made"),
            "commitmentsExpired": detailed.get("commitments_expired"),
            "transferCount": summary["transfer_count"],
        },
    }
    if expl is not None:
        meta["judgeMeans"] = {axis: expl["means"][axis] for axis in _JUDGE_AXES}
    if cell == figures.CLEAN:
        meta["cleanSeedSpread"] = {
            str(s): figures.read_live_summary(cell, s)["served_load_fraction"] for s in (1, 7)
        }
    return meta


def _write(path: Path, obj: Any) -> int:
    """Write compact JSON + one trailing newline (pre-commit end-of-file-fixer parity)."""
    blob = json.dumps(obj, separators=(",", ":")) + "\n"
    raw = blob.encode()
    if len(raw) >= _MAX_FILE_BYTES:
        raise ValueError(
            f"refusing to write {path.name}: {len(raw)} bytes >= the {_MAX_FILE_BYTES}-byte "
            "demo payload ceiling"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return len(raw)


def export_cell(slug: str, out_root: Path) -> None:
    """Write ``<out_root>/<slug>/{meta,ticks,messages,explanations}.json``."""
    cell, seed = DEMO_CELLS[slug]
    run_dir = REF / cell / "llm_agent" / figures.LIVE_CELLS[cell][seed]

    scenario = scenario_for(slug)
    state_rows = load_jsonl(run_dir / "state.jsonl")
    events_rows = load_jsonl(run_dir / "events.jsonl")
    messages_rows = load_jsonl(run_dir / "messages.jsonl")
    summary = json.loads((run_dir / "summary.json").read_text())

    tick_ts = tick_times(state_rows)
    tick_of = {t: i for i, t in enumerate(tick_ts)}
    houses = build_houses(scenario, state_rows)
    house_order = [h["id"] for h in houses]

    ticks = build_ticks(
        state_rows,
        events_rows,
        messages_rows,
        tick_of,
        house_order,
        scenario.dt_hours,
        capacities={h["id"]: h["batteryKwh"] for h in houses},
    )
    # Served-load identity: the per-tick physics must reproduce the committed
    # headline exactly BEFORE the 4-dp rounding the demo ships.
    total_load = sum(float(r["load_kw"]) * scenario.dt_hours for r in state_rows)
    total_served = total_load - sum(float(r["unmet_kwh"]) for r in state_rows)
    served = total_served / total_load
    if abs(served - summary["served_load_fraction"]) >= 1e-9:
        raise ValueError(
            f"{slug}: served-load identity broken — state.jsonl gives {served!r}, "
            f"summary.json says {summary['served_load_fraction']!r}"
        )

    expl_path = run_dir / "explanations_eval.json"
    expl = (
        build_explanations(json.loads(expl_path.read_text()), tick_of)
        if expl_path.exists()
        else None
    )
    methods = figures.collect_cell(cell, seed)
    meta = build_meta(slug, scenario, houses, methods, summary, tick_ts, expl)

    out_dir = out_root / slug
    sizes = [
        (out_dir / "meta.json", _write(out_dir / "meta.json", meta)),
        (out_dir / "ticks.json", _write(out_dir / "ticks.json", ticks)),
        (
            out_dir / "messages.json",
            _write(out_dir / "messages.json", build_messages(messages_rows, tick_of)),
        ),
    ]
    if expl is not None:
        sizes.append((out_dir / "explanations.json", _write(out_dir / "explanations.json", expl)))
    print(f"{slug}: " + ", ".join(f"{p.name} {n:,} B" for p, n in sizes))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--out", default="web/static/data", help="output root directory")
    p.add_argument("--cells", default=",".join(DEMO_CELLS), help="comma-separated demo slugs")
    args = p.parse_args(argv)
    slugs = [s.strip() for s in str(args.cells).split(",") if s.strip()]
    unknown = [s for s in slugs if s not in DEMO_CELLS]
    if unknown:
        raise SystemExit(f"unknown demo cell(s) {unknown}; known: {sorted(DEMO_CELLS)}")
    out_root = Path(args.out)
    for slug in slugs:
        export_cell(slug, out_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
