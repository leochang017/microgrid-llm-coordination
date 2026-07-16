"""Run logging: state.jsonl, events.jsonl, config.json, summary.json."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sim.household import HouseholdState
from sim.types import Event


class JsonlLogger:
    """Writes per-tick state rows and discrete events to JSONL files in a run dir.

    File layout (one per scenario run):
      runs/<scenario_id>/<timestamp>/
        config.json    Resolved scenario config (one-shot, written at run start)
        state.jsonl    One JSON row per (house, tick)
        events.jsonl   One JSON row per discrete event
        summary.json   Top-level metrics, written by finalize() in Task 14
    """

    def __init__(self, run_dir: Path | str, scenario_id: str) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.scenario_id = scenario_id
        self._state_file = (self.run_dir / "state.jsonl").open("w")
        self._events_file = (self.run_dir / "events.jsonl").open("w")

    def write_config(self, config: dict[str, Any]) -> None:
        with (self.run_dir / "config.json").open("w") as f:
            json.dump(config, f, indent=2, default=str)

    def write_state(
        self,
        t: datetime,
        states: dict[str, HouseholdState],
        solar_kw: dict[str, float],
        load_kw: dict[str, float],
        grid: dict[str, bool],
    ) -> None:
        for hid, s in states.items():
            row = {
                "t": t.isoformat(),
                "house_id": hid,
                "soc_kwh": s.soc_kwh,
                "solar_kw": solar_kw[hid],
                "load_kw": load_kw[hid],
                "grid_status": grid[hid],
                "wasted_kwh": s.wasted_kwh,
                "unmet_kwh": s.unmet_kwh,
                "grid_import_kwh": s.grid_import_kwh,
                "grid_export_kwh": s.grid_export_kwh,
                "achieved_net_export_kw": s.achieved_net_export_kw,
            }
            self._state_file.write(json.dumps(row) + "\n")

    def write_events(self, events: list[Event], t: datetime) -> None:
        for e in events:
            row = {
                "t": t.isoformat(),
                "kind": e.kind.value,
                "house_ids": list(e.house_ids),
                "kw": e.kw,
                "details": e.details,
            }
            self._events_file.write(json.dumps(row) + "\n")

    def close(self) -> None:
        self._state_file.close()
        self._events_file.close()

    def finalize(
        self,
        dt_hours: float,
        *,
        failure_modes: dict[str, Any] | None = None,
        critical_frac_by_house: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Compute top-level summary metrics from state + events, write summary.json.

        ``failure_modes`` is the scenario's resolved failure-mode config; it lands
        in summary.json as ``failure_modes_active`` so a run directory records
        which cell it belongs to (was hardcoded {} before 2026-07-07).

        CAUTION — "active" means CONFIGURED FOR THIS CELL, not applied to this
        run. Failure modes have exactly one application site in the codebase:
        ``llm_agent.prepare`` (which ``llm_fallback`` also routes through).
        ``round_robin`` and ``lp_optimal`` never read them -- round_robin gets
        ``message_bus=None`` and reads engine ground truth; lp_optimal is an
        oracle over ground-truth profiles. So a round_robin summary.json in the
        comm cell truthfully reports ``per_tick_budget: 2`` while not one line
        of comm code ran, and its served_load_fraction is bit-identical to
        clean. Do not read this field as evidence a strategy was exposed to a
        failure mode; check the strategy first. (Verified 2026-07-16: the
        round_robin and lp_optimal baselines are identical across all five
        cells to 6 dp.)
        """
        # Re-read state.jsonl
        self._state_file.flush()
        load_by_house: dict[str, float] = {}
        unmet_by_house: dict[str, float] = {}
        wasted_total = 0.0
        with (self.run_dir / "state.jsonl").open() as f:
            for line in f:
                row = json.loads(line)
                h = row["house_id"]
                load_by_house[h] = load_by_house.get(h, 0.0) + row["load_kw"] * dt_hours
                unmet_by_house[h] = unmet_by_house.get(h, 0.0) + row["unmet_kwh"]
                wasted_total += row["wasted_kwh"]

        total_load = sum(load_by_house.values())
        total_unmet = sum(unmet_by_house.values())
        served_frac = 1.0 - (total_unmet / total_load if total_load > 0 else 0.0)
        per_house_served = [
            (load_by_house[h] - unmet_by_house.get(h, 0.0)) / load_by_house[h]
            if load_by_house[h] > 0
            else 1.0
            for h in load_by_house
        ]

        # Count transfers from events.jsonl
        self._events_file.flush()
        transfer_count = 0
        with (self.run_dir / "events.jsonl").open() as f:
            for line in f:
                row = json.loads(line)
                if row["kind"] == "transfer_executed":
                    transfer_count += 1

        summary: dict[str, Any] = {
            "scenario_id": self.scenario_id,
            "served_load_fraction": served_frac,
            "unmet_kwh_total": total_unmet,
            "wasted_kwh_total": wasted_total,
            "gini_welfare": _gini(per_house_served),
            "transfer_count": transfer_count,
        }
        # Phase 3 needs-aware fairness metrics (additive).
        summary["min_house_served_fraction"] = min(per_house_served) if per_house_served else 1.0
        summary["jains_index"] = _jains_index(per_house_served)
        summary["served_critical_load_fraction"] = _served_critical_fraction(
            load_by_house, unmet_by_house, critical_frac_by_house or {}
        )
        # Phase 2 additive fields (zero defaults; Phase 1.x parsers ignore extra keys).
        summary["message_counts"] = phase2_message_counts(self.run_dir / "messages.jsonl")
        summary["llm_call_counts"] = {
            "reflect_plan": 0,
            "react_msg": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }
        summary["llm_cost_usd_estimated"] = 0.0
        summary["failure_modes_active"] = failure_modes or {}
        summary["policy_parse_failures"] = 0
        summary["policy_fallbacks_to_round_robin"] = 0
        with (self.run_dir / "summary.json").open("w") as f:
            json.dump(summary, f, indent=2)
        return summary


def _jains_index(values: list[float]) -> float:
    """Jain's fairness index: (sum x)^2 / (n * sum x^2). 1.0 = perfectly even.

    Complements Gini for the paper's fairness pillar; defined as 1.0 for empty
    or all-zero inputs (no allocation to be unfair about).
    """
    if not values:
        return 1.0
    sq = sum(v * v for v in values)
    if sq <= 0:
        return 1.0
    total = sum(values)
    return (total * total) / (len(values) * sq)


def _served_critical_fraction(
    load_by_house: dict[str, float],
    unmet_by_house: dict[str, float],
    critical_frac_by_house: dict[str, float],
) -> float:
    """Fraction of CRITICAL load served, under the documented accounting rule:
    unmet energy hits flexible load first, so per house
    critical_unmet = max(0, unmet - flexible_load). Returns 1.0 when no house
    has any critical load configured (pre-Phase-3 scenarios)."""
    total_critical = 0.0
    total_critical_served = 0.0
    for hid, load in load_by_house.items():
        frac = float(critical_frac_by_house.get(hid, 0.0))
        if frac <= 0 or load <= 0:
            continue
        critical = frac * load
        flexible = load - critical
        unmet = unmet_by_house.get(hid, 0.0)
        critical_unmet = max(0.0, unmet - flexible)
        total_critical += critical
        total_critical_served += critical - min(critical, critical_unmet)
    if total_critical <= 0:
        return 1.0
    return total_critical_served / total_critical


def phase2_message_counts(messages_jsonl: Path) -> dict[str, int]:
    """Tally per-outcome counts from a messages.jsonl produced by MessageBus.

    Empty / missing file yields zeros.
    """
    counts = {
        "sent": 0,
        "delivered": 0,
        "dropped_invalid_recipient": 0,
        "dropped_comm": 0,
        "dropped_budget": 0,
        "pending_at_end": 0,
    }
    p = Path(messages_jsonl)
    if not p.exists():
        return counts
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        counts["sent"] += 1
        if row["outcome"] == "delivered":
            counts["delivered"] += 1
        elif row["outcome"] == "dropped":
            reason = row.get("reason") or ""
            if reason == "invalid_recipient":
                counts["dropped_invalid_recipient"] += 1
            elif reason == "comm_drop":
                counts["dropped_comm"] += 1
            elif reason == "budget_overflow":
                counts["dropped_budget"] += 1
        elif row["outcome"] == "pending_at_end":
            counts["pending_at_end"] += 1
    return counts


def _gini(values: list[float]) -> float:
    """Standard Gini coefficient.

    Returns 0 for perfectly equal welfare across households, approaches 1 for
    maximally unequal. Phase 1 uses per-household served-load fraction as the
    welfare proxy; Phase 3 will replace this with a needs-weighted welfare
    informed by the energy-justice literature.
    """
    if not values:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    total = sum(sorted_v)
    if total <= 0:
        return 0.0
    cum = sum((i + 1) * v for i, v in enumerate(sorted_v))
    return (2 * cum) / (n * total) - (n + 1) / n
