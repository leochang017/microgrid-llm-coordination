"""Tests for the neighborhood network."""

from sim.network import build_grid_neighborhood


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
