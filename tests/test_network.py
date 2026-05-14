"""Tests for the neighborhood network."""

import pytest

from sim.network import build_grid_neighborhood, settle_transfers
from sim.types import EventKind, Transfer


def test_grid_neighborhood_5x6_has_30_houses() -> None:
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    assert len(n.comm_graph) == 30


def test_corner_house_has_2_neighbors() -> None:
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    # House (0,0) is a corner; neighbors are (0,1) and (1,0)
    assert sorted(n.comm_graph["r0c0"]) == ["r0c1", "r1c0"]


def test_edge_house_has_3_neighbors() -> None:
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    # House (0,1) is on the top edge; neighbors: (0,0), (0,2), (1,1)
    assert sorted(n.comm_graph["r0c1"]) == ["r0c0", "r0c2", "r1c1"]


def test_interior_house_has_4_neighbors() -> None:
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    # House (1,1) is interior; neighbors: (0,1), (1,0), (1,2), (2,1)
    assert sorted(n.comm_graph["r1c1"]) == ["r0c1", "r1c0", "r1c2", "r2c1"]


def test_bus_capacity_stored() -> None:
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0, bus_loss_factor=0.05)
    assert n.bus_max_kw == 50.0
    assert n.bus_loss_factor == 0.05


def test_single_transfer_no_clipping() -> None:
    """One 2 kW transfer through 50 kW bus with 5% loss -> sender sends 2, receiver gets 1.9."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0, bus_loss_factor=0.05)
    transfers = [Transfer(from_id="r0c0", to_id="r0c1", kw=2.0)]
    grid_status = {f"r{r}c{c}": False for r in range(5) for c in range(6)}
    sender_caps = {hid: 10.0 for hid in grid_status}
    receiver_caps = {hid: 10.0 for hid in grid_status}

    result = settle_transfers(n, transfers, grid_status, sender_caps, receiver_caps)

    assert result.actual_sent["r0c0"] == pytest.approx(2.0, abs=1e-9)
    assert result.actual_received["r0c1"] == pytest.approx(2.0 * 0.95, abs=1e-9)
    assert any(e.kind == EventKind.TRANSFER_EXECUTED for e in result.events)
