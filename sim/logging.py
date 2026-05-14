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
