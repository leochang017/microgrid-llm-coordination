"""C1/C2 commitment-integrity fixes (2026-07-18): TDD tests for two
commitment-negotiation bugs in the LLM agent layer.

C1 — a commitment is registered the moment an agent formulates an
ACCEPT/COUNTER reply, even if the bus later refuses to deliver that reply
(message-budget overflow, comm drop). The requester never sees the promise,
but the promiser still ships energy against it. Fix (Task 3): retract the
provisional commitment when ``send()`` reports refusal.

C2 — a committed transfer bypasses the below-mean discretionary-sharing
filter (a promise is a promise) but was ALSO bypassing the agent's own
``share_min_soc_frac`` safety floor: an agent that has since fallen below its
own threshold could still export committed energy. Fix (Task 4): hold (don't
serve) below-threshold commitments; they age out on their original TTL or
resume once the agent recovers.

This file opens with a characterization pin (Task 1) that freezes the
current, unmodified mock clean-cell outcome, plus the shared `_agent`/`_own`/
`_request`/`_run_mock` helpers Tasks 3 and 4 build on.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from sim.agents.agent import LLMAgent
from sim.agents.cache import PromptCache
from sim.agents.failure_modes import FailureModeConfig, NoiseSource
from sim.agents.llm import LLMResponse, MockLLMClient
from sim.agents.memory import MemoryStream
from sim.agents.policy import Policy
from sim.agents.protocol import Message

ROOT = Path(__file__).resolve().parent.parent
SCEN_DIR = ROOT / "configs" / "scenarios"


def _bare_agent(tmp_path: Path) -> LLMAgent:
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


def _agent(tmp_path: Path, reply_text: str = "ACCEPT 0.4\nrationale: ok") -> LLMAgent:
    """A bare agent whose ``react_to_pending()`` replies are canned with
    `reply_text`. Default ACCEPTs a positive 0.4 kWh so a default `_request`
    (which asks for 0.9 kWh) produces exactly one commitment."""
    a = _bare_agent(tmp_path)
    a.llm_client = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path / "rc"),
        canned={"You are reacting": LLMResponse(text=reply_text, tokens_in=50, tokens_out=10)},
    )
    return a


def _own(soc: float = 5.0) -> dict:
    return {
        "soc_kwh": soc,
        "soc_capacity": 10.0,
        "grid_islanded": True,
        "load_kw": 1.0,
        "solar_kw": 0.0,
        "dod_floor_frac": 0.1,
    }


def _request(sender: str, cid: str, t: datetime, kwh: float = 0.9) -> Message:
    return Message(
        t_sent=t,
        sender=sender,
        recipient="r0c0",
        performative="REQUEST",
        payload={"kwh": kwh, "urgency": "normal"},
        rationale_nl="need energy",
        correlation_id=cid,
    )


def _canned_mock(tmp_path: Path) -> MockLLMClient:
    policy_yaml = yaml.safe_dump(
        {
            "sharing_intent": "generous",
            "share_min_soc_frac": 0.30,
            "max_share_kw_per_tick": 1.5,
            "recipient_priority": [
                {"circle": "owner", "weight": 1.0},
                {"circle": "geographic", "weight": 0.5},
            ],
            "distrusted_peers": [],
            "request_urgency": "normal",
            "belief_note": "",
            "ttl_ticks": 4,
        }
    )
    return MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={
            "You are household": LLMResponse(
                text=f"r\n\n```yaml\n{policy_yaml}\n```", tokens_in=400, tokens_out=160
            ),
            "You are reacting": LLMResponse(
                text="ACCEPT\nrationale: ok", tokens_in=80, tokens_out=20
            ),
        },
    )


def _run_mock(scenario_file: str, tmp_path: Path, monkeypatch) -> dict:
    from sim.agents.protocol import MessageBus
    from sim.engine import run
    from sim.logging import JsonlLogger
    from sim.network import build_overlay_neighborhood
    from sim.scenario import load_scenario
    from sim.strategies import llm_agent as llm_strat

    s = load_scenario(SCEN_DIR / scenario_file)
    mock = _canned_mock(tmp_path / scenario_file.replace(".yaml", ""))
    monkeypatch.setattr(llm_strat, "_make_llm_client", lambda model, run_dir: mock)
    nb = build_overlay_neighborhood(
        rows=s.rows,
        cols=s.cols,
        affiliations=s.affiliations,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
    )
    bus = MessageBus(neighborhood=nb, seed=s.seed)
    out = tmp_path / scenario_file.replace(".yaml", "")
    out.mkdir()
    run(
        scenario=s,
        decide_transfers=None,
        prepare=llm_strat.prepare,
        logger=JsonlLogger(run_dir=out, scenario_id=s.scenario_id),
        message_bus=bus,
    )
    # Fills in llm_call_counts_detailed from the module-global registry left
    # behind by the prepare() call above (mirrors scripts/run.py).
    llm_strat.update_summary_with_counts(out)
    return json.loads((out / "summary.json").read_text())  # type: ignore[no-any-return]


def test_mock_clean_cell_characterization_pin(tmp_path, monkeypatch) -> None:
    """Frozen mock clean-cell outcome. Committed BEFORE the C1 fix; the C1
    commit must keep it green (proof C1 is a no-op without bus drops). The C2
    commit deliberately re-pins it (below-threshold holders stop exporting) —
    update the values IN THAT COMMIT ONLY, with old->new in the comment."""
    summary = _run_mock("haves_havenots__llm.yaml", tmp_path, monkeypatch)
    assert summary["served_load_fraction"] == pytest.approx(0.519560067167591, abs=5e-7)
    assert summary["transfer_count"] == 664
    assert summary["llm_call_counts_detailed"]["commitments_made"] == 2287
    # C1 (Task 3): this is a zero-drop mock cell, so no reply is ever refused —
    # the no-op proof the register-then-retract design depends on.
    assert summary["llm_call_counts_detailed"]["commitments_retracted"] == 0


# --- Task 3: C1 — retract commitments whose reply the bus refused ---


def test_retract_commitment_undoes_the_refused_reply(tmp_path) -> None:
    a = _agent(tmp_path)
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(t=t0, own_state=_own(8.0), inbox=[_request("r0c0", "c1", t0)], t_idx=0)
    (reply,) = a.react_to_pending(t=t0)
    assert len(a.commitments) == 1 and a.n_commitments_made == 1
    a.retract_commitment(reply)  # bus said False
    assert a.commitments == []
    assert a.n_commitments_retracted == 1
    assert a.n_commitments_made == 1  # made stays: the promise WAS uttered
    a.retract_commitment(reply)  # idempotent
    assert a.n_commitments_retracted == 1


def test_retract_is_a_noop_for_reject_replies(tmp_path) -> None:
    a = _agent(tmp_path, reply_text="REJECT\nrationale: no")
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(t=t0, own_state=_own(8.0), inbox=[_request("r0c0", "c2", t0)], t_idx=0)
    (reply,) = a.react_to_pending(t=t0)
    a.retract_commitment(reply)
    assert a.commitments == [] and a.n_commitments_retracted == 0


def _prepare_1x3_with_budget(tmp_path: Path, per_tick_budget: int | None):  # type: ignore[no-untyped-def]
    """Prepare a minimal 1x3 llm_agent cell under a comm per_tick_budget and
    return (decide, scenario, households). Modeled on
    tests/test_strategy_llm_agent.py::_prepare_with_failure; uses the shared
    _canned_mock (bare ACCEPT replies bind, plan policy fixed)."""
    from sim.agents.failure_modes import CommConfig, FailureModeConfig
    from sim.household import Household
    from sim.network import build_overlay_neighborhood
    from sim.scenario import Scenario
    from sim.strategies import llm_agent as llm_strat
    from sim.types import HouseholdProfile

    fm = FailureModeConfig(comm=CommConfig(per_tick_budget=per_tick_budget))
    scenario = Scenario(
        scenario_id="t",
        start=datetime(2026, 1, 1, 8, 0),
        end=datetime(2026, 1, 1, 8, 30),
        dt_hours=0.25,
        seed=42,
        rows=1,
        cols=3,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
        strategy="llm_agent",
        data_source="synthetic",
        household_sampling={
            "pv_kw_peak": [4.0, 4.0],
            "battery_kwh": [10.0, 10.0],
            "rt_efficiency": 0.9,
            "dod_floor_frac": 0.1,
        },
        failure_modes=fm,
    )
    households = {
        f"r0c{c}": Household(
            id=f"r0c{c}",
            pv_kw_peak=4.0,
            battery_kwh=10.0,
            battery_max_rate_kw=2.0,
            rt_efficiency=0.9,
            dod_floor_frac=0.1,
            grid_max_kw=10.0,
            profile=HouseholdProfile(description="t"),
        )
        for c in range(3)
    }
    nb = build_overlay_neighborhood(
        rows=1, cols=3, affiliations={}, bus_max_kw=50.0, bus_loss_factor=0.05
    )
    mock = _canned_mock(tmp_path / "cache")
    decide = llm_strat.prepare(
        scenario=scenario,
        households=households,
        solar=None,
        loads=None,
        neighborhood=nb,
        llm_client_factory=lambda model, run_dir: mock,
    )
    return decide, scenario, households


def _seed_two_requests_and_tick(decide, scenario, households):  # type: ignore[no-untyped-def]
    """Send two REQUESTs to the middle house (r0c1) so they're delivered on
    the first tick, then run one decide() tick. Returns the registry."""
    from datetime import timedelta

    from sim.household import HouseholdState
    from sim.network import build_overlay_neighborhood

    reg = decide.registry
    t0 = scenario.start
    dt = timedelta(hours=scenario.dt_hours)
    for sender, cid in (("r0c0", "req1"), ("r0c2", "req2")):
        reg.bus.send(
            Message(
                t_sent=t0 - dt,
                sender=sender,
                recipient="r0c1",
                performative="REQUEST",
                payload={"kwh": 0.9, "urgency": "normal"},
                rationale_nl="need energy",
                correlation_id=cid,
            )
        )
    states = {
        hid: HouseholdState(soc_kwh=5.0, last_solar_kw=0.0, last_load_kw=1.0, grid_connected=True)
        for hid in households
    }
    # grid-CONNECTED (not islanded): act() returns [] early for every agent,
    # so nothing serves/expires a commitment this tick — the assertions below
    # isolate the react/retract bookkeeping this test targets, undisturbed by
    # the commitment-serving physics in act() (which runs the same tick).
    grid = {hid: True for hid in households}
    solar_kw = {hid: 0.0 for hid in households}
    load_kw = {hid: 1.0 for hid in households}
    nb = build_overlay_neighborhood(
        rows=1, cols=3, affiliations={}, bus_max_kw=50.0, bus_loss_factor=0.05
    )
    decide(t0, states, households, solar_kw, load_kw, grid, nb, scenario.dt_hours)
    return reg


def test_budget_dropped_reply_leaves_no_commitment(tmp_path) -> None:
    decide, scenario, households = _prepare_1x3_with_budget(tmp_path, per_tick_budget=1)
    reg = _seed_two_requests_and_tick(decide, scenario, households)

    middle = reg.agents["r0c1"]
    assert middle.n_commitments_made == 2
    assert middle.n_commitments_retracted == 1
    assert len(middle.commitments) == 1
    dropped_accepts = [
        r for r in reg.bus.iter_log() if r["outcome"] == "dropped" and r["performative"] == "ACCEPT"
    ]
    assert len(dropped_accepts) == 1


def test_no_drop_run_retracts_nothing(tmp_path) -> None:
    decide, scenario, households = _prepare_1x3_with_budget(tmp_path, per_tick_budget=None)
    reg = _seed_two_requests_and_tick(decide, scenario, households)

    middle = reg.agents["r0c1"]
    assert middle.n_commitments_retracted == 0
    assert len(middle.commitments) == 2
