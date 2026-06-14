"""LLMAgent unit tests. Built up across Tasks 13-16."""

from __future__ import annotations

from datetime import datetime

from sim.agents.agent import LLMAgent
from sim.agents.cache import PromptCache
from sim.agents.failure_modes import FailureModeConfig, NoiseSource
from sim.agents.llm import MockLLMClient
from sim.agents.memory import MemoryStream
from sim.agents.policy import Policy
from sim.agents.protocol import Message


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
