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


def test_sender_cap_clips_transfer() -> None:
    """Sender wants to send 5 kW but can only spare 3 -> sent=3, event emitted."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    transfers = [Transfer(from_id="r0c0", to_id="r0c1", kw=5.0)]
    grid_status = {f"r{r}c{c}": False for r in range(5) for c in range(6)}
    sender_caps = {hid: 10.0 for hid in grid_status}
    sender_caps["r0c0"] = 3.0
    receiver_caps = {hid: 10.0 for hid in grid_status}

    result = settle_transfers(n, transfers, grid_status, sender_caps, receiver_caps)
    assert result.actual_sent["r0c0"] == pytest.approx(3.0, abs=1e-9)
    assert result.actual_received["r0c1"] == pytest.approx(3.0 * 0.95, abs=1e-9)
    assert any(e.kind == EventKind.SENDER_DOD_FLOOR for e in result.events)


def test_receiver_cap_clips_transfer() -> None:
    """Receiver can only absorb 1 kW post-loss -> sender send is 1/0.95 kW."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    transfers = [Transfer(from_id="r0c0", to_id="r0c1", kw=5.0)]
    grid_status = {f"r{r}c{c}": False for r in range(5) for c in range(6)}
    sender_caps = {hid: 10.0 for hid in grid_status}
    receiver_caps = {hid: 10.0 for hid in grid_status}
    receiver_caps["r0c1"] = 1.0

    result = settle_transfers(n, transfers, grid_status, sender_caps, receiver_caps)
    assert result.actual_received["r0c1"] == pytest.approx(1.0, abs=1e-9)
    assert result.actual_sent["r0c0"] == pytest.approx(1.0 / 0.95, abs=1e-6)
    assert any(e.kind == EventKind.RECEIVER_FULL for e in result.events)


def test_multiple_transfers_share_sender_cap_proportionally() -> None:
    """Sender has 3 kW cap, requests 4 + 2 to two neighbors -> 2 + 1 (proportional)."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    transfers = [
        Transfer(from_id="r0c0", to_id="r0c1", kw=4.0),
        Transfer(from_id="r0c0", to_id="r1c0", kw=2.0),
    ]
    grid_status = {f"r{r}c{c}": False for r in range(5) for c in range(6)}
    sender_caps = {hid: 10.0 for hid in grid_status}
    sender_caps["r0c0"] = 3.0
    receiver_caps = {hid: 10.0 for hid in grid_status}

    result = settle_transfers(n, transfers, grid_status, sender_caps, receiver_caps)
    assert result.actual_sent["r0c0"] == pytest.approx(3.0, abs=1e-9)
    # Proportional share: r0c1 gets 4/6 * 3 = 2.0; r1c0 gets 2/6 * 3 = 1.0 (pre-loss kW)
    assert result.actual_received["r0c1"] == pytest.approx(2.0 * 0.95, abs=1e-6)
    assert result.actual_received["r1c0"] == pytest.approx(1.0 * 0.95, abs=1e-6)


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


def test_bus_saturation_clips_proportionally() -> None:
    """Two transfers of 30 kW each through a 50 kW bus -> clipped to 25 kW each."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0, bus_loss_factor=0.0)
    transfers = [
        Transfer(from_id="r0c0", to_id="r0c1", kw=30.0),
        Transfer(from_id="r1c0", to_id="r1c1", kw=30.0),
    ]
    grid_status = {f"r{r}c{c}": False for r in range(5) for c in range(6)}
    caps = {hid: 100.0 for hid in grid_status}
    result = settle_transfers(n, transfers, grid_status, caps, caps)
    assert result.actual_sent["r0c0"] == pytest.approx(25.0, abs=1e-6)
    assert result.actual_sent["r1c0"] == pytest.approx(25.0, abs=1e-6)
    assert any(e.kind == EventKind.BUS_SATURATED for e in result.events)
    # TRANSFER_EXECUTED events must report the POST-saturation delivered kW,
    # not the pre-saturation requested kW (review fix I5).
    transfer_events = [e for e in result.events if e.kind == EventKind.TRANSFER_EXECUTED]
    assert len(transfer_events) == 2
    for e in transfer_events:
        assert e.kw == pytest.approx(25.0, abs=1e-6)


def test_no_wheeling_in_partial_island() -> None:
    """Sender grid-connected, receiver islanded -> transfer blocked, event emitted."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    transfers = [Transfer(from_id="r0c0", to_id="r0c1", kw=2.0)]
    grid_status = {f"r{r}c{c}": False for r in range(5) for c in range(6)}
    grid_status["r0c0"] = True  # sender connected
    grid_status["r0c1"] = False  # receiver islanded
    caps = {hid: 100.0 for hid in grid_status}
    result = settle_transfers(n, transfers, grid_status, caps, caps)
    assert result.actual_sent["r0c0"] == 0.0
    assert result.actual_received["r0c1"] == 0.0
    assert any(e.kind == EventKind.NO_WHEELING_REJECTED for e in result.events)


def test_all_islanded_allows_transfer() -> None:
    """All houses islanded -> transfers work normally."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0, bus_loss_factor=0.05)
    transfers = [Transfer(from_id="r0c0", to_id="r0c1", kw=2.0)]
    grid_status = {f"r{r}c{c}": False for r in range(5) for c in range(6)}
    caps = {hid: 100.0 for hid in grid_status}
    result = settle_transfers(n, transfers, grid_status, caps, caps)
    assert result.actual_sent["r0c0"] == pytest.approx(2.0, abs=1e-9)


def test_all_connected_allows_transfer() -> None:
    """All houses grid-connected -> transfers work normally (the outage-free default)."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0, bus_loss_factor=0.05)
    transfers = [Transfer(from_id="r0c0", to_id="r0c1", kw=2.0)]
    grid_status = {f"r{r}c{c}": True for r in range(5) for c in range(6)}
    caps = {hid: 100.0 for hid in grid_status}
    result = settle_transfers(n, transfers, grid_status, caps, caps)
    assert result.actual_sent["r0c0"] == pytest.approx(2.0, abs=1e-9)


def test_build_grid_populates_geographic_layer() -> None:
    from sim.network import build_grid_neighborhood

    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    assert "geographic" in n.edges_by_type
    assert sorted(n.edges_by_type["geographic"]["r0c0"]) == ["r0c1", "r1c0"]


def test_union_neighbors_unions_layers_and_excludes_self() -> None:
    from sim.network import Neighborhood

    n = Neighborhood(
        comm_graph={"a": ["b"], "b": ["a"], "c": []},
        edges_by_type={
            "geographic": {"a": ["b"], "b": ["a"], "c": []},
            "owner": {"a": ["c"], "b": [], "c": ["a"]},
        },
        bus_max_kw=50.0,
    )
    assert n.union_neighbors("a") == ["b", "c"]
    assert n.union_neighbors("c") == ["a"]


def test_union_neighbors_falls_back_to_geographic_only() -> None:
    from sim.network import build_grid_neighborhood

    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    assert n.union_neighbors("r0c0") == ["r0c1", "r1c0"]


def test_overlay_builds_affiliation_cliques() -> None:
    from sim.network import build_overlay_neighborhood

    affiliations = {
        "owner": {"owner_acme": ("r0c0", "r0c1", "r4c5")},
        "hoa": {"hoa_north": ("r0c0", "r0c1")},
    }
    n = build_overlay_neighborhood(rows=5, cols=6, affiliations=affiliations, bus_max_kw=50.0)
    assert sorted(n.edges_by_type["owner"]["r0c0"]) == ["r0c1", "r4c5"]
    assert sorted(n.edges_by_type["owner"]["r4c5"]) == ["r0c0", "r0c1"]
    assert sorted(n.edges_by_type["geographic"]["r0c0"]) == ["r0c1", "r1c0"]
    assert n.union_neighbors("r0c0") == ["r0c1", "r1c0", "r4c5"]


def test_overlay_no_affiliations_equals_geographic() -> None:
    from sim.network import build_overlay_neighborhood

    n = build_overlay_neighborhood(rows=2, cols=2, affiliations={}, bus_max_kw=50.0)
    assert set(n.edges_by_type) == {"geographic"}
    assert n.union_neighbors("r0c0") == ["r0c1", "r1c0"]


def test_default_affiliations_deterministic_and_typed() -> None:
    from sim.network import default_affiliations

    a1 = default_affiliations(rows=5, cols=6, seed=17)
    a2 = default_affiliations(rows=5, cols=6, seed=17)
    assert a1 == a2
    assert {"owner", "hoa", "dr_aggregator"} <= set(a1)
    valid = {f"r{r}c{c}" for r in range(5) for c in range(6)}
    for groups in a1.values():
        for members in groups.values():
            assert set(members) <= valid


def test_default_affiliations_different_seed_differs() -> None:
    from sim.network import default_affiliations

    assert default_affiliations(5, 6, seed=1) != default_affiliations(5, 6, seed=2)
