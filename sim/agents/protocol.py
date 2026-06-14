"""Speech-act Message + MessageBus.

Performatives follow FIPA-ACL/speech-act tradition. The vocabulary is small enough
that recipient parsing is fully structured; only the ``rationale_nl`` field is
natural language, and it carries the explainability substrate Phase 3 evaluates.

MessageBus lands in Task 8; this module ships the Message type first so the
agent layer can be built bottom-up.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

Performative = Literal["REQUEST", "OFFER", "ACCEPT", "REJECT", "COUNTER", "INFORM"]

_VALID_PERFORMATIVES: frozenset[str] = frozenset(
    {"REQUEST", "OFFER", "ACCEPT", "REJECT", "COUNTER", "INFORM"}
)


@dataclass(frozen=True)
class Message:
    t_sent: datetime
    sender: str
    recipient: str
    performative: Performative
    payload: dict[str, Any]
    rationale_nl: str
    correlation_id: str

    def __post_init__(self) -> None:
        if self.performative not in _VALID_PERFORMATIVES:
            raise ValueError(
                f"performative must be one of {sorted(_VALID_PERFORMATIVES)}, "
                f"got {self.performative!r}"
            )


def new_correlation_id(rng: random.Random | None = None) -> str:
    """Return a short id for threading a negotiation.

    If ``rng`` is provided, the id is deterministic given that RNG's state.
    Engine-owned RNG is what tests pass in; production code uses ``uuid.uuid4``.
    """
    if rng is None:
        return uuid.uuid4().hex[:12]
    return f"{rng.getrandbits(48):012x}"
