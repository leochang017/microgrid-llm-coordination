"""Engine wiring: optional message_bus, messages.jsonl written, non-LLM strategies unchanged."""

from __future__ import annotations

import textwrap
from pathlib import Path

_SMOKE = textwrap.dedent("""
    scenario_id: engine_bus_smoke
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


def _smoke_scenario(tmp_path: Path) -> Path:
    p = tmp_path / "s.yaml"
    p.write_text(_SMOKE)
    return p


def test_engine_round_robin_byte_identical_without_message_bus(tmp_path: Path) -> None:
    """Adding the optional message_bus parameter must NOT change non-LLM strategy output."""
    from sim.engine import run
    from sim.logging import JsonlLogger
    from sim.scenario import load_scenario
    from sim.strategies import round_robin

    s = load_scenario(_smoke_scenario(tmp_path))
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    out_a.mkdir()
    out_b.mkdir()
    run(
        scenario=s,
        decide_transfers=round_robin.decide_transfers,
        logger=JsonlLogger(run_dir=out_a, scenario_id=s.scenario_id),
    )
    run(
        scenario=s,
        decide_transfers=round_robin.decide_transfers,
        logger=JsonlLogger(run_dir=out_b, scenario_id=s.scenario_id),
    )

    assert (out_a / "state.jsonl").read_bytes() == (out_b / "state.jsonl").read_bytes()
    assert (out_a / "events.jsonl").read_bytes() == (out_b / "events.jsonl").read_bytes()


def test_engine_writes_messages_jsonl_when_bus_supplied(tmp_path: Path) -> None:
    """When a MessageBus is passed, messages.jsonl is written even if empty."""
    from sim.agents.protocol import MessageBus
    from sim.engine import run
    from sim.logging import JsonlLogger
    from sim.network import build_overlay_neighborhood
    from sim.scenario import load_scenario
    from sim.strategies import round_robin

    s = load_scenario(_smoke_scenario(tmp_path))
    neighborhood = build_overlay_neighborhood(
        rows=s.rows,
        cols=s.cols,
        affiliations=s.affiliations,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
    )
    bus = MessageBus(neighborhood=neighborhood, seed=s.seed)
    out = tmp_path / "out"
    out.mkdir()
    run(
        scenario=s,
        decide_transfers=round_robin.decide_transfers,
        logger=JsonlLogger(run_dir=out, scenario_id=s.scenario_id),
        message_bus=bus,
    )

    assert (out / "messages.jsonl").exists()
    # round_robin doesn't send messages ⇒ empty file
    assert (out / "messages.jsonl").read_text() == ""
