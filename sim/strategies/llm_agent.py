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

from sim.agents.agent import (
    _PLAN_SYSTEM_PROMPT_COOPERATIVE,
    _PLAN_SYSTEM_PROMPT_SELFISH,
    _REACT_SYSTEM_PROMPT_COOPERATIVE,
    _REACT_SYSTEM_PROMPT_SELFISH,
    LLMAgent,
)
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


LLMClientFactory = Callable[[str, Path], LLMClient]


def prepare(
    scenario: Scenario,
    households: dict[str, Household],
    solar: Any,
    loads: Any,
    neighborhood: Neighborhood,
    *,
    message_bus: MessageBus | None = None,
    run_dir: Path | None = None,
    llm_client_factory: LLMClientFactory | None = None,
    **_: Any,
) -> DecideFn:
    """Engine hook. Returns a ``decide_transfers`` callable bound to a fresh registry.

    Pass ``llm_client_factory`` to inject a test client (e.g., MockLLMClient).
    Defaults to ``_make_llm_client`` which builds an ``AnthropicLLMClient``.
    """
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
    factory = llm_client_factory or _make_llm_client
    client = factory(model, run_dir or Path("runs/_inline"))

    # Resolve per-agent system prompts based on defector realization.
    # `wrapper` (default Phase 2) leaves prompts cooperative and corrupts msgs at the bus.
    # `prompt` / `both` set the selfish system prompts for defectors so the LLM
    # itself is briefed to prioritize own household survival.
    use_selfish_prompt = fm.defector_realization in ("prompt", "both")

    # Phase 2.7: shared scenario context surfaced in every agent's plan prompt.
    # The outage horizon comes from the first OutageWindow; multi-window
    # scenarios just see the first one (good enough for the typical "one big
    # outage" scenario design).
    outage_start_iso = ""
    outage_end_iso = ""
    if scenario.outages:
        outage_start_iso = scenario.outages[0].start.isoformat()
        outage_end_iso = scenario.outages[0].end.isoformat()
    n_houses = len(households)

    agents: dict[str, LLMAgent] = {}
    for hid, hh in households.items():
        is_defector = hid in defectors
        plan_prompt = (
            _PLAN_SYSTEM_PROMPT_SELFISH
            if is_defector and use_selfish_prompt
            else _PLAN_SYSTEM_PROMPT_COOPERATIVE
        )
        react_prompt = (
            _REACT_SYSTEM_PROMPT_SELFISH
            if is_defector and use_selfish_prompt
            else _REACT_SYSTEM_PROMPT_COOPERATIVE
        )
        agents[hid] = LLMAgent(
            house_id=hid,
            scenario_seed=scenario.seed,
            trust_circles=dict(hh.affiliations or {}),
            policy=Policy.default_round_robin_fallback(),
            memory=MemoryStream(),
            llm_client=client,
            model=model,
            noise=noise,
            system_prompt_plan=plan_prompt,
            system_prompt_react=react_prompt,
            household_context={
                "battery_kwh": float(hh.battery_kwh),
                "battery_max_rate_kw": float(hh.battery_max_rate_kw),
                "rt_efficiency": float(hh.rt_efficiency),
                "dod_floor_frac": float(hh.dod_floor_frac),
                "outage_start_iso": outage_start_iso,
                "outage_end_iso": outage_end_iso,
                "n_houses_neighborhood": n_houses,
            },
        )

    _REGISTRY = _AgentRegistry(
        agents=agents,
        bus=bus,
        defector_wrapper=wrapper,
    )
    return decide_transfers


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
        if agent.should_replan(grid_islanded=not grid[hid], t=t):
            agent.plan(t=t)

    # 4. React to pending messages
    for agent in reg.agents.values():
        replies = agent.react_to_pending(t=t)
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
        transfers, outbox = agent.act(
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


def current_call_counts() -> dict[str, int]:
    """Aggregate LLM call counters across all agents in the current run.

    Returns zeros if no run has been prepared. Callable from ``scripts/run.py``
    after the engine returns to fill summary.json's `llm_call_counts` field.
    """
    if _REGISTRY is None:
        return {
            "reflect_plan": 0,
            "react_msg": 0,
            "react_skipped": 0,
            "plan_parse_failures": 0,
            "plan_fallbacks": 0,
            "react_refusals": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }
    plan = sum(a.n_plan_calls for a in _REGISTRY.agents.values())
    react = sum(a.n_react_calls for a in _REGISTRY.agents.values())
    react_skipped = sum(a.n_react_skipped for a in _REGISTRY.agents.values())
    parse_fails = sum(a.n_plan_parse_failures for a in _REGISTRY.agents.values())
    fallbacks = sum(a.n_plan_fallbacks for a in _REGISTRY.agents.values())
    refusals = sum(a.n_react_refusals for a in _REGISTRY.agents.values())
    # Cache hits/misses come from the shared LLM client (all agents share one).
    # The client lives on each agent; pick any.
    any_agent = next(iter(_REGISTRY.agents.values()))
    cache = any_agent.llm_client.cache
    return {
        "reflect_plan": plan,
        "react_msg": react,
        "react_skipped": react_skipped,
        "plan_parse_failures": parse_fails,
        "plan_fallbacks": fallbacks,
        "react_refusals": refusals,
        "cache_hits": getattr(cache, "n_hits", 0),
        "cache_misses": getattr(cache, "n_misses", 0),
    }


def update_summary_with_counts(run_dir: Path) -> None:
    """Read run_dir/summary.json, fill in llm_call_counts + policy_* fields, write back."""
    import json

    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return
    summary = json.loads(summary_path.read_text())
    counts = current_call_counts()
    summary["llm_call_counts"] = {
        "reflect_plan": counts["reflect_plan"],
        "react_msg": counts["react_msg"],
        "cache_hits": counts["cache_hits"],
        "cache_misses": counts["cache_misses"],
    }
    summary["policy_parse_failures"] = counts["plan_parse_failures"]
    summary["policy_fallbacks_to_round_robin"] = counts["plan_fallbacks"]
    # Also extend with finer-grained Phase-2.5 fields.
    summary["llm_call_counts_detailed"] = counts
    summary_path.write_text(json.dumps(summary, indent=2))
