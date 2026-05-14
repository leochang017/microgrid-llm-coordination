"""Neighborhood: spatial comm graph + shared physical bus + transfer settlement.

Task 7 builds only the network structure. Settlement logic (transfer clipping,
bus saturation, no-wheeling rule) lands in Tasks 8-10.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
