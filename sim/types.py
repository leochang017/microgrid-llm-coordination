"""Shared dataclass types used across the simulator."""
from __future__ import annotations

from dataclasses import dataclass, field


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
