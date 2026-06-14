"""Speech-act Message schema. MessageBus tests land in Task 8."""

from __future__ import annotations

from datetime import datetime

import pytest

from sim.agents.protocol import Message, new_correlation_id


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
