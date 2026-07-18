"""Speech-act Message + MessageBus.

Performatives follow FIPA-ACL/speech-act tradition. The vocabulary is small enough
that recipient parsing is fully structured; only the ``rationale_nl`` field is
natural language, and it carries the explainability substrate Phase 3 evaluates.

MessageBus lands in Task 8; this module ships the Message type first so the
agent layer can be built bottom-up.
"""

from __future__ import annotations

import json
import random
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from sim.agents.seeding import stable_seed
from sim.network import Neighborhood

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
    # Phase 3 explainability provenance: True when the rationale is a Python
    # f-string template (act/emit_informs/emit_requests), False when it was
    # authored by the LLM (react replies, and any future LLM-written text).
    # The explanation judge only scores LLM-authored rationales as
    # "explanations"; templated ones are reported separately.
    templated: bool = True

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


@dataclass
class _LogRow:
    t_sent: datetime
    t_decided: datetime
    sender: str
    recipient: str
    performative: str
    payload: dict[str, Any]
    rationale_nl: str
    correlation_id: str
    outcome: Literal["delivered", "dropped", "pending_at_end"]
    templated: bool = True
    reason: str | None = None


@dataclass
class MessageBus:
    """One-tick-latency message queue with structured routing and per-message logging.

    Messages sent at tick t are delivered at tick t+dt (default 15 min). The bus enforces:
    - routing through Neighborhood.union_neighbors (any overlay edge type),
    - dropout per failure_modes.comm.drop_prob_by_circle (via configure_failure_modes),
    - per-tick send budget per agent (via configure_failure_modes).

    All decisions are logged to an in-memory list; write_jsonl dumps to messages.jsonl.
    Drops are logged with a reason.
    """

    neighborhood: Neighborhood
    seed: int = 0
    # One tick — pass timedelta(hours=scenario.dt_hours); the 15-min default only
    # matches dt_hours=0.25 scenarios.
    dt: timedelta = field(default_factory=lambda: timedelta(minutes=15))

    _queue: list[Message] = field(default_factory=list)
    _log: list[_LogRow] = field(default_factory=list)
    _rng: random.Random = field(init=False, repr=False)
    _drop_prob_by_circle: dict[str, float] = field(default_factory=dict)
    _per_tick_budget: int | None = field(default=None)
    _budget_used: dict[tuple[datetime, str], int] = field(default_factory=lambda: defaultdict(int))

    def __post_init__(self) -> None:
        self._rng = random.Random(stable_seed(self.seed, "bus"))

    def configure_failure_modes(
        self,
        drop_prob_by_circle: dict[str, float] | None = None,
        per_tick_budget: int | None = None,
    ) -> None:
        self._drop_prob_by_circle = dict(drop_prob_by_circle or {})
        self._per_tick_budget = per_tick_budget

    def send(self, m: Message) -> bool:
        """Attempt to enqueue ``m`` for delivery.

        Returns True iff the message entered the delivery queue… False iff
        the bus refused it (budget_overflow, invalid_recipient, comm_drop) —
        the recipient will never see it. Callers registering state against a
        message (commitment ledgers) must treat False as "this message does
        not exist for the recipient" (C1 fix, 2026-07-18).
        """
        if self._per_tick_budget is not None:
            key = (m.t_sent, m.sender)
            self._budget_used[key] += 1
            if self._budget_used[key] > self._per_tick_budget:
                self._log.append(
                    _LogRow(
                        t_sent=m.t_sent,
                        t_decided=m.t_sent,
                        sender=m.sender,
                        recipient=m.recipient,
                        performative=m.performative,
                        payload=dict(m.payload),
                        rationale_nl=m.rationale_nl,
                        correlation_id=m.correlation_id,
                        templated=m.templated,
                        outcome="dropped",
                        reason="budget_overflow",
                    )
                )
                return False
        if m.recipient not in self.neighborhood.union_neighbors(m.sender):
            self._log.append(
                _LogRow(
                    t_sent=m.t_sent,
                    t_decided=m.t_sent,
                    sender=m.sender,
                    recipient=m.recipient,
                    performative=m.performative,
                    payload=dict(m.payload),
                    rationale_nl=m.rationale_nl,
                    correlation_id=m.correlation_id,
                    templated=m.templated,
                    outcome="dropped",
                    reason="invalid_recipient",
                )
            )
            return False
        circle = self._circle_between(m.sender, m.recipient)
        drop_p = self._drop_prob_by_circle.get(circle, 0.0)
        if drop_p > 0 and self._rng.random() < drop_p:
            self._log.append(
                _LogRow(
                    t_sent=m.t_sent,
                    t_decided=m.t_sent,
                    sender=m.sender,
                    recipient=m.recipient,
                    performative=m.performative,
                    payload=dict(m.payload),
                    rationale_nl=m.rationale_nl,
                    correlation_id=m.correlation_id,
                    templated=m.templated,
                    outcome="dropped",
                    reason="comm_drop",
                )
            )
            return False
        self._queue.append(m)
        return True

    def deliver_pending(self, now: datetime) -> dict[str, list[Message]]:
        inboxes: dict[str, list[Message]] = defaultdict(list)
        keep: list[Message] = []
        for m in self._queue:
            if m.t_sent + self.dt <= now:
                inboxes[m.recipient].append(m)
                self._log.append(
                    _LogRow(
                        t_sent=m.t_sent,
                        t_decided=now,
                        sender=m.sender,
                        recipient=m.recipient,
                        performative=m.performative,
                        payload=dict(m.payload),
                        rationale_nl=m.rationale_nl,
                        correlation_id=m.correlation_id,
                        templated=m.templated,
                        outcome="delivered",
                    )
                )
            else:
                keep.append(m)
        self._queue = keep
        return dict(inboxes)

    def iter_log(self) -> list[dict[str, Any]]:
        return [
            {
                "t_sent": r.t_sent.isoformat(),
                "t_decided": r.t_decided.isoformat(),
                "sender": r.sender,
                "recipient": r.recipient,
                "performative": r.performative,
                "payload": r.payload,
                "rationale_nl": r.rationale_nl,
                "correlation_id": r.correlation_id,
                "templated": r.templated,
                "outcome": r.outcome,
                "reason": r.reason,
            }
            for r in self._log
        ]

    def flush_undelivered(self) -> None:
        """Log messages still queued when the run ends. Without this the final
        tick's accepted traffic appears in NO output (2026-07-12 fix)."""
        for m in self._queue:
            self._log.append(
                _LogRow(
                    t_sent=m.t_sent,
                    t_decided=m.t_sent,
                    sender=m.sender,
                    recipient=m.recipient,
                    performative=m.performative,
                    payload=dict(m.payload),
                    rationale_nl=m.rationale_nl,
                    correlation_id=m.correlation_id,
                    templated=m.templated,
                    outcome="pending_at_end",
                )
            )
        self._queue = []

    def write_jsonl(self, path: Path) -> None:
        self.flush_undelivered()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for row in self.iter_log():
                f.write(json.dumps(row, sort_keys=True) + "\n")

    def _circle_between(self, sender: str, recipient: str) -> str:
        """Return the (deterministic) circle name connecting sender and recipient.

        Preference: any non-geographic overlay first (alphabetical), then geographic.
        """
        for circle in sorted(self.neighborhood.edges_by_type):
            if circle == "geographic":
                continue
            if recipient in self.neighborhood.edges_by_type[circle].get(sender, []):
                return circle
        return "geographic"
