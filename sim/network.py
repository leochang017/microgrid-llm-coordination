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
    edges_by_type: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    def union_neighbors(self, hid: str) -> list[str]:
        """Sorted union of a house's neighbors across every edge layer.

        Falls back to comm_graph when edges_by_type is empty (e.g. a
        Neighborhood built without overlays).
        """
        layers = self.edges_by_type or {"geographic": self.comm_graph}
        acc: set[str] = set()
        for layer in layers.values():
            acc.update(layer.get(hid, []))
        acc.discard(hid)
        return sorted(acc)


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
    return Neighborhood(
        comm_graph=graph,
        bus_max_kw=bus_max_kw,
        bus_loss_factor=bus_loss_factor,
        edges_by_type={"geographic": graph},
    )


def build_overlay_neighborhood(
    rows: int,
    cols: int,
    affiliations: dict[str, dict[str, tuple[str, ...]]],
    *,
    bus_max_kw: float,
    bus_loss_factor: float = 0.05,
) -> Neighborhood:
    """Geographic 4-neighbor graph plus one clique layer per affiliation group.

    `affiliations` maps affiliation_type -> group_id -> tuple of member house ids.
    Within each group all members are mutually connected; the resulting per-type
    adjacency is stored as its own layer in edges_by_type alongside "geographic".
    """
    geo = build_grid_neighborhood(
        rows, cols, bus_max_kw=bus_max_kw, bus_loss_factor=bus_loss_factor
    )
    all_ids = list(geo.comm_graph)
    edges_by_type: dict[str, dict[str, list[str]]] = {"geographic": geo.comm_graph}
    for atype, groups in affiliations.items():
        layer: dict[str, set[str]] = {hid: set() for hid in all_ids}
        for members in groups.values():
            for a in members:
                for b in members:
                    if a != b:
                        layer[a].add(b)
        edges_by_type[atype] = {hid: sorted(neighbors) for hid, neighbors in layer.items()}
    return Neighborhood(
        comm_graph=geo.comm_graph,
        bus_max_kw=bus_max_kw,
        bus_loss_factor=bus_loss_factor,
        edges_by_type=edges_by_type,
    )


def settle_transfers(
    n: Neighborhood,
    requested: list[Transfer],
    grid_status: dict[str, bool],
    sender_caps_kw: dict[str, float],
    receiver_caps_kw: dict[str, float],
) -> SettlementResult:
    """Resolve requested peer transfers against physical limits, return what really moved.

    Two-stage clipping:
      1. Per sender: if total requested out > sender cap, scale each outgoing
         transfer proportionally and emit a SENDER_DOD_FLOOR event.
      2. Per receiver: if total *received* (post-bus-loss) > receiver cap, scale
         all transfers into that receiver proportionally and emit RECEIVER_FULL.
         The sender's actual_sent is reduced accordingly.

    Task 10 adds two more constraints:
      - No wheeling in partial-island scenarios: if a sender's grid status differs
        from the receiver's, the transfer is rejected (a connected house cannot
        pass grid energy to an islanded neighbor through the bus).
      - Bus saturation: if total gross outgoing exceeds n.bus_max_kw, scale all
        flows proportionally and emit BUS_SATURATED.
    """
    actual_sent: dict[str, float] = dict.fromkeys(n.comm_graph, 0.0)
    actual_received: dict[str, float] = dict.fromkeys(n.comm_graph, 0.0)
    events: list[Event] = []
    loss_factor = 1.0 - n.bus_loss_factor

    # No-wheeling filter: reject any transfer where sender's and receiver's grid
    # status differ. Done before any other math so rejected transfers don't
    # consume sender capacity in the proportional-share step below.
    filtered: list[Transfer] = []
    for t in requested:
        if grid_status.get(t.from_id, False) != grid_status.get(t.to_id, False):
            events.append(
                Event(
                    kind=EventKind.NO_WHEELING_REJECTED,
                    house_ids=(t.from_id, t.to_id),
                    kw=t.kw,
                    details="grid status differs between sender and receiver",
                )
            )
        else:
            filtered.append(t)
    requested = filtered

    # Group by sender so we can clip each sender's outgoing pool proportionally.
    by_sender: dict[str, list[Transfer]] = {}
    for t in requested:
        by_sender.setdefault(t.from_id, []).append(t)

    # Stage 1: sender-cap clipping (gives a per-(sender, receiver) provisional kw).
    sender_alloc: dict[str, dict[str, float]] = {}
    for sender, transfers in by_sender.items():
        total_req = sum(t.kw for t in transfers)
        cap = sender_caps_kw.get(sender, 0.0)
        if total_req <= cap or total_req == 0.0:
            allocations = {t.to_id: t.kw for t in transfers}
        else:
            scale = cap / total_req
            allocations = {t.to_id: t.kw * scale for t in transfers}
            events.append(
                Event(
                    kind=EventKind.SENDER_DOD_FLOOR,
                    house_ids=(sender,),
                    kw=total_req - cap,
                    details=f"requested {total_req:.3f} kW, cap {cap:.3f} kW",
                )
            )
        sender_alloc[sender] = allocations

    # Stage 2: receiver-cap clipping (over post-loss received kW).
    receiver_want_net: dict[str, float] = dict.fromkeys(n.comm_graph, 0.0)
    for allocations in sender_alloc.values():
        for r, kw in allocations.items():
            receiver_want_net[r] += kw * loss_factor

    receiver_scale: dict[str, float] = {}
    for r, want_net in receiver_want_net.items():
        cap = receiver_caps_kw.get(r, 0.0)
        if want_net > cap and want_net > 0.0:
            receiver_scale[r] = cap / want_net
            events.append(
                Event(
                    kind=EventKind.RECEIVER_FULL,
                    house_ids=(r,),
                    kw=want_net - cap,
                    details=f"wanted {want_net:.3f} kW net, cap {cap:.3f} kW",
                )
            )
        else:
            receiver_scale[r] = 1.0

    # Stage 3: apply receiver clipping back to senders and tally provisional flows.
    # We track per-pair flows so the TRANSFER_EXECUTED events can be emitted AFTER
    # bus saturation with the actually-delivered kW (not stale pre-saturation values).
    provisional_pair_kw: list[tuple[str, str, float]] = []
    for sender, allocations in sender_alloc.items():
        for r, kw in allocations.items():
            final_send = kw * receiver_scale[r]
            if final_send <= 0:
                continue
            actual_sent[sender] += final_send
            actual_received[r] += final_send * loss_factor
            provisional_pair_kw.append((sender, r, final_send))

    # Stage 4: bus saturation. If total gross out exceeds bus cap, scale all flows
    # (and per-pair provisional values) proportionally so the TRANSFER_EXECUTED
    # events report the final delivered amount.
    total_gross = sum(actual_sent.values())
    sat_scale = 1.0
    if total_gross > n.bus_max_kw and total_gross > 0:
        sat_scale = n.bus_max_kw / total_gross
        for hid in actual_sent:
            actual_sent[hid] *= sat_scale
        for hid in actual_received:
            actual_received[hid] *= sat_scale
        events.append(
            Event(
                kind=EventKind.BUS_SATURATED,
                house_ids=tuple(sorted(actual_sent)),
                kw=total_gross - n.bus_max_kw,
                details=f"total {total_gross:.3f} kW exceeded bus cap {n.bus_max_kw:.3f} kW",
            )
        )

    # Stage 5: emit TRANSFER_EXECUTED events with post-saturation kW values.
    for sender, r, final_send in provisional_pair_kw:
        delivered = final_send * sat_scale
        if delivered <= 0:
            continue
        events.append(
            Event(
                kind=EventKind.TRANSFER_EXECUTED,
                house_ids=(sender, r),
                kw=delivered,
            )
        )

    return SettlementResult(
        actual_sent=actual_sent,
        actual_received=actual_received,
        events=events,
    )
