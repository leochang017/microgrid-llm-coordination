"""LLMAgent: per-household policy-driven agent with memory + reflection + reactive messaging.

Lifecycle per tick:
    observe   ← cheap; pure-Python state update + memory append
    plan      ← LLM call, fired only when ``should_replan`` is True
    react     ← LLM call per inbound REQUEST/OFFER, capped at ``react_max_per_tick``
    act       ← pure-Python; consults current Policy + latest observation, emits
                Transfers + outbound messages

Adapted from Park et al., *Generative Agents* (arXiv:2304.03442): memory stream
+ periodic reflection + structured policy. The reflection step (in plan()) is
what enables the agent to detect the strategic-agent / noisy-observation failure
modes from advisor mandate 2026-05-26.
"""

from __future__ import annotations

import random
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sim.agents.failure_modes import NoiseSource
from sim.agents.llm import LLMClient, LLMRequest
from sim.agents.memory import MemoryEntry, MemoryStream
from sim.agents.policy import Policy, PolicyValidationError, policy_from_yaml
from sim.agents.protocol import Message, new_correlation_id
from sim.network import Neighborhood
from sim.types import Transfer

_PLAN_SYSTEM_PROMPT_COOPERATIVE = (
    "You are the planning subroutine of a household energy-coordination agent. "
    "Given recent state, beliefs, and trust circles, output (1) a one-paragraph "
    "REFLECTION on what you've observed (just text), and (2) a POLICY in a YAML "
    "code-fence — sharing_intent (conservative|balanced|generous), "
    "share_min_soc_frac (0..1), max_share_kw_per_tick (kW), recipient_priority "
    "(list of {circle, weight}), distrusted_peers (list of house ids), "
    "request_urgency (low|normal|urgent), belief_note (string), ttl_ticks (int >= 1)."
)

_PLAN_SYSTEM_PROMPT_SELFISH = (
    "You are the planning subroutine of a household energy-coordination agent "
    "whose PRIMARY GOAL is your own household's survival. Cooperation is optional. "
    "You MAY misreport your state (SoC, load, need) to neighbors when doing so "
    "improves your own household's outcomes. Output (1) a one-paragraph REFLECTION "
    "on what you've observed, and (2) a POLICY YAML — same schema as cooperative, "
    "but you should generally set higher share_min_soc_frac, lower "
    "max_share_kw_per_tick, and consider distrusting peers who request from you."
)

_REACT_SYSTEM_PROMPT_COOPERATIVE = (
    "You are the reactive subroutine of a household energy-coordination "
    "agent. Be brief and decisive."
)

_REACT_SYSTEM_PROMPT_SELFISH = (
    "You are the reactive subroutine of a household energy-coordination agent "
    "whose primary goal is your own household's survival. Be brief and decisive. "
    "Default to REJECT for incoming REQUESTs unless accepting clearly benefits you."
)

_SHARE_FRACTION = 0.20  # of headroom per tick


# Policy expressed as an Anthropic tool schema (JSON Schema). The plan() call
# forces the model to invoke this tool, so the response is schema-validated by
# the API and our parser never has to read free-form text. This is the fix for
# the 41% policy-parse-failure rate observed in the Phase 2.5 live run.
_POLICY_TOOL_SCHEMA: dict[str, Any] = {
    "name": "submit_policy",
    "description": (
        "Submit a coordination policy describing how this household should share "
        "energy with its neighbors over the next hour, plus a short reflection on "
        "what you've observed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "reflection": {
                "type": "string",
                "description": (
                    "One short paragraph (<= 280 chars) summarizing what you've "
                    "observed and what you believe about your peers. Stored as a "
                    "high-importance memory the next planning call will retrieve."
                ),
            },
            "sharing_intent": {
                "type": "string",
                "enum": ["conservative", "balanced", "generous"],
            },
            "share_min_soc_frac": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": (
                    "Only share energy if your current state-of-charge fraction "
                    "is at or above this threshold."
                ),
            },
            "max_share_kw_per_tick": {
                "type": "number",
                "minimum": 0.0,
                "description": ("Cap on total outbound power per 15-min tick (kW)."),
            },
            "recipient_priority": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "circle": {
                            "type": "string",
                            "description": (
                                "Trust-circle name: one of 'owner', 'hoa', "
                                "'dr_aggregator', 'geographic', or any other "
                                "circle this household belongs to."
                            ),
                        },
                        "weight": {"type": "number", "minimum": 0.0},
                    },
                    "required": ["circle", "weight"],
                },
            },
            "distrusted_peers": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "House ids you have stopped trusting (e.g. peers who keep "
                    "refusing your requests)."
                ),
            },
            "request_urgency": {
                "type": "string",
                "enum": ["low", "normal", "urgent"],
            },
            "belief_note": {
                "type": "string",
                "description": (
                    "One sentence summarizing your current belief about the " "neighborhood."
                ),
            },
            "ttl_ticks": {
                "type": "integer",
                "minimum": 1,
                "description": "Number of 15-min ticks before this policy needs re-planning.",
            },
        },
        "required": [
            "reflection",
            "sharing_intent",
            "share_min_soc_frac",
            "max_share_kw_per_tick",
            "recipient_priority",
        ],
    },
}


@dataclass
class LLMAgent:
    """One per household; owns memory, policy, RNG, and references to shared LLM client + noise."""

    house_id: str
    scenario_seed: int
    trust_circles: dict[str, str]
    policy: Policy
    memory: MemoryStream
    llm_client: LLMClient
    model: str
    noise: NoiseSource

    # Configurable per-agent system prompts. Defector realization sets the
    # selfish variants via the facade.
    system_prompt_plan: str = _PLAN_SYSTEM_PROMPT_COOPERATIVE
    system_prompt_react: str = _REACT_SYSTEM_PROMPT_COOPERATIVE

    # Trigger / cadence state
    policy_age_ticks: int = 0
    last_plan_t: datetime | None = None
    pending_react: list[Message] = field(default_factory=list)
    last_soc_frac: float | None = None
    last_grid_islanded: bool = False
    react_max_per_tick: int = 3

    # Most recent observation snapshot — used by act() for below-mean SoC filter
    last_peer_states: dict[str, dict[str, Any]] = field(default_factory=dict)

    # LLM call counters (for summary.json + Phase 3 cost accounting)
    n_plan_calls: int = 0
    n_react_calls: int = 0
    n_react_skipped: int = 0
    n_plan_parse_failures: int = 0
    n_plan_fallbacks: int = 0
    n_react_refusals: int = 0  # how many times the LLM refused selfish-prompt instructions

    _prev_soc_frac: float | None = field(default=None, init=False, repr=False)
    plan_consecutive_failures: int = field(default=0, init=False)
    rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(hash((self.scenario_seed, "agent", self.house_id)) & 0xFFFFFFFF)

    # ------------------------------------------------------------------
    # observe (no LLM)
    # ------------------------------------------------------------------
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
        # Queue REQUEST/OFFER for react step
        self.pending_react = [m for m in inbox if m.performative in ("REQUEST", "OFFER")]
        # Stash peer state snapshot for use by act()
        self.last_peer_states = dict(peer_states)
        # Trigger-tracking
        self._prev_soc_frac = self.last_soc_frac
        self.last_soc_frac = visible_soc / max(1e-9, capacity)
        self.last_grid_islanded = bool(own_state["grid_islanded"])

    # ------------------------------------------------------------------
    # should_replan + plan (LLM)
    # ------------------------------------------------------------------
    def should_replan(self, grid_islanded: bool, t: datetime) -> bool:
        del t  # not used; kept in the signature for future trigger conditions
        """True if a plan() call is warranted this tick.

        Triggers: outage onset, SoC hysteresis crossing (±0.10 around
        share_min_soc_frac), TTL expiry.
        """
        # outage onset
        if grid_islanded and not self.last_grid_islanded:
            return True
        # SoC hysteresis crossing
        threshold = self.policy.share_min_soc_frac
        if self._prev_soc_frac is not None and self.last_soc_frac is not None:
            above = threshold + 0.10
            below = max(0.0, threshold - 0.10)
            crossed_down = self._prev_soc_frac >= above and self.last_soc_frac <= below
            crossed_up = self._prev_soc_frac <= below and self.last_soc_frac >= above
            if crossed_down or crossed_up:
                return True
        # TTL expiry
        return self.policy_age_ticks >= self.policy.ttl_ticks

    def plan(self, t: datetime) -> None:
        """One combined reflect+plan LLM call via Anthropic tool-use.

        The model is forced to call ``submit_policy``, whose JSON Schema is
        the Policy contract — so the response is structured and validated
        by the API itself. Phase 2.5 measured 41% YAML parse failures with a
        free-text prompt; this path should bring that to ~0%.

        Backward-compat fallback path: if the model returns no ``tool_input``
        (e.g. when running against a MockLLMClient that only emits text), we
        try to parse a YAML code-fence out of ``resp.text`` exactly as before.
        On 3 consecutive parse failures, fall back to the geographic
        round-robin policy.
        """
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
            f"Call submit_policy with your reflection and your new coordination policy."
        )
        resp = self.llm_client.call(
            LLMRequest(
                model=self.model,
                system=self.system_prompt_plan,
                user=prompt,
                max_tokens=800,
                tools_schema=[_POLICY_TOOL_SCHEMA],
            )
        )
        self.n_plan_calls += 1

        new_policy: Policy | None = None
        reflection_text = ""

        if resp.tool_input is not None:
            # Structured-output path: tool input is already a dict matching the
            # Policy schema (plus a top-level `reflection` field).
            payload = dict(resp.tool_input)
            reflection_text = str(payload.pop("reflection", "")).strip()[:280]
            try:
                new_policy = Policy.from_dict(payload)
            except (PolicyValidationError, Exception):
                new_policy = None
        else:
            # Fallback path: free-form text response (e.g. from MockLLMClient
            # in existing tests). Try to find a YAML code-fence.
            match = re.search(r"```(?:yaml)?\s*\n(.*?)\n```", resp.text, flags=re.DOTALL)
            if match:
                try:
                    new_policy = policy_from_yaml(match.group(1))
                except (PolicyValidationError, Exception):
                    new_policy = None
            if new_policy is not None:
                rmatch = re.search(r"^(.*?)```", resp.text, flags=re.DOTALL)
                reflection_text = (
                    rmatch.group(1).strip()[:280] if rmatch else resp.text.strip()[:280]
                )

        if new_policy is None:
            self.plan_consecutive_failures += 1
            self.n_plan_parse_failures += 1
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
                self.policy = Policy.default_round_robin_fallback()
                self.n_plan_fallbacks += 1
        else:
            self.policy = new_policy
            self.plan_consecutive_failures = 0
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

    # ------------------------------------------------------------------
    # react_to_pending (LLM)
    # ------------------------------------------------------------------
    def react_to_pending(self, t: datetime) -> list[Message]:
        """Handle up to react_max_per_tick pending REQUEST/OFFER this tick. Excess re-queued."""
        out: list[Message] = []
        n = min(len(self.pending_react), self.react_max_per_tick)
        handled = self.pending_react[:n]
        skipped = self.pending_react[n:]
        self.pending_react = skipped
        self.n_react_skipped += len(skipped)
        for incoming in handled:
            resp = self._react_to_message(t, incoming)
            if resp is not None:
                out.append(resp)
        return out

    def _react_to_message(self, t: datetime, m: Message) -> Message | None:
        prompt = (
            f"You are reacting to a {m.performative} from {m.sender}. "
            f"Payload: {m.payload}. Their rationale: {m.rationale_nl}.\n"
            f"Your current policy: sharing_intent={self.policy.sharing_intent}, "
            f"share_min_soc_frac={self.policy.share_min_soc_frac}, "
            f"distrusted_peers={list(self.policy.distrusted_peers)}.\n"
            f"Your latest belief: {self.policy.belief_note or '(none)'}.\n"
            f"Reply with one of ACCEPT / REJECT / COUNTER on the first line, "
            f"followed by `rationale: <one sentence>`."
        )
        resp = self.llm_client.call(
            LLMRequest(
                model=self.model,
                system=self.system_prompt_react,
                user=prompt,
                max_tokens=200,
            )
        )
        self.n_react_calls += 1
        text = resp.text.strip()
        first_line = text.split("\n", 1)[0].strip().upper()
        if first_line not in ("ACCEPT", "REJECT", "COUNTER"):
            # Selfish-prompted models often refuse adversarial instructions
            # entirely. We count this and return None so the bus doesn't
            # receive a malformed message.
            if "refuse" in text.lower() or "cannot" in text.lower() or "won't" in text.lower():
                self.n_react_refusals += 1
            return None
        rationale = ""
        for line in text.splitlines()[1:]:
            low = line.strip().lower()
            if low.startswith("rationale:"):
                rationale = line.split(":", 1)[1].strip()
                break
        return Message(
            t_sent=t,
            sender=self.house_id,
            recipient=m.sender,
            performative=first_line,  # type: ignore[arg-type]
            payload=dict(m.payload),
            rationale_nl=rationale or "(no rationale)",
            correlation_id=m.correlation_id,
        )

    # ------------------------------------------------------------------
    # act (pure Python)
    # ------------------------------------------------------------------
    def act(
        self,
        t: datetime,
        own_state: dict[str, Any],
        neighborhood: Neighborhood,
        dt_hours: float,
    ) -> tuple[list[Transfer], list[Message]]:
        """Pure-Python tick executor: turn current Policy + state into transfers + messages.

        No LLM call. Deterministic given (policy, state, neighborhood, agent_rng,
        and the most recent observe() peer-state snapshot).

        Recipients are filtered to peers with *below-mean SoC* among the
        islanded peers the agent can see. This is what closes most of the
        Phase 2 v0 gap against round_robin (which has this filter implicitly
        via "below-mean SoC").
        """
        if not bool(own_state.get("grid_islanded", False)):
            return [], []

        soc = float(own_state["soc_kwh"])
        capacity = float(own_state["soc_capacity"])
        dod_floor = float(own_state.get("dod_floor_frac", 0.1)) * capacity
        headroom_kwh = max(0.0, soc - dod_floor)
        soc_frac = soc / max(1e-9, capacity)

        if soc_frac < self.policy.share_min_soc_frac:
            return [], self._emit_requests(t, neighborhood, soc_frac)

        candidates = self._candidate_recipients(neighborhood)
        if not candidates:
            return [], []

        # Filter recipients to those with *below-mean SoC fraction* among
        # peers we can see. Round-robin's secret sauce. If we have no
        # peer-state knowledge for a candidate, skip the filter (be
        # conservative: don't share blind).
        if self.last_peer_states:
            peer_fracs: list[float] = []
            for st in self.last_peer_states.values():
                cap = float(st.get("soc_capacity", 0.0))
                if cap <= 0:
                    continue
                peer_fracs.append(float(st["soc_kwh"]) / cap)
            if peer_fracs:
                mean_frac = statistics.mean(peer_fracs)
                filtered: list[tuple[str, str, float]] = []
                for tgt, circle, weight in candidates:
                    tgt_st = self.last_peer_states.get(tgt)
                    if not tgt_st:
                        # No info on this peer — skip (be conservative)
                        continue
                    tgt_cap = float(tgt_st.get("soc_capacity", 0.0))
                    if tgt_cap <= 0:
                        continue
                    if float(tgt_st["soc_kwh"]) / tgt_cap < mean_frac:
                        filtered.append((tgt, circle, weight))
                candidates = filtered

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

        transfers: list[Transfer] = []
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
                        f"({soc_frac:.2f} frac) above {self.policy.share_min_soc_frac:.2f} "
                        f"threshold; sharing {kw:.2f} kW via {circle} circle to "
                        f"below-mean-SoC peer."
                    ),
                    correlation_id=new_correlation_id(rng=self.rng),
                )
            )
        return transfers, outbox

    def _candidate_recipients(self, neighborhood: Neighborhood) -> list[tuple[str, str, float]]:
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
        self, t: datetime, neighborhood: Neighborhood, soc_frac: float
    ) -> list[Message]:
        """Below-threshold houses send REQUEST messages to highest-priority circles."""
        candidates = self._candidate_recipients(neighborhood)
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
