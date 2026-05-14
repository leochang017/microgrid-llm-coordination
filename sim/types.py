"""Shared dataclass types used across the simulator."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class Transfer:
    """A requested or executed peer-to-peer energy transfer for one tick.

    `kw` is the sender-side power; receiver gets `kw * (1 - bus_loss_factor)`
    after `network.settle_transfers` applies transit loss.
    """

    from_id: str
    to_id: str
    kw: float

    def __post_init__(self) -> None:
        if self.from_id == self.to_id:
            raise ValueError(f"self-transfer not allowed (id={self.from_id})")
        if not math.isfinite(self.kw):
            raise ValueError(f"transfer kw must be finite, got {self.kw}")
        if self.kw <= 0:
            raise ValueError(f"transfer kw must be positive, got {self.kw}")


@dataclass(frozen=True, slots=True)
class HouseholdProfile:
    """Demographic / needs metadata for one household.

    Phase 1 stores this but does not use it in physics. Phase 2 LLM agents
    will consume `description` (free text) and the structured tags.
    """

    description: str
    has_medical: bool = False
    has_infant: bool = False
    essential_only: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)


class EventKind(StrEnum):
    """Discrete events emitted by the simulator during a tick."""

    OUTAGE_STARTED = "outage_started"
    OUTAGE_ENDED = "outage_ended"
    TRANSFER_EXECUTED = "transfer_executed"
    BUS_SATURATED = "bus_saturated"
    SENDER_DOD_FLOOR = "sender_dod_floor"
    RECEIVER_FULL = "receiver_full"
    RECEIVER_RATE_LIMITED = "receiver_rate_limited"
    UNMET_LOAD = "unmet_load"
    NO_WHEELING_REJECTED = "no_wheeling_rejected"


@dataclass(frozen=True, slots=True)
class Event:
    """One discrete event for the event log."""

    kind: EventKind
    house_ids: tuple[str, ...]
    kw: float = 0.0
    details: str = ""


@dataclass(frozen=True, slots=True)
class SettlementResult:
    """Output of network.settle_transfers for one tick."""

    actual_sent: dict[str, float]  # house_id -> kW sent out (gross, pre-bus-loss)
    actual_received: dict[str, float]  # house_id -> kW received (net, post-bus-loss)
    events: list[Event]
