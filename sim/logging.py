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

    def finalize(self, dt_hours: float) -> dict[str, Any]:
        """Compute top-level summary metrics from state + events, write summary.json."""
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
        # Phase 2 additive fields (zero defaults; Phase 1.x parsers ignore extra keys).
        summary["message_counts"] = phase2_message_counts(self.run_dir / "messages.jsonl")
        summary["llm_call_counts"] = {
            "reflect_plan": 0,
            "react_msg": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }
        summary["llm_cost_usd_estimated"] = 0.0
        summary["failure_modes_active"] = {}
        summary["policy_parse_failures"] = 0
        summary["policy_fallbacks_to_round_robin"] = 0
        with (self.run_dir / "summary.json").open("w") as f:
            json.dump(summary, f, indent=2)
        return summary


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
