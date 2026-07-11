"""LLMAgent unit tests. Built up across Tasks 13-16."""

from __future__ import annotations

from datetime import datetime

import pytest
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
        inbox=inbox,
        t_idx=0,
    )
    # Only REQUEST should be queued for react
    assert len(a.pending_react) == 1
    assert a.pending_react[0][1].performative == "REQUEST"


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
    # Phase 3: peer knowledge arrives ONLY via INFORM messages. A third
    # "have" peer raises the believed mean so both connected peers (r0c1,
    # r1c0) fall below it and receive OFFERs.
    a.observe(
        t=t0,
        own_state=_own_state(8.0),
        inbox=[
            _inform("r0c1", 2.0, 10.0, t0, "b1"),  # geo neighbor, below mean
            _inform("r1c0", 3.0, 10.0, t0, "b2"),  # owner neighbor, below mean
            _inform("r2c2", 8.0, 10.0, t0, "b3"),  # heard from, but not a neighbor
        ],
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
    # Asymmetric believed peers: r0c1 well below mean (have-not), r1c0 well
    # above (another have). Beliefs from INFORMs only. Only r0c1 gets an OFFER.
    a.observe(
        t=t0,
        own_state=_own_state(8.0),
        inbox=[
            _inform("r0c1", 1.0, 10.0, t0, "c1"),
            _inform("r1c0", 9.0, 10.0, t0, "c2"),
        ],
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
    a.observe(t=t0, own_state=_own_state(3.0), inbox=[], t_idx=0)
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
    a.observe(t=t0, own_state=_own_state(8.0), inbox=[], t_idx=0)
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
    a.observe(t=t0, own_state=own, inbox=[], t_idx=0)
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
    # Set up well-above-then-well-below relative to share_min_soc_frac.
    # The default policy uses share_min_soc_frac=0.30 (Phase 2.7) so the
    # hysteresis band is [0.20, 0.40]. Use 0.80 → 0.05 to be safely on
    # opposite sides regardless of the exact threshold.
    a._prev_soc_frac = 0.80
    a.last_soc_frac = 0.05
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


# --- LLMAgent.plan via tool-use (Phase 2.6) ---


def test_plan_consumes_tool_input_when_present(tmp_path) -> None:
    """When the LLM client returns tool_input (structured output), plan() uses it
    directly and bypasses the free-text YAML parser. Parse failures stay zero."""
    from sim.agents.llm import LLMRequest, LLMResponse

    structured = {
        "reflection": "owner group reciprocated; havenot peers visibly low",
        "sharing_intent": "generous",
        "share_min_soc_frac": 0.3,
        "max_share_kw_per_tick": 1.5,
        "recipient_priority": [
            {"circle": "owner", "weight": 1.0},
            {"circle": "geographic", "weight": 0.5},
        ],
        "distrusted_peers": ["r2c3"],
        "request_urgency": "normal",
        "belief_note": "haves should help havenots",
        "ttl_ticks": 4,
    }

    class _ToolReturning(MockLLMClient):
        def call(self, req: LLMRequest) -> LLMResponse:  # type: ignore[override]
            return LLMResponse(text="", tokens_in=10, tokens_out=20, tool_input=structured)

    a = _bare_agent(tmp_path)
    a.llm_client = _ToolReturning(cache=PromptCache(local_dir=tmp_path), canned={})
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(
        t=t0,
        own_state={
            "soc_kwh": 8.0,
            "soc_capacity": 10.0,
            "grid_islanded": True,
            "load_kw": 1.0,
            "solar_kw": 0.0,
        },
        inbox=[],
        t_idx=0,
    )
    a.plan(t=t0)
    assert a.policy.sharing_intent == "generous"
    assert a.policy.share_min_soc_frac == 0.3
    assert "r2c3" in a.policy.distrusted_peers
    assert a.policy.belief_note == "haves should help havenots"
    assert a.n_plan_parse_failures == 0
    # Reflection text becomes a memory
    assert any(
        e.kind == "reflection" and "owner group reciprocated" in e.nl for e in a.memory.entries
    )


def test_react_queue_survives_across_ticks_and_gets_answered(tmp_path) -> None:
    """A deferred REQUEST must be answered on the NEXT tick, not silently
    destroyed — pre-2026-07-07 observe() replaced the queue every tick, so
    19.5% of inbound REQUEST/OFFERs in the reference run vanished unanswered."""
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={
            "You are reacting to a REQUEST": LLMResponse(
                text="ACCEPT\nrationale: surplus available", tokens_in=50, tokens_out=10
            )
        },
    )
    a = _bare_agent(tmp_path)
    a.llm_client = mock
    a.react_max_per_tick = 1
    t0 = datetime(2026, 1, 1, 8, 0)
    own = {
        "soc_kwh": 8.0,
        "soc_capacity": 10.0,
        "grid_islanded": True,
        "load_kw": 1.0,
        "solar_kw": 0.0,
    }
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
        for i in range(2)
    ]
    a.observe(t=t0, own_state=own, inbox=inbox, t_idx=0)
    first = a.react_to_pending(t=t0)
    assert len(first) == 1 and first[0].correlation_id == "id0"
    # Next tick, empty inbox: the deferred id1 must still be there and get answered.
    t1 = datetime(2026, 1, 1, 8, 15)
    a.observe(t=t1, own_state=own, inbox=[], t_idx=1)
    second = a.react_to_pending(t=t1)
    assert len(second) == 1 and second[0].correlation_id == "id1"
    assert a.n_react_dropped_stale == 0


def test_react_queue_ages_out_stale_entries_with_counter(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    a.react_max_per_tick = 0  # never answer anything
    t0 = datetime(2026, 1, 1, 8, 0)
    own = {
        "soc_kwh": 8.0,
        "soc_capacity": 10.0,
        "grid_islanded": True,
        "load_kw": 1.0,
        "solar_kw": 0.0,
    }
    inbox = [
        Message(
            t_sent=t0,
            sender="r0c1",
            recipient="r0c0",
            performative="REQUEST",
            payload={"kwh": 0.5},
            rationale_nl="x",
            correlation_id="stale",
        )
    ]
    a.observe(t=t0, own_state=own, inbox=inbox, t_idx=0)
    a.observe(t=t0, own_state=own, inbox=[], t_idx=1)
    assert len(a.pending_react) == 1  # age 1 < react_stale_after_ticks
    a.observe(t=t0, own_state=own, inbox=[], t_idx=2)
    assert a.pending_react == []
    assert a.n_react_dropped_stale == 1


def test_malformed_tool_input_counts_parse_failure_and_keeps_policy(tmp_path) -> None:
    """The tool-use branch the LIVE runs take (agent.py plan(): tool_input is
    preferred) had zero failure-path coverage pre-2026-07-07 — yet the paper's
    policy_parse_failures statistic flows through exactly this branch."""
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={
            "You are household": LLMResponse(
                text="", tokens_in=10, tokens_out=5, tool_input={"bogus": True}
            )
        },
    )
    a = _bare_agent(tmp_path)
    a.llm_client = mock
    before = a.policy
    t0 = datetime(2026, 1, 1, 8, 0)
    a.plan(t=t0)
    assert a.n_plan_parse_failures == 1
    assert a.policy is before  # keeps previous policy on a single failure


def test_three_malformed_tool_inputs_trigger_round_robin_fallback(tmp_path) -> None:
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={
            "You are household": LLMResponse(
                text="", tokens_in=10, tokens_out=5, tool_input={"bogus": True}
            )
        },
    )
    a = _bare_agent(tmp_path)
    a.llm_client = mock
    t0 = datetime(2026, 1, 1, 8, 0)
    a.plan(t=t0)
    a.plan(t=t0)
    a.plan(t=t0)
    assert a.policy.belief_note == "(fallback to geographic round-robin)"
    assert a.n_plan_fallbacks == 1


# --- Phase 3 Task 2: PeerBelief store + INFORM emission ---


def _own(soc: float = 5.0) -> dict:
    return {
        "soc_kwh": soc,
        "soc_capacity": 10.0,
        "grid_islanded": True,
        "load_kw": 1.0,
        "solar_kw": 0.0,
        "dod_floor_frac": 0.1,
    }


def _inform(sender: str, soc: float, cap: float, t: datetime, cid: str) -> Message:
    return Message(
        t_sent=t,
        sender=sender,
        recipient="r0c0",
        performative="INFORM",
        payload={"soc_kwh": soc, "soc_capacity": cap},
        rationale_nl="status report",
        correlation_id=cid,
    )


def test_observe_updates_peer_beliefs_from_inform(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(
        t=t0,
        own_state=_own(),
        inbox=[_inform("r0c1", 3.2, 10.0, t0, "i1")],
        t_idx=4,
    )
    b = a.peer_beliefs["r0c1"]
    assert b.soc_kwh == 3.2 and b.soc_capacity == 10.0 and b.t_idx_reported == 4
    # A newer INFORM overwrites.
    a.observe(
        t=t0,
        own_state=_own(),
        inbox=[_inform("r0c1", 2.0, 10.0, t0, "i2")],
        t_idx=5,
    )
    assert a.peer_beliefs["r0c1"].soc_kwh == 2.0
    assert a.peer_beliefs["r0c1"].t_idx_reported == 5


def test_emit_informs_carry_the_noised_self_view(tmp_path) -> None:
    """INFORM payloads must carry what the agent BELIEVES (noised observe()
    output), not engine truth — that is how observation noise propagates to
    peers under the Phase 3 information-flow design."""
    from sim.agents.failure_modes import ObsNoiseConfig

    noisy_cfg = FailureModeConfig(obs_noise=ObsNoiseConfig(soc_std_frac=0.3))
    a = _bare_agent(tmp_path)
    a.noise = NoiseSource(cfg=noisy_cfg.obs_noise, scenario_seed=42)
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(t=t0, own_state=_own(soc=5.0), inbox=[], t_idx=0)
    visible = a.last_visible_own["soc_kwh"]
    assert visible != 5.0  # noise actually applied at this std

    from sim.network import build_grid_neighborhood

    nb = build_grid_neighborhood(rows=1, cols=3, bus_max_kw=50.0)
    informs = a.emit_informs(t=t0, neighborhood=nb)
    assert len(informs) == len(nb.union_neighbors("r0c0"))
    for m in informs:
        assert m.performative == "INFORM"
        assert m.payload["soc_kwh"] == visible
        assert m.payload["soc_capacity"] == 10.0


def test_emit_informs_empty_before_first_observe(tmp_path) -> None:
    from sim.network import build_grid_neighborhood

    a = _bare_agent(tmp_path)
    nb = build_grid_neighborhood(rows=1, cols=3, bus_max_kw=50.0)
    assert a.emit_informs(t=datetime(2026, 1, 1, 8, 0), neighborhood=nb) == []


def test_act_decides_on_noised_view_not_raw_state(tmp_path) -> None:
    """Phase 3 T4: the share-vs-request branch must follow the agent's noised
    self-view from observe(), not the raw engine state the facade passes."""
    from sim.agents.failure_modes import ObsNoiseConfig
    from sim.network import build_grid_neighborhood

    a = _bare_agent(tmp_path)
    a.noise = NoiseSource(cfg=ObsNoiseConfig(soc_std_frac=0.4), scenario_seed=7)
    nb = build_grid_neighborhood(rows=1, cols=3, bus_max_kw=50.0)
    t0 = datetime(2026, 1, 1, 8, 0)
    true_soc = 5.0
    # Two beliefs so the below-mean filter can pass someone: r0c1 (needy
    # neighbor) sits below the mean lifted by r0c2 (rich non-neighbor).
    a.observe(
        t=t0,
        own_state=_own(soc=true_soc),
        inbox=[
            _inform("r0c1", 1.0, 10.0, t0, "n1"),
            _inform("r0c2", 9.0, 10.0, t0, "n2"),
        ],
        t_idx=0,
    )
    visible = a.last_visible_own["soc_kwh"]
    assert visible != true_soc
    # Pick a threshold strictly between the true and visible SoC fractions:
    # the branch act() takes reveals which value it consulted.
    import dataclasses

    lo, hi = sorted((true_soc / 10.0, visible / 10.0))
    a.policy = dataclasses.replace(
        a.policy, share_min_soc_frac=(lo + hi) / 2, sharing_intent="generous"
    )
    transfers, outbox = a.act(t=t0, own_state=_own(soc=true_soc), neighborhood=nb, dt_hours=0.25)
    if visible > true_soc:
        # Visible above threshold -> shares (raw would have requested).
        assert transfers or any(m.performative == "OFFER" for m in outbox)
    else:
        # Visible below threshold -> requests (raw would have shared).
        assert not transfers
        assert all(m.performative == "REQUEST" for m in outbox)


# --- Phase 3 Task 5: binding negotiation ---


def _ctx() -> dict:
    return {
        "battery_kwh": 10.0,
        "battery_max_rate_kw": 2.0,
        "rt_efficiency": 1.0,
        "dod_floor_frac": 0.1,
        "outage_start_iso": "",
        "outage_end_iso": "",
        "n_houses_neighborhood": 3,
    }


def test_request_kwh_sized_by_estimated_deficit(tmp_path) -> None:
    """REQUEST asks for the actual next-tick shortfall, not a hardcoded 0.5:
    need = (load - solar)*dt - deliverable_from_battery, from the noised view."""
    from sim.network import build_grid_neighborhood

    a = _bare_agent(tmp_path)
    a.household_context = _ctx()
    nb = build_grid_neighborhood(rows=1, cols=3, bus_max_kw=50.0)
    t0 = datetime(2026, 1, 1, 8, 0)
    # soc 1.2, floor 1.0 -> avail 0.2 kWh; rate 2 kW * 0.25 h = 0.5 kWh cap
    # deliverable = min(0.5, 0.2) * 1.0 = 0.2 kWh. load 4 kW, solar 0:
    # need = 4*0.25 - 0.2 = 0.8 kWh.
    own = {
        "soc_kwh": 1.2,
        "soc_capacity": 10.0,
        "grid_islanded": True,
        "load_kw": 4.0,
        "solar_kw": 0.0,
        "dod_floor_frac": 0.1,
    }
    a.observe(
        t=t0,
        own_state=own,
        inbox=[
            _inform("r0c1", 9.0, 10.0, t0, "q1"),
        ],
        t_idx=0,
    )
    _, outbox = a.act(t=t0, own_state=own, neighborhood=nb, dt_hours=0.25)
    reqs = [m for m in outbox if m.performative == "REQUEST"]
    assert reqs, "below-threshold agent with deficit must request"
    for m in reqs:
        assert m.payload["kwh"] == pytest.approx(0.8, abs=1e-9)
        assert m.payload["deficit_estimate"] == pytest.approx(0.8, abs=1e-9)


def test_no_request_when_battery_covers_the_load(tmp_path) -> None:
    from sim.network import build_grid_neighborhood

    a = _bare_agent(tmp_path)
    a.household_context = _ctx()
    nb = build_grid_neighborhood(rows=1, cols=3, bus_max_kw=50.0)
    t0 = datetime(2026, 1, 1, 8, 0)
    # soc 2.0, floor 1.0 -> avail 1.0; deliverable = min(0.5, 1.0) = 0.5 kWh;
    # load 1 kW * 0.25 = 0.25 kWh < 0.5 -> no deficit -> no REQUEST spam.
    own = {
        "soc_kwh": 2.0,
        "soc_capacity": 10.0,
        "grid_islanded": True,
        "load_kw": 1.0,
        "solar_kw": 0.0,
        "dod_floor_frac": 0.1,
    }
    a.observe(
        t=t0,
        own_state=own,
        inbox=[
            _inform("r0c1", 9.0, 10.0, t0, "q2"),
        ],
        t_idx=0,
    )
    _, outbox = a.act(t=t0, own_state=own, neighborhood=nb, dt_hours=0.25)
    assert [m for m in outbox if m.performative == "REQUEST"] == []


def _request(sender: str, kwh: float, t: datetime, cid: str) -> Message:
    return Message(
        t_sent=t,
        sender=sender,
        recipient="r0c0",
        performative="REQUEST",
        payload={"kwh": kwh, "urgency": "normal"},
        rationale_nl="need energy",
        correlation_id=cid,
    )


def _react_agent(tmp_path, reply_text: str) -> LLMAgent:
    a = _bare_agent(tmp_path)
    a.llm_client = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path / "rc"),
        canned={"You are reacting": LLMResponse(text=reply_text, tokens_in=50, tokens_out=10)},
    )
    return a


def test_accept_with_amount_creates_commitment(tmp_path) -> None:
    a = _react_agent(tmp_path, "ACCEPT 0.4\nrationale: can spare that much")
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(t=t0, own_state=_own(8.0), inbox=[_request("r0c1", 0.9, t0, "r1")], t_idx=0)
    out = a.react_to_pending(t=t0)
    assert out[0].performative == "ACCEPT"
    assert out[0].payload["kwh"] == pytest.approx(0.4)
    assert len(a.commitments) == 1
    c = a.commitments[0]
    assert c.recipient == "r0c1" and c.kwh_remaining == pytest.approx(0.4)
    assert a.n_commitments_made == 1


def test_bare_accept_defaults_to_requested_amount(tmp_path) -> None:
    a = _react_agent(tmp_path, "ACCEPT\nrationale: ok")
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(t=t0, own_state=_own(8.0), inbox=[_request("r0c1", 0.9, t0, "r2")], t_idx=0)
    a.react_to_pending(t=t0)
    assert a.commitments[0].kwh_remaining == pytest.approx(0.9)
    assert a.n_react_amount_defaulted == 1


def test_counter_commits_at_countered_amount(tmp_path) -> None:
    a = _react_agent(tmp_path, "COUNTER 0.2\nrationale: only a little")
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(t=t0, own_state=_own(8.0), inbox=[_request("r0c1", 0.9, t0, "r3")], t_idx=0)
    out = a.react_to_pending(t=t0)
    assert out[0].performative == "COUNTER"
    assert a.commitments[0].kwh_remaining == pytest.approx(0.2)


def test_reject_creates_no_commitment(tmp_path) -> None:
    a = _react_agent(tmp_path, "REJECT\nrationale: no headroom")
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(t=t0, own_state=_own(8.0), inbox=[_request("r0c1", 0.9, t0, "r4")], t_idx=0)
    a.react_to_pending(t=t0)
    assert a.commitments == []


def test_commitment_produces_transfer_bypassing_belief_filter(tmp_path) -> None:
    """A promise is a promise: committed energy flows next act() even though
    the recipient's believed SoC would fail the below-mean filter."""
    from sim.agents.agent import Commitment
    from sim.network import build_grid_neighborhood

    a = _bare_agent(tmp_path)
    nb = build_grid_neighborhood(rows=1, cols=3, bus_max_kw=50.0)
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(t=t0, own_state=_own(8.0), inbox=[], t_idx=0)
    a.commitments.append(Commitment(recipient="r0c1", kwh_remaining=0.4, expires_t_idx=2))
    transfers, outbox = a.act(t=t0, own_state=_own(8.0), neighborhood=nb, dt_hours=0.25)
    by_target = {tr.to_id: tr.kw for tr in transfers}
    assert by_target.get("r0c1") == pytest.approx(0.4 / 0.25)
    assert a.commitments == []  # fully served
    assert any(m.recipient == "r0c1" and m.performative == "OFFER" for m in outbox)


def test_commitment_expires_after_ttl_with_counter(tmp_path) -> None:
    from sim.agents.agent import Commitment
    from sim.network import build_grid_neighborhood

    a = _bare_agent(tmp_path)
    nb = build_grid_neighborhood(rows=1, cols=3, bus_max_kw=50.0)
    t0 = datetime(2026, 1, 1, 8, 0)
    a.commitments.append(Commitment(recipient="r0c1", kwh_remaining=0.4, expires_t_idx=1))
    a.observe(t=t0, own_state=_own(8.0), inbox=[], t_idx=3)  # past TTL
    a.act(t=t0, own_state=_own(8.0), neighborhood=nb, dt_hours=0.25)
    assert a.commitments == []
    assert a.n_commitments_expired == 1


def test_out_of_range_tool_policy_is_a_parse_failure(tmp_path) -> None:
    """A live policy that violates the tool schema's advisory bounds
    (share_min_soc_frac=30 — percent confusion) takes the parse-failure path:
    the agent keeps its prior policy and increments the failure counter."""
    from sim.agents.llm import LLMRequest

    structured = {
        "reflection": "r",
        "sharing_intent": "balanced",
        "share_min_soc_frac": 30,
        "max_share_kw_per_tick": 4.0,
        "recipient_priority": [{"circle": "geographic", "weight": 1.0}],
    }

    class _ToolReturning(MockLLMClient):
        def call(self, req: LLMRequest) -> LLMResponse:  # type: ignore[override]
            return LLMResponse(text="", tokens_in=10, tokens_out=20, tool_input=structured)

    a = _bare_agent(tmp_path)
    a.llm_client = _ToolReturning(cache=PromptCache(local_dir=tmp_path), canned={})
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(
        t=t0,
        own_state={
            "soc_kwh": 8.0,
            "soc_capacity": 10.0,
            "grid_islanded": True,
            "load_kw": 1.0,
            "solar_kw": 0.0,
        },
        inbox=[],
        t_idx=0,
    )
    before = a.policy
    a.plan(t=t0)
    assert a.policy == before
    assert a.n_plan_parse_failures == 1


def test_beliefs_ingested_in_same_observe_call_and_age_rendered(tmp_path) -> None:
    agent = _bare_agent(tmp_path)
    inform = Message(
        t_sent=datetime(2018, 1, 1),
        sender="r0c1",
        recipient=agent.house_id,
        performative="INFORM",
        payload={"soc_kwh": 2.0, "soc_capacity": 10.0},
        rationale_nl="status",
        correlation_id="c1",
    )
    agent.observe(t=datetime(2018, 1, 1), own_state=_own_state(8.0), inbox=[inform], t_idx=2)
    # Post-ingestion: the INFORM delivered THIS tick is already in the snapshot.
    assert agent.last_peer_states["r0c1"]["age_ticks"] == 0
    agent.observe(t=datetime(2018, 1, 1, 0, 45), own_state=_own_state(8.0), inbox=[], t_idx=5)
    assert agent.last_peer_states["r0c1"]["age_ticks"] == 3
    assert "reported 3 tick(s) ago" in agent._peers_summary()


def test_react_prompt_contains_own_state_and_open_commitments(tmp_path) -> None:
    from dataclasses import dataclass

    from sim.agents.agent import Commitment
    from sim.agents.llm import LLMRequest

    @dataclass
    class _RecordingMock(MockLLMClient):
        last_user: str = ""

        def _call_provider(self, req: LLMRequest) -> LLMResponse:
            self.last_user = req.user
            return super()._call_provider(req)

    agent = _bare_agent(tmp_path)
    agent.llm_client = _RecordingMock(
        cache=PromptCache(local_dir=tmp_path / "cache"),
        canned={
            "reacting to a REQUEST": LLMResponse(
                text="ACCEPT 0.4\nrationale: fine", tokens_in=0, tokens_out=0
            )
        },
    )
    agent.observe(t=datetime(2018, 1, 1), own_state=_own_state(8.0), inbox=[], t_idx=0)
    agent.commitments.append(Commitment(recipient="r9c9", kwh_remaining=1.5, expires_t_idx=2))
    req = Message(
        t_sent=datetime(2018, 1, 1),
        sender="r0c1",
        recipient=agent.house_id,
        performative="REQUEST",
        payload={"kwh": 0.4},
        rationale_nl="need",
        correlation_id="c2",
    )
    agent._react_to_message(datetime(2018, 1, 1), req)
    last_user = agent.llm_client.last_user  # type: ignore[attr-defined]
    assert "Your state (as you see it): SoC 8.00/10 kWh" in last_user
    assert "open commitments): 1.50 kWh" in last_user
    assert "3 serviceable ticks" in last_user


def test_offers_do_not_enter_react_queue_but_requests_do(tmp_path) -> None:
    agent = _bare_agent(tmp_path)
    offer = Message(
        t_sent=datetime(2018, 1, 1),
        sender="r0c1",
        recipient=agent.house_id,
        performative="OFFER",
        payload={"kwh": 0.5},
        rationale_nl="sharing",
        correlation_id="c3",
    )
    req = Message(
        t_sent=datetime(2018, 1, 1),
        sender="r0c2",
        recipient=agent.house_id,
        performative="REQUEST",
        payload={"kwh": 0.4},
        rationale_nl="need",
        correlation_id="c4",
    )
    agent.observe(t=datetime(2018, 1, 1), own_state=_own_state(8.0), inbox=[offer, req], t_idx=0)
    assert [m.performative for _, m in agent.pending_react] == ["REQUEST"]
    # The OFFER still reaches memory (importance 6.0 msg_recv entry).
    assert any(
        e.kind == "msg_recv" and e.content["performative"] == "OFFER" for e in agent.memory.entries
    )


def test_request_need_is_split_across_recipients(tmp_path) -> None:
    from sim.network import build_grid_neighborhood

    agent = _bare_agent(tmp_path)  # house r0c0
    nb = build_grid_neighborhood(rows=2, cols=2, bus_max_kw=50.0)
    agent.household_context = {"battery_max_rate_kw": 0.0, "rt_efficiency": 0.9}
    agent.last_visible_own = {
        "soc_kwh": 0.0,
        "soc_capacity": 2.0,
        "load_kw": 2.0,
        "solar_kw": 0.0,
        "grid_islanded": True,
        "dod_floor_frac": 0.1,
    }
    out = agent._emit_requests(datetime(2018, 1, 1), nb, soc_frac=0.0, dt_hours=0.25)
    # need = (2.0 - 0.0) * 0.25 - 0 = 0.5 kWh, split over 2 peers -> 0.25 each
    assert len(out) == 2
    assert all(m.payload["kwh"] == pytest.approx(0.25) for m in out)
    assert sum(m.payload["kwh"] for m in out) == pytest.approx(0.5)


def test_request_recipients_deduped_across_circles(tmp_path) -> None:
    import dataclasses

    from sim.network import build_overlay_neighborhood

    nb = build_overlay_neighborhood(
        rows=1,
        cols=2,
        affiliations={"owner": {"o1": ("r0c0", "r0c1")}},
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
    )
    agent = _bare_agent(tmp_path)  # r0c0; r0c1 reachable via BOTH geographic and owner
    agent.policy = dataclasses.replace(
        agent.policy,
        recipient_priority=(
            RecipientPriority(circle="owner", weight=2.0),
            RecipientPriority(circle="geographic", weight=1.0),
        ),
    )
    agent.household_context = {"battery_max_rate_kw": 0.0, "rt_efficiency": 0.9}
    agent.last_visible_own = {
        "soc_kwh": 0.0,
        "soc_capacity": 2.0,
        "load_kw": 2.0,
        "solar_kw": 0.0,
        "grid_islanded": True,
        "dod_floor_frac": 0.1,
    }
    out = agent._emit_requests(datetime(2018, 1, 1), nb, soc_frac=0.0, dt_hours=0.25)
    assert len(out) == 1  # ONE ask, not one per circle
    assert out[0].payload["kwh"] == pytest.approx(0.5)  # full need to the single peer
    assert "owner" in out[0].rationale_nl  # highest-weight circle won the dedup
