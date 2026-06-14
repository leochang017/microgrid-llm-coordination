"""LLMAgent unit tests. Built up across Tasks 13-16."""

from __future__ import annotations

from datetime import datetime

import yaml

from sim.agents.agent import LLMAgent
from sim.agents.cache import PromptCache
from sim.agents.failure_modes import FailureModeConfig, NoiseSource
from sim.agents.llm import LLMResponse, MockLLMClient
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
    # Asymmetric peers + a third "have" peer the agent sees but doesn't share
    # with directly — raises the mean so both connected peers (r0c1, r1c0)
    # fall below it under the Phase-2.5 filter and receive OFFERs.
    a.observe(
        t=t0,
        own_state=_own_state(8.0),
        peer_states={
            "r0c1": {"soc_kwh": 2.0, "soc_capacity": 10.0},  # geo neighbor, below mean
            "r1c0": {"soc_kwh": 3.0, "soc_capacity": 10.0},  # owner neighbor, below mean
            "r2c2": {"soc_kwh": 8.0, "soc_capacity": 10.0},  # visible but not a neighbor
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
    # Owner-edge target (r1c0) is weighted higher than geographic-edge (r0c1).
    assert by_target["r1c0"] > by_target["r0c1"]
    assert all(m.performative == "OFFER" for m in outbox)
    assert all(m.rationale_nl for m in outbox)


def test_act_filters_recipients_by_below_mean_soc(tmp_path) -> None:
    """Below-mean-SoC filter (Phase 2.5): peers above the visible peers'
    mean SoC fraction are not sent OFFERs. Round-robin's secret sauce."""
    a = _bare_agent(tmp_path)
    a.policy = _generous_policy()
    nb = _three_house_neighborhood()
    t0 = datetime(2026, 1, 1, 8, 0)
    # Asymmetric peers: r0c1 well below mean (have-not), r1c0 well above mean
    # (another have). Only r0c1 should receive an OFFER.
    a.observe(
        t=t0,
        own_state=_own_state(8.0),
        peer_states={
            "r0c1": {"soc_kwh": 1.0, "soc_capacity": 10.0},
            "r1c0": {"soc_kwh": 9.0, "soc_capacity": 10.0},
        },
        inbox=[],
        t_idx=0,
    )
    transfers, _ = a.act(t=t0, own_state=_own_state(8.0), neighborhood=nb, dt_hours=0.25)
    by_target = {tr.to_id: tr.kw for tr in transfers}
    assert "r0c1" in by_target
    assert "r1c0" not in by_target


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


# --- LLMAgent.plan tests (Task 15) ---


def test_plan_calls_llm_and_updates_policy(tmp_path) -> None:
    new_policy_yaml = yaml.safe_dump(
        {
            "sharing_intent": "conservative",
            "share_min_soc_frac": 0.7,
            "max_share_kw_per_tick": 0.5,
            "recipient_priority": [{"circle": "owner", "weight": 1.0}],
            "distrusted_peers": ["r2c3"],
            "request_urgency": "low",
            "belief_note": "owner-group reliable; r2c3 untrustworthy",
            "ttl_ticks": 6,
        }
    )
    mock_text = f"""
Reflection: peer r2c3 refused 4 of 4 requests.

Policy:
```yaml
{new_policy_yaml}
```
"""
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={
            "You are household": LLMResponse(text=mock_text, tokens_in=300, tokens_out=120),
        },
    )
    a = _bare_agent(tmp_path)
    a.llm_client = mock
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(
        t=t0,
        own_state={
            "soc_kwh": 5.0,
            "soc_capacity": 10.0,
            "grid_islanded": True,
            "load_kw": 1.0,
            "solar_kw": 0.0,
        },
        peer_states={},
        inbox=[],
        t_idx=0,
    )
    a.plan(t=t0)
    assert a.policy.sharing_intent == "conservative"
    assert a.policy.share_min_soc_frac == 0.7
    assert "r2c3" in a.policy.distrusted_peers


def test_plan_falls_back_on_unparseable_response(tmp_path) -> None:
    """3 consecutive parse failures → fallback to default round_robin policy."""
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={"You are household": LLMResponse(text="i am a teapot", tokens_in=10, tokens_out=5)},
    )
    a = _bare_agent(tmp_path)
    a.llm_client = mock
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(
        t=t0,
        own_state={
            "soc_kwh": 5.0,
            "soc_capacity": 10.0,
            "grid_islanded": True,
            "load_kw": 1.0,
            "solar_kw": 0.0,
        },
        peer_states={},
        inbox=[],
        t_idx=0,
    )
    a.plan(t=t0)
    a.plan(t=t0)
    a.plan(t=t0)
    assert a.policy.belief_note == "(fallback to geographic round-robin)"


def test_plan_prompt_contains_trust_circles_and_state(tmp_path) -> None:
    captured: dict[str, str] = {}

    class _Capture(MockLLMClient):
        def _call_provider(self, req):  # type: ignore[no-untyped-def]
            captured["user"] = req.user
            captured["system"] = req.system
            return LLMResponse(text="(no policy)", tokens_in=0, tokens_out=0)

    a = _bare_agent(tmp_path)
    a.llm_client = _Capture(
        cache=PromptCache(local_dir=tmp_path),
        canned={"": LLMResponse(text="", tokens_in=0, tokens_out=0)},
    )
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(
        t=t0,
        own_state={
            "soc_kwh": 5.0,
            "soc_capacity": 10.0,
            "grid_islanded": True,
            "load_kw": 1.0,
            "solar_kw": 0.0,
        },
        peer_states={},
        inbox=[],
        t_idx=0,
    )
    a.plan(t=t0)
    assert "owner_acme" in captured["user"]
    assert "household r0c0" in captured["user"]


# --- LLMAgent.react_to_pending + trigger tests (Task 16) ---


def test_react_produces_accept_or_reject_per_message(tmp_path) -> None:
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={
            "You are reacting to a REQUEST": LLMResponse(
                text="ACCEPT\nrationale: I have surplus from owner group",
                tokens_in=120,
                tokens_out=20,
            )
        },
    )
    a = _bare_agent(tmp_path)
    a.llm_client = mock
    t0 = datetime(2026, 1, 1, 8, 0)
    inbox = [
        Message(
            t_sent=t0,
            sender="r0c1",
            recipient="r0c0",
            performative="REQUEST",
            payload={"kwh": 0.5},
            rationale_nl="my SoC is low",
            correlation_id="abc",
        )
    ]
    a.observe(
        t=t0,
        own_state={
            "soc_kwh": 8.0,
            "soc_capacity": 10.0,
            "grid_islanded": True,
            "load_kw": 1.0,
            "solar_kw": 0.0,
        },
        peer_states={},
        inbox=inbox,
        t_idx=0,
    )
    out = a.react_to_pending(t=t0)
    assert len(out) == 1
    assert out[0].performative == "ACCEPT"
    assert out[0].rationale_nl != ""
    assert out[0].correlation_id == "abc"


def test_react_caps_at_max_per_tick(tmp_path) -> None:
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={
            "You are reacting to a REQUEST": LLMResponse(
                text="REJECT\nrationale: not enough headroom",
                tokens_in=100,
                tokens_out=20,
            )
        },
    )
    a = _bare_agent(tmp_path)
    a.llm_client = mock
    a.react_max_per_tick = 2
    t0 = datetime(2026, 1, 1, 8, 0)
    inbox = [
        Message(
            t_sent=t0,
            sender=f"r0c{i}",
            recipient="r0c0",
            performative="REQUEST",
            payload={"kwh": 0.5},
            rationale_nl="x",
            correlation_id=f"id{i}",
        )
        for i in range(5)
    ]
    a.observe(
        t=t0,
        own_state={
            "soc_kwh": 8.0,
            "soc_capacity": 10.0,
            "grid_islanded": True,
            "load_kw": 1.0,
            "solar_kw": 0.0,
        },
        peer_states={},
        inbox=inbox,
        t_idx=0,
    )
    out = a.react_to_pending(t=t0)
    assert len(out) == 2
    assert len(a.pending_react) == 3


def test_trigger_outage_onset(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    t0 = datetime(2026, 1, 1, 8, 0)
    a.last_grid_islanded = False
    assert a.should_replan(grid_islanded=True, t=t0) is True


def test_trigger_soc_hysteresis_crossing(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    t0 = datetime(2026, 1, 1, 8, 0)
    # set up previous-above + current-below
    a._prev_soc_frac = 0.65
    a.last_soc_frac = 0.35
    a.policy_age_ticks = 0
    a.last_grid_islanded = True  # already islanded so onset doesn't fire
    assert a.should_replan(grid_islanded=True, t=t0) is True


def test_trigger_ttl_expiry(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    a.policy_age_ticks = a.policy.ttl_ticks
    assert a.should_replan(grid_islanded=True, t=datetime(2026, 1, 1)) is True


def test_no_replan_when_idle_and_inside_ttl(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    a.policy_age_ticks = 0
    a.last_soc_frac = 0.6
    a._prev_soc_frac = 0.6
    a.last_grid_islanded = True
    assert a.should_replan(grid_islanded=True, t=datetime(2026, 1, 1)) is False
