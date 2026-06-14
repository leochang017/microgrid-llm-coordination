"""LLMAgent: per-household policy-driven agent with memory + reflection + reactive messaging.

This module is built up across Tasks 13-16:
- Task 13: __init__, observe (with memory append + pending_react queue + RNG seeding)
- Task 14: act (pure-Python tick executor)
- Task 15: plan (combined reflect+plan LLM call)
- Task 16: react_to_pending + triggers
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sim.agents.failure_modes import NoiseSource
from sim.agents.llm import LLMClient
from sim.agents.memory import MemoryEntry, MemoryStream
from sim.agents.policy import Policy
from sim.agents.protocol import Message


@dataclass
class LLMAgent:
    house_id: str
    scenario_seed: int
    trust_circles: dict[str, str]
    policy: Policy
    memory: MemoryStream
    llm_client: LLMClient
    model: str
    noise: NoiseSource

    policy_age_ticks: int = 0
    last_plan_t: datetime | None = None
    pending_react: list[Message] = field(default_factory=list)
    last_soc_frac: float | None = None
    last_grid_islanded: bool = False
    _prev_soc_frac: float | None = field(default=None, init=False, repr=False)

    react_max_per_tick: int = 3
    plan_consecutive_failures: int = field(default=0, init=False)

    rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(hash((self.scenario_seed, "agent", self.house_id)) & 0xFFFFFFFF)

    def observe(
        self,
        t: datetime,
        own_state: dict[str, Any],
        peer_states: dict[str, dict[str, Any]],
        inbox: list[Message],
        t_idx: int,
    ) -> None:
        visible_soc = self.noise.noise_soc(
            t_idx=t_idx,
            house_id=self.house_id,
            true_soc=float(own_state["soc_kwh"]),
            capacity=float(own_state["soc_capacity"]),
        )
        visible_load = self.noise.noise_load(
            t_idx=t_idx,
            house_id=self.house_id,
            true_load=float(own_state["load_kw"]),
        )
        capacity = float(own_state["soc_capacity"])
        self.memory.append(
            MemoryEntry(
                t=t,
                kind="obs",
                content={
                    "own_soc_kwh": visible_soc,
                    "own_soc_capacity": capacity,
                    "grid_islanded": bool(own_state["grid_islanded"]),
                    "own_load_kw": visible_load,
                    "own_solar_kw": float(own_state.get("solar_kw", 0.0)),
                    "peer_states": peer_states,
                },
                nl=(
                    f"SoC={visible_soc:.2f}/{capacity:.0f} kWh; "
                    f"islanded={bool(own_state['grid_islanded'])}; "
                    f"load={visible_load:.2f} kW"
                ),
                importance=5.0,
            )
        )
        for m in inbox:
            self.memory.append(
                MemoryEntry(
                    t=t,
                    kind="msg_recv",
                    content={
                        "sender": m.sender,
                        "performative": m.performative,
                        "payload": dict(m.payload),
                        "correlation_id": m.correlation_id,
                    },
                    nl=f"from {m.sender}: {m.performative} payload={m.payload} — {m.rationale_nl}",
                    importance=6.0 if m.performative in ("REQUEST", "OFFER", "REJECT") else 4.0,
                )
            )
        # Queue REQUEST/OFFER for react step (Task 16)
        self.pending_react = [m for m in inbox if m.performative in ("REQUEST", "OFFER")]
        # Trigger-tracking
        self._prev_soc_frac = self.last_soc_frac
        self.last_soc_frac = visible_soc / max(1e-9, capacity)
        self.last_grid_islanded = bool(own_state["grid_islanded"])


_SHARE_FRACTION = 0.20  # of headroom per tick (module-level for ease of testing)


def _agent_act(
    self: LLMAgent,
    t: datetime,
    own_state: dict[str, Any],
    neighborhood: Any,  # sim.network.Neighborhood — late-bound to avoid cycle
    dt_hours: float,
) -> tuple[list[Any], list[Message]]:
    """Pure-Python tick executor — see LLMAgent.act bound below."""
    from sim.agents.protocol import new_correlation_id
    from sim.types import Transfer

    if not bool(own_state.get("grid_islanded", False)):
        return [], []

    soc = float(own_state["soc_kwh"])
    capacity = float(own_state["soc_capacity"])
    dod_floor = float(own_state.get("dod_floor_frac", 0.1)) * capacity
    headroom_kwh = max(0.0, soc - dod_floor)
    soc_frac = soc / max(1e-9, capacity)

    if soc_frac < self.policy.share_min_soc_frac:
        return [], _emit_requests(self, t, neighborhood, soc_frac)

    candidates = _candidate_recipients(self, neighborhood)
    if not candidates:
        return [], []

    share_kwh = min(
        _SHARE_FRACTION * headroom_kwh,
        self.policy.max_share_kw_per_tick * dt_hours,
    )
    share_kw = share_kwh / dt_hours
    if share_kw <= 0:
        return [], []

    total_weight = sum(w for _, _, w in candidates)
    if total_weight <= 0:
        return [], []

    transfers: list[Any] = []
    outbox: list[Message] = []
    for target, circle, weight in candidates:
        kw = share_kw * (weight / total_weight)
        if kw <= 0:
            continue
        transfers.append(Transfer(from_id=self.house_id, to_id=target, kw=kw))
        outbox.append(
            Message(
                t_sent=t,
                sender=self.house_id,
                recipient=target,
                performative="OFFER",
                payload={"kwh": kw * dt_hours},
                rationale_nl=(
                    f"SoC {soc:.2f}/{capacity:.0f} kWh "
                    f"({soc_frac:.2f} frac) above {self.policy.share_min_soc_frac:.2f} threshold; "
                    f"sharing {kw:.2f} kW via {circle} circle."
                ),
                correlation_id=new_correlation_id(rng=self.rng),
            )
        )
    return transfers, outbox


def _candidate_recipients(self: LLMAgent, neighborhood: Any) -> list[tuple[str, str, float]]:
    """Return [(target_hid, circle, weight)] for each (peer, circle) the policy ranks."""
    distrusted = set(self.policy.distrusted_peers)
    weight_by_circle = {rp.circle: rp.weight for rp in self.policy.recipient_priority}
    candidates: list[tuple[str, str, float]] = []
    for circle, edges in neighborhood.edges_by_type.items():
        weight = weight_by_circle.get(circle, 0.0)
        if weight <= 0:
            continue
        for nb in edges.get(self.house_id, []):
            if nb == self.house_id or nb in distrusted:
                continue
            candidates.append((nb, circle, weight))
    return candidates


def _emit_requests(
    self: LLMAgent, t: datetime, neighborhood: Any, soc_frac: float
) -> list[Message]:
    """Below-threshold houses send REQUEST messages to highest-priority circles."""
    from sim.agents.protocol import new_correlation_id

    candidates = _candidate_recipients(self, neighborhood)
    candidates.sort(key=lambda x: x[2], reverse=True)
    top = candidates[:3]
    out: list[Message] = []
    urgency = self.policy.request_urgency
    for target, circle, _w in top:
        out.append(
            Message(
                t_sent=t,
                sender=self.house_id,
                recipient=target,
                performative="REQUEST",
                payload={"kwh": 0.5, "urgency": urgency},
                rationale_nl=(
                    f"SoC frac {soc_frac:.2f} below share threshold; "
                    f"requesting energy via {circle} circle."
                ),
                correlation_id=new_correlation_id(rng=self.rng),
            )
        )
    return out


# Bind methods onto LLMAgent (this avoids the class body getting too long
# while still landing the methods on the class for normal dot-call use):
LLMAgent.act = _agent_act  # type: ignore[attr-defined]


_PLAN_SYSTEM_PROMPT = (
    "You are the planning subroutine of a household energy-coordination agent. "
    "Given recent state, beliefs, and trust circles, output (1) a one-paragraph "
    "REFLECTION on what you've observed (just text), and (2) a POLICY in a YAML "
    "code-fence — sharing_intent (conservative|balanced|generous), "
    "share_min_soc_frac (0..1), max_share_kw_per_tick (kW), recipient_priority "
    "(list of {circle, weight}), distrusted_peers (list of house ids), "
    "request_urgency (low|normal|urgent), belief_note (string), ttl_ticks (int >= 1)."
)


def _agent_plan(self: LLMAgent, t: datetime) -> None:
    """One combined LLM call that updates beliefs AND refreshes the policy.

    On 3 consecutive parse failures, fall back to the default round_robin policy.
    """
    import re

    from sim.agents.llm import LLMRequest
    from sim.agents.policy import PolicyValidationError, policy_from_yaml

    recents = self.memory.top_k(now=t, k=20)
    recents_str = (
        "\n".join(f"  - [{e.t.isoformat()} {e.kind}] {e.nl}" for e in recents)
        or "  (no recent memories)"
    )
    circles_str = ", ".join(f"{k}={v}" for k, v in sorted(self.trust_circles.items()))
    latest_obs = next((e for e in reversed(recents) if e.kind == "obs"), None)
    state_summary = latest_obs.nl if latest_obs else "(no state observed yet)"

    prompt = (
        f"You are household {self.house_id}.\n"
        f"Trust circles: {circles_str or '(none)'}.\n"
        f"Current state: {state_summary}.\n"
        f"Current policy belief: {self.policy.belief_note or '(none)'}.\n"
        f"Recent memories (top-20):\n{recents_str}\n\n"
        f"Output reflection text, then a POLICY in a ```yaml ... ``` code fence."
    )
    resp = self.llm_client.call(
        LLMRequest(
            model=self.model,
            system=_PLAN_SYSTEM_PROMPT,
            user=prompt,
            max_tokens=800,
        )
    )

    new_policy = None
    match = re.search(r"```(?:yaml)?\s*\n(.*?)\n```", resp.text, flags=re.DOTALL)
    if match:
        try:
            new_policy = policy_from_yaml(match.group(1))
        except (PolicyValidationError, Exception):
            new_policy = None

    if new_policy is None:
        self.plan_consecutive_failures += 1
        self.memory.append(
            MemoryEntry(
                t=t,
                kind="reflection",
                content={"parse_failure": True},
                nl="(policy parse failed; keeping previous policy)",
                importance=8.0,
            )
        )
        if self.plan_consecutive_failures >= 3:
            from sim.agents.policy import Policy as _P

            self.policy = _P.default_round_robin_fallback()
    else:
        self.policy = new_policy
        self.plan_consecutive_failures = 0
        # Extract reflection text (everything before the first ``` fence)
        rmatch = re.search(r"^(.*?)```", resp.text, flags=re.DOTALL)
        reflection_text = rmatch.group(1).strip()[:280] if rmatch else resp.text.strip()[:280]
        if reflection_text:
            self.memory.append(
                MemoryEntry(
                    t=t,
                    kind="reflection",
                    content={"reflection": reflection_text},
                    nl=reflection_text,
                    importance=7.0,
                )
            )
    self.policy_age_ticks = 0
    self.last_plan_t = t


LLMAgent.plan = _agent_plan  # type: ignore[attr-defined]
