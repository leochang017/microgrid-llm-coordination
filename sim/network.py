"""Neighborhood: spatial comm graph + shared physical bus + transfer settlement.

Task 8 ships the happy path of settle_transfers (no clipping, just bus-loss
accounting). Sender/receiver capacity clipping lands in Task 9; bus saturation
and the no-wheeling rule for partial outages land in Task 10.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sim.types import Event, EventKind, SettlementResult, Transfer


@dataclass(frozen=True, slots=True)
class Neighborhood:
    comm_graph: dict[str, list[str]] = field(default_factory=dict)
    bus_max_kw: float = 50.0
    bus_loss_factor: float = 0.05


def build_grid_neighborhood(
    rows: int, cols: int, *, bus_max_kw: float, bus_loss_factor: float = 0.05
) -> Neighborhood:
    """Build a rows x cols grid neighborhood with 4-neighbor comm graph (N/E/S/W)."""
    graph: dict[str, list[str]] = {}
    for r in range(rows):
        for c in range(cols):
            key = f"r{r}c{c}"
            neighbors: list[str] = []
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    neighbors.append(f"r{nr}c{nc}")
            graph[key] = neighbors
    return Neighborhood(comm_graph=graph, bus_max_kw=bus_max_kw, bus_loss_factor=bus_loss_factor)


def settle_transfers(
    n: Neighborhood,
    requested: list[Transfer],
    grid_status: dict[str, bool],
    sender_caps_kw: dict[str, float],
    receiver_caps_kw: dict[str, float],
) -> SettlementResult:
    """Resolve requested peer transfers against physical limits, return what really moved.

    Task 8 ships only the happy path: each transfer goes through as requested,
    receiver gets `kw * (1 - bus_loss_factor)`, an event is emitted. Sender/
    receiver caps are accepted as arguments but ignored here — Task 9 wires
    those constraints in. Bus saturation and no-wheeling land in Task 10.
    """
    # The sender_caps and receiver_caps args are unused in Task 8's happy path.
    # They are part of the public signature so Tasks 9-10 don't have to change
    # callers when they wire the constraints in.
    del sender_caps_kw, receiver_caps_kw
    del grid_status

    actual_sent: dict[str, float] = dict.fromkeys(n.comm_graph, 0.0)
    actual_received: dict[str, float] = dict.fromkeys(n.comm_graph, 0.0)
    events: list[Event] = []
    loss_factor = 1.0 - n.bus_loss_factor

    for t in requested:
        actual_sent[t.from_id] += t.kw
        actual_received[t.to_id] += t.kw * loss_factor
        events.append(
            Event(
                kind=EventKind.TRANSFER_EXECUTED,
                house_ids=(t.from_id, t.to_id),
                kw=t.kw,
                details="happy path",
            )
        )

    return SettlementResult(
        actual_sent=actual_sent,
        actual_received=actual_received,
        events=events,
    )
