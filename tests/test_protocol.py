"""Speech-act Message schema + MessageBus (Tasks 4, 8, 9)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from sim.agents.protocol import Message, MessageBus, new_correlation_id
from sim.network import Neighborhood


def test_message_is_frozen() -> None:
    m = Message(
        t_sent=datetime(2026, 1, 1, 8, 0),
        sender="r0c0",
        recipient="r0c1",
        performative="REQUEST",
        payload={"kwh": 0.5},
        rationale_nl="my SoC is low",
        correlation_id="abc",
    )
    with pytest.raises((AttributeError, TypeError)):
        m.payload = {"kwh": 1.0}  # type: ignore[misc]


def test_message_performative_validated() -> None:
    with pytest.raises(ValueError, match="performative"):
        Message(
            t_sent=datetime(2026, 1, 1, 8, 0),
            sender="r0c0",
            recipient="r0c1",
            performative="SHRUG",  # type: ignore[arg-type]
            payload={},
            rationale_nl="",
            correlation_id="x",
        )


def test_new_correlation_id_unique_per_call() -> None:
    ids = {new_correlation_id() for _ in range(100)}
    assert len(ids) == 100


def test_new_correlation_id_deterministic_with_seeded_rng() -> None:
    import random

    rng1 = random.Random(42)
    rng2 = random.Random(42)
    a = [new_correlation_id(rng=rng1) for _ in range(5)]
    b = [new_correlation_id(rng=rng2) for _ in range(5)]
    assert a == b


# --- MessageBus tests (Task 8) ---


def _bus_neighborhood() -> Neighborhood:
    return Neighborhood(
        comm_graph={"r0c0": ["r0c1"], "r0c1": ["r0c0"], "r1c0": []},
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
        edges_by_type={
            "geographic": {"r0c0": ["r0c1"], "r0c1": ["r0c0"], "r1c0": []},
            "owner": {"r0c0": ["r1c0"], "r0c1": [], "r1c0": ["r0c0"]},
        },
    )


def _msg(t, sender, recipient, perf="REQUEST", kwh=0.5) -> Message:
    return Message(
        t_sent=t,
        sender=sender,
        recipient=recipient,
        performative=perf,
        payload={"kwh": kwh},
        rationale_nl="ok",
        correlation_id="x",
    )


def test_bus_delivers_next_tick() -> None:
    bus = MessageBus(neighborhood=_bus_neighborhood(), seed=42)
    t0 = datetime(2026, 1, 1, 8, 0)
    bus.send(_msg(t0, "r0c0", "r0c1"))
    assert bus.deliver_pending(t0) == {}
    inboxes = bus.deliver_pending(t0 + timedelta(minutes=15))
    assert "r0c1" in inboxes
    assert inboxes["r0c1"][0].sender == "r0c0"


def test_bus_routes_owner_layer_too() -> None:
    """r0c0 and r1c0 are not geographic neighbors but share an owner edge."""
    bus = MessageBus(neighborhood=_bus_neighborhood(), seed=42)
    t0 = datetime(2026, 1, 1, 8, 0)
    bus.send(_msg(t0, "r0c0", "r1c0"))
    inboxes = bus.deliver_pending(t0 + timedelta(minutes=15))
    assert "r1c0" in inboxes


def test_bus_rejects_off_graph_recipient() -> None:
    bus = MessageBus(neighborhood=_bus_neighborhood(), seed=42)
    t0 = datetime(2026, 1, 1, 8, 0)
    bus.send(_msg(t0, "r0c1", "r1c0"))
    inboxes = bus.deliver_pending(t0 + timedelta(minutes=15))
    assert "r1c0" not in inboxes
    drops = [
        r
        for r in bus.iter_log()
        if r["outcome"] == "dropped" and r["reason"] == "invalid_recipient"
    ]
    assert len(drops) == 1


def test_bus_log_jsonl_round_trip(tmp_path) -> None:
    bus = MessageBus(neighborhood=_bus_neighborhood(), seed=42)
    t0 = datetime(2026, 1, 1, 8, 0)
    bus.send(_msg(t0, "r0c0", "r0c1"))
    bus.deliver_pending(t0 + timedelta(minutes=15))
    bus.write_jsonl(tmp_path / "messages.jsonl")
    rows = [json.loads(line) for line in (tmp_path / "messages.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["outcome"] == "delivered"
    assert rows[0]["sender"] == "r0c0"
    assert rows[0]["recipient"] == "r0c1"
    assert rows[0]["performative"] == "REQUEST"


# --- MessageBus failure-mode tests (Task 9) ---


def test_bus_drops_per_circle_probability() -> None:
    bus = MessageBus(neighborhood=_bus_neighborhood(), seed=42)
    bus.configure_failure_modes(drop_prob_by_circle={"geographic": 1.0})
    t0 = datetime(2026, 1, 1, 8, 0)
    bus.send(_msg(t0, "r0c0", "r0c1"))
    inboxes = bus.deliver_pending(t0 + timedelta(minutes=15))
    assert inboxes == {}
    drops = [r for r in bus.iter_log() if r["reason"] == "comm_drop"]
    assert len(drops) == 1


def test_bus_owner_layer_preferred_over_geographic_for_dropout() -> None:
    nb = Neighborhood(
        comm_graph={"a": ["b"], "b": ["a"]},
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
        edges_by_type={
            "geographic": {"a": ["b"], "b": ["a"]},
            "owner": {"a": ["b"], "b": ["a"]},
        },
    )
    bus = MessageBus(neighborhood=nb, seed=42)
    bus.configure_failure_modes(drop_prob_by_circle={"geographic": 1.0, "owner": 0.0})
    t0 = datetime(2026, 1, 1, 8, 0)
    bus.send(_msg(t0, "a", "b"))
    inboxes = bus.deliver_pending(t0 + timedelta(minutes=15))
    assert "b" in inboxes


def test_bus_per_tick_budget_enforces_cap() -> None:
    bus = MessageBus(neighborhood=_bus_neighborhood(), seed=42)
    bus.configure_failure_modes(per_tick_budget=2)
    t0 = datetime(2026, 1, 1, 8, 0)
    bus.send(_msg(t0, "r0c0", "r0c1"))
    bus.send(_msg(t0, "r0c0", "r1c0"))
    bus.send(_msg(t0, "r0c0", "r0c1"))
    inboxes = bus.deliver_pending(t0 + timedelta(minutes=15))
    delivered = sum(len(v) for v in inboxes.values())
    assert delivered == 2
    overflows = [r for r in bus.iter_log() if r["reason"] == "budget_overflow"]
    assert len(overflows) == 1


def test_bus_dropout_is_deterministic_given_seed() -> None:
    nb = _bus_neighborhood()
    t0 = datetime(2026, 1, 1, 8, 0)

    def collect_outcomes(seed: int) -> list[str]:
        bus = MessageBus(neighborhood=nb, seed=seed)
        bus.configure_failure_modes(drop_prob_by_circle={"geographic": 0.5})
        for _ in range(20):
            bus.send(_msg(t0, "r0c0", "r0c1"))
        return [r["outcome"] for r in bus.iter_log()]

    a = collect_outcomes(123)
    b = collect_outcomes(123)
    assert a == b
    c = collect_outcomes(456)
    assert a != c
