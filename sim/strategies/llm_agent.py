"""Thin facade for the LLM-agent strategy.

This module is the ONLY place that imports both ``sim.agents`` and is callable
from ``sim.engine`` via the strategy plug-point. The engine itself does not
import the agent layer.

``prepare(...)`` instantiates one ``LLMAgent`` per household and binds them to
a shared ``MessageBus`` (passed in by the engine via the prepare hook).
``decide_transfers(t, ...)`` delegates to each agent's ``act()`` and returns
the union of their transfer intents.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sim.agents.agent import LLMAgent
from sim.agents.cache import PromptCache
from sim.agents.failure_modes import (
    DefectorWrapper,
    NoiseSource,
    assign_defectors,
)
from sim.agents.llm import AnthropicLLMClient, LLMClient
from sim.agents.memory import MemoryStream
from sim.agents.policy import Policy
from sim.agents.protocol import MessageBus
from sim.household import Household
from sim.network import Neighborhood
from sim.scenario import Scenario
from sim.types import Transfer

DecideFn = Callable[..., list[Transfer]]


@dataclass
class _AgentRegistry:
    agents: dict[str, LLMAgent]
    bus: MessageBus
    defector_wrapper: DefectorWrapper
    tick_index: dict[datetime, int] = field(default_factory=dict)
    next_tick_idx: int = 0

    def t_idx(self, t: datetime) -> int:
        if t not in self.tick_index:
            self.tick_index[t] = self.next_tick_idx
            self.next_tick_idx += 1
        return self.tick_index[t]


_REGISTRY: _AgentRegistry | None = None


def _make_llm_client(model: str, run_dir: Path) -> LLMClient:
    """Factory; overridden by tests to inject a MockLLMClient."""
    del model
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    cache = PromptCache(
        local_dir=run_dir / "llm_cache",
        reference_dir=_reference_cache_dir(run_dir),
    )
    return AnthropicLLMClient(cache=cache, api_key=api_key)


def _reference_cache_dir(run_dir: Path) -> Path | None:
    """Walk up from runs/<scenario>/<strategy>/<ts>/ to find reference_runs/."""
    try:
        repo_root = run_dir.parent.parent.parent
        scen = run_dir.parent.parent.name
        strat = run_dir.parent.name
    except Exception:
        return None
    cell = os.environ.get("MICROGRID_REFERENCE_CELL", "clean")
    candidate = repo_root / "reference_runs" / scen / strat / cell / "llm_cache"
    return candidate if candidate.exists() else None


def prepare(
    scenario: Scenario,
    households: dict[str, Household],
    solar: Any,
    loads: Any,
    neighborhood: Neighborhood,
    *,
    message_bus: MessageBus | None = None,
    run_dir: Path | None = None,
    **_: Any,
) -> DecideFn:
    """Engine hook. Returns a ``decide_transfers`` callable bound to a fresh registry."""
    global _REGISTRY
    del solar, loads

    fm = scenario.failure_modes
    house_ids = list(households)
    defectors = assign_defectors(house_ids, fm, scenario.seed)
    bus = message_bus or MessageBus(neighborhood=neighborhood, seed=scenario.seed)
    bus.configure_failure_modes(
        drop_prob_by_circle=fm.comm.drop_prob_by_circle,
        per_tick_budget=fm.comm.per_tick_budget,
    )
    noise = NoiseSource(cfg=fm.obs_noise, scenario_seed=scenario.seed)
    wrapper = DefectorWrapper(defectors=defectors, scenario_seed=scenario.seed)

    model = scenario.llm.get("model", "claude-haiku-4-5-20251001")
    client = _make_llm_client(
        model=model,
        run_dir=run_dir or Path("runs/_inline"),
    )

    agents: dict[str, LLMAgent] = {}
    for hid, hh in households.items():
        agents[hid] = LLMAgent(
            house_id=hid,
            scenario_seed=scenario.seed,
            trust_circles=dict(hh.affiliations or {}),
            policy=_initial_policy(is_defector_prompt=hid in defectors),
            memory=MemoryStream(),
            llm_client=client,
            model=model,
            noise=noise,
        )

    _REGISTRY = _AgentRegistry(
        agents=agents,
        bus=bus,
        defector_wrapper=wrapper,
    )
    return decide_transfers


def _initial_policy(is_defector_prompt: bool) -> Policy:
    # All agents start with the same balanced default. The `is_defector_prompt`
    # flag is computed for parity with the spec but its *effect* (selfish system-
    # prompt override on plan/react calls) is deferred — see Phase 2 known
    # limitations. The `wrapper` realization (Task 11) is the default ablation.
    del is_defector_prompt
    return Policy.default_round_robin_fallback()


def decide_transfers(
    t: datetime,
    states: dict[str, Any],
    households: dict[str, Household],
    solar_kw: dict[str, float],
    load_kw: dict[str, float],
    grid: dict[str, bool],
    neighborhood: Neighborhood,
    dt_hours: float,
) -> list[Transfer]:
    assert _REGISTRY is not None, "llm_agent.prepare() must be called before decide_transfers"
    reg = _REGISTRY
    t_idx = reg.t_idx(t)

    # 1. Deliver pending messages from prior tick into agent inboxes
    inboxes = reg.bus.deliver_pending(t)

    # 2. Each agent observes
    for hid, agent in reg.agents.items():
        own = states[hid]
        own_state = {
            "soc_kwh": own.soc_kwh,
            "soc_capacity": households[hid].battery_kwh,
            "grid_islanded": not grid[hid],
            "load_kw": load_kw.get(hid, 0.0),
            "solar_kw": solar_kw.get(hid, 0.0),
            "dod_floor_frac": households[hid].dod_floor_frac,
        }
        peer_states = {
            p: {"soc_kwh": states[p].soc_kwh, "soc_capacity": households[p].battery_kwh}
            for p in neighborhood.union_neighbors(hid)
            if p in states
        }
        agent.observe(
            t=t,
            own_state=own_state,
            peer_states=peer_states,
            inbox=inboxes.get(hid, []),
            t_idx=t_idx,
        )

    # 3. Replan where needed
    for hid, agent in reg.agents.items():
        if agent.should_replan(grid_islanded=not grid[hid], t=t):  # type: ignore[attr-defined]
            agent.plan(t=t)  # type: ignore[attr-defined]

    # 4. React to pending messages
    for agent in reg.agents.values():
        replies = agent.react_to_pending(t=t)  # type: ignore[attr-defined]
        for m in replies:
            reg.bus.send(reg.defector_wrapper.maybe_corrupt(m))

    # 5. Act: collect transfers + outbound messages
    all_transfers: list[Transfer] = []
    for hid, agent in reg.agents.items():
        own = states[hid]
        own_state = {
            "soc_kwh": own.soc_kwh,
            "soc_capacity": households[hid].battery_kwh,
            "grid_islanded": not grid[hid],
            "load_kw": load_kw.get(hid, 0.0),
            "solar_kw": solar_kw.get(hid, 0.0),
            "dod_floor_frac": households[hid].dod_floor_frac,
        }
        transfers, outbox = agent.act(  # type: ignore[attr-defined]
            t=t,
            own_state=own_state,
            neighborhood=neighborhood,
            dt_hours=dt_hours,
        )
        all_transfers.extend(transfers)
        for m in outbox:
            reg.bus.send(reg.defector_wrapper.maybe_corrupt(m))

    # 6. Age policies
    for agent in reg.agents.values():
        agent.policy_age_ticks += 1

    return all_transfers
