"""Phase 2 summary.json extensions are additive (Phase 1.x parsers unaffected)."""

from __future__ import annotations

import json
import textwrap
from datetime import datetime
from pathlib import Path

_SMOKE = textwrap.dedent("""
    scenario_id: smry
    start: "2018-01-01T08:00:00"
    end: "2018-01-01T08:45:00"
    dt_hours: 0.25
    seed: 1
    rows: 2
    cols: 2
    bus_max_kw: 50.0
    strategy: round_robin
    data_source: synthetic
    outages:
      - start: "2018-01-01T08:00:00"
        end: "2018-01-01T10:00:00"
        affected_houses: [r0c0, r0c1, r1c0, r1c1]
    household_sampling:
      pv_kw_peak: [4.0, 4.0]
      battery_kwh: [10.0, 10.0]
      rt_efficiency: 0.9
      dod_floor_frac: 0.1
""")


def test_summary_carries_phase2_fields_when_messages_jsonl_present(tmp_path: Path) -> None:
    from sim.agents.protocol import MessageBus
    from sim.engine import run
    from sim.logging import JsonlLogger
    from sim.network import build_overlay_neighborhood
    from sim.scenario import load_scenario
    from sim.strategies import round_robin

    p = tmp_path / "s.yaml"
    p.write_text(_SMOKE)
    s = load_scenario(p)

    nb = build_overlay_neighborhood(
        rows=s.rows,
        cols=s.cols,
        affiliations=s.affiliations,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
    )
    bus = MessageBus(neighborhood=nb, seed=s.seed)
    out = tmp_path / "out"
    out.mkdir()
    run(
        scenario=s,
        decide_transfers=round_robin.decide_transfers,
        logger=JsonlLogger(run_dir=out, scenario_id=s.scenario_id),
        message_bus=bus,
    )

    blob = json.loads((out / "summary.json").read_text())
    # Phase 1 fields are unchanged
    assert "served_load_fraction" in blob
    assert "gini_welfare" in blob
    # Phase 2 fields are present (zeros for non-LLM strategy)
    assert "message_counts" in blob
    assert blob["message_counts"]["sent"] == 0
    assert "llm_call_counts" in blob
    assert blob["llm_call_counts"]["reflect_plan"] == 0


def test_phase2_message_counts_categorizes_drops(tmp_path: Path) -> None:
    """When the bus drops messages, summary.message_counts reflects it."""
    from sim.agents.protocol import Message, MessageBus
    from sim.logging import phase2_message_counts
    from sim.network import build_overlay_neighborhood

    nb = build_overlay_neighborhood(
        rows=2,
        cols=2,
        affiliations={},
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
    )
    bus = MessageBus(neighborhood=nb, seed=1)
    bus.send(
        Message(
            t_sent=datetime(2026, 1, 1, 8, 0),
            sender="r0c0",
            recipient="r1c1",  # not neighbors
            performative="REQUEST",
            payload={"kwh": 0.5},
            rationale_nl="x",
            correlation_id="y",
        )
    )
    bus.write_jsonl(tmp_path / "messages.jsonl")
    counts = phase2_message_counts(tmp_path / "messages.jsonl")
    assert counts["sent"] == 1
    assert counts["dropped_invalid_recipient"] == 1
    assert counts["delivered"] == 0
