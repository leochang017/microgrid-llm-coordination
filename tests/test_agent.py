"""LLMAgent unit tests. Built up across Tasks 13-16."""

from __future__ import annotations

from datetime import datetime

from sim.agents.agent import LLMAgent
from sim.agents.cache import PromptCache
from sim.agents.failure_modes import FailureModeConfig, NoiseSource
from sim.agents.llm import MockLLMClient
from sim.agents.memory import MemoryStream
from sim.agents.policy import Policy, RecipientPriority
from sim.agents.protocol import Message
from sim.network import Neighborhood


def _bare_agent(tmp_path) -> LLMAgent:
    return LLMAgent(
        house_id="r0c0",
        scenario_seed=42,
        trust_circles={"owner": "owner_acme", "geographic": "_grid_"},
        policy=Policy.default_round_robin_fallback(),
        memory=MemoryStream(),
        llm_client=MockLLMClient(cache=PromptCache(local_dir=tmp_path), canned={}),
        model="claude-haiku-4-5-20251001",
        noise=NoiseSource(cfg=FailureModeConfig().obs_noise, scenario_seed=42),
    )


def test_agent_rng_is_deterministic(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    b = _bare_agent(tmp_path)
    seq_a = [a.rng.random() for _ in range(5)]
    seq_b = [b.rng.random() for _ in range(5)]
    assert seq_a == seq_b


def test_agent_observe_appends_to_memory(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(
        t=t0,
        own_state={
            "soc_kwh": 6.0,
            "soc_capacity": 10.0,
            "grid_islanded": True,
            "load_kw": 1.0,
            "solar_kw": 0.0,
        },
        peer_states={"r0c1": {"soc_kwh": 4.0, "soc_capacity": 10.0}},
        inbox=[],
        t_idx=0,
    )
    assert any(e.kind == "obs" for e in a.memory.entries)
    obs = next(e for e in a.memory.entries if e.kind == "obs")
    assert obs.content["own_soc_kwh"] == 6.0


def test_agent_observe_appends_inbox_as_msg_recv(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    t0 = datetime(2026, 1, 1, 8, 0)
    inbox = [
        Message(
            t_sent=t0,
            sender="r0c1",
            recipient="r0c0",
            performative="REQUEST",
            payload={"kwh": 0.3},
            rationale_nl="my SoC is low",
            correlation_id="abc",
        )
    ]
    a.observe(
        t=t0,
        own_state={
            "soc_kwh": 6.0,
            "soc_capacity": 10.0,
            "grid_islanded": True,
            "load_kw": 1.0,
            "solar_kw": 0.0,
        },
        peer_states={},
        inbox=inbox,
        t_idx=0,
    )
    assert any(e.kind == "msg_recv" for e in a.memory.entries)


def test_agent_pending_react_queued(tmp_path) -> None:
    """REQUEST and OFFER messages are queued for react_to_pending; others are not."""
    a = _bare_agent(tmp_path)
    t0 = datetime(2026, 1, 1, 8, 0)
    inbox = [
        Message(
            t_sent=t0,
            sender="r0c1",
            recipient="r0c0",
            performative="REQUEST",
            payload={"kwh": 0.3},
            rationale_nl="x",
            correlation_id="a",
        ),
        Message(
            t_sent=t0,
            sender="r0c1",
            recipient="r0c0",
            performative="INFORM",
            payload={"soc_kwh": 5.0},
            rationale_nl="y",
            correlation_id="b",
        ),
    ]
    a.observe(
        t=t0,
        own_state={
            "soc_kwh": 6.0,
            "soc_capacity": 10.0,
            "grid_islanded": True,
            "load_kw": 1.0,
            "solar_kw": 0.0,
        },
        peer_states={},
        inbox=inbox,
        t_idx=0,
    )
    # Only REQUEST should be queued for react
    assert len(a.pending_react) == 1
    assert a.pending_react[0].performative == "REQUEST"


# --- LLMAgent.act tests (Task 14) ---


def _three_house_neighborhood() -> Neighborhood:
    return Neighborhood(
        comm_graph={"r0c0": ["r0c1"], "r0c1": ["r0c0"], "r1c0": []},
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
        edges_by_type={
            "geographic": {"r0c0": ["r0c1"], "r0c1": ["r0c0"], "r1c0": []},
            "owner": {"r0c0": ["r1c0"], "r0c1": [], "r1c0": ["r0c0"]},
        },
    )


def _generous_policy() -> Policy:
    return Policy(
        sharing_intent="generous",
        share_min_soc_frac=0.50,
        max_share_kw_per_tick=2.0,
        recipient_priority=(
            RecipientPriority(circle="owner", weight=1.0),
            RecipientPriority(circle="geographic", weight=0.5),
        ),
        distrusted_peers=(),
        request_urgency="normal",
        belief_note="",
        ttl_ticks=4,
    )


def _own_state(soc_kwh: float, capacity: float = 10.0, islanded: bool = True) -> dict:
    return {
        "soc_kwh": soc_kwh,
        "soc_capacity": capacity,
        "grid_islanded": islanded,
        "load_kw": 1.0,
        "solar_kw": 0.0,
        "dod_floor_frac": 0.1,
    }


def test_act_emits_offers_to_neighbors_when_soc_above_threshold(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    a.policy = _generous_policy()
    nb = _three_house_neighborhood()
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(
        t=t0,
        own_state=_own_state(8.0),
        peer_states={
            "r0c1": {"soc_kwh": 2.0, "soc_capacity": 10.0},
            "r1c0": {"soc_kwh": 2.5, "soc_capacity": 10.0},
        },
        inbox=[],
        t_idx=0,
    )
    transfers, outbox = a.act(
        t=t0,
        own_state=_own_state(8.0),
        neighborhood=nb,
        dt_hours=0.25,
    )
    assert len(transfers) >= 1
    by_target = {tr.to_id: tr.kw for tr in transfers}
    assert "r1c0" in by_target and "r0c1" in by_target
    assert by_target["r1c0"] > by_target["r0c1"]
    assert all(m.performative == "OFFER" for m in outbox)
    assert all(m.rationale_nl for m in outbox)


def test_act_skips_when_soc_below_threshold(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    a.policy = _generous_policy()
    nb = _three_house_neighborhood()
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(t=t0, own_state=_own_state(3.0), peer_states={}, inbox=[], t_idx=0)
    transfers, outbox = a.act(t=t0, own_state=_own_state(3.0), neighborhood=nb, dt_hours=0.25)
    assert transfers == []
    assert all(m.performative == "REQUEST" for m in outbox)


def test_act_excludes_distrusted_peers(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    p = _generous_policy()
    a.policy = Policy(
        sharing_intent=p.sharing_intent,
        share_min_soc_frac=p.share_min_soc_frac,
        max_share_kw_per_tick=p.max_share_kw_per_tick,
        recipient_priority=p.recipient_priority,
        distrusted_peers=("r1c0",),
        request_urgency=p.request_urgency,
        belief_note=p.belief_note,
        ttl_ticks=p.ttl_ticks,
    )
    nb = _three_house_neighborhood()
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(t=t0, own_state=_own_state(8.0), peer_states={}, inbox=[], t_idx=0)
    transfers, _ = a.act(t=t0, own_state=_own_state(8.0), neighborhood=nb, dt_hours=0.25)
    assert all(tr.to_id != "r1c0" for tr in transfers)


def test_act_respects_headroom_cap(tmp_path) -> None:
    """Total outbound kw never exceeds (soc - dod_floor) / dt."""
    a = _bare_agent(tmp_path)
    a.policy = _generous_policy()
    nb = _three_house_neighborhood()
    t0 = datetime(2026, 1, 1, 8, 0)
    own = {
        "soc_kwh": 5.5,
        "soc_capacity": 10.0,
        "grid_islanded": True,
        "load_kw": 0.0,
        "solar_kw": 0.0,
        "dod_floor_frac": 0.5,
    }
    a.observe(t=t0, own_state=own, peer_states={}, inbox=[], t_idx=0)
    transfers, _ = a.act(t=t0, own_state=own, neighborhood=nb, dt_hours=0.25)
    total_kw = sum(tr.kw for tr in transfers)
    headroom_kwh = 5.5 - 0.5 * 10.0
    headroom_kw = headroom_kwh / 0.25
    assert total_kw <= headroom_kw + 1e-9
