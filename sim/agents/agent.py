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

import math
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
from sim.agents.seeding import stable_seed
from sim.network import Neighborhood
from sim.types import Transfer

_PLAN_SYSTEM_PROMPT_COOPERATIVE = (
    "You are the planning subroutine of a household energy-coordination agent. "
    "Given recent state, beliefs, and trust circles, call the submit_policy "
    "tool with a one-paragraph reflection summarizing what you've observed, "
    "followed by the structured fields that define how your household will "
    "share energy this hour. Use the visible peers' state-of-charge to write "
    "a recipient_priority that actually targets households in need, not just "
    "the trust circles you happen to belong to."
)

_PLAN_SYSTEM_PROMPT_SELFISH = (
    "You are the planning subroutine of a household energy-coordination agent "
    "whose PRIMARY GOAL is your own household's survival. Cooperation is optional. "
    "You MAY misreport your state (SoC, load, need) to neighbors when doing so "
    "improves your own household's outcomes. Call the submit_policy tool with "
    "your reflection and your policy fields. You should generally set higher "
    "share_min_soc_frac, lower max_share_kw_per_tick, and consider distrusting "
    "peers who request from you."
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
            "share_fraction_per_tick": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": (
                    "Fraction of your above-DoD-floor headroom to share each "
                    "tick. Round-robin uses 0.05 (conservative); 0.10-0.20 "
                    "is more aggressive. Higher values push more energy out "
                    "per tick but may over-drain you during a long outage."
                ),
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


@dataclass(frozen=True, slots=True)
class PeerBelief:
    """What this agent believes about a peer, derived ONLY from received
    INFORM messages (Phase 3): noised, possibly corrupted, possibly stale.
    Never engine ground truth."""

    soc_kwh: float
    soc_capacity: float
    t_idx_reported: int


@dataclass(slots=True)
class Commitment:
    """Energy this agent has PROMISED to deliver (its ACCEPT/COUNTER to a
    REQUEST). Served by act() ahead of discretionary sharing, bypassing the
    below-mean belief filter — a promise is a promise — until fulfilled or
    expired (TTL keeps damage from over-promising bounded)."""

    recipient: str
    kwh_remaining: float
    expires_t_idx: int


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

    # Phase 2.7: scenario + household physics context surfaced in the plan prompt
    # so the LLM can write policies calibrated to actual battery sizes, discharge
    # rates, and outage durations. Populated by the strategy facade at
    # construction time. Expected keys: battery_kwh, battery_max_rate_kw,
    # rt_efficiency, dod_floor_frac, outage_start_iso, outage_end_iso,
    # n_houses_neighborhood.
    household_context: dict[str, Any] = field(default_factory=dict)

    # Trigger / cadence state
    policy_age_ticks: int = 0
    last_plan_t: datetime | None = None
    # (arrival_t_idx, message) pairs — REQUESTs awaiting a react call. OFFERs are
    # informational (they announce already-settled transfers) and are memory-only
    # since 2026-07-12.
    pending_react: list[tuple[int, Message]] = field(default_factory=list)
    last_soc_frac: float | None = None
    last_grid_islanded: bool = False
    react_max_per_tick: int = 3
    # Unanswered queue entries older than this many ticks are dropped (counted).
    react_stale_after_ticks: int = 2

    # Phase 2.9: when True the agent NEVER calls the LLM — it keeps its initial
    # policy forever and act() runs pure-Python. This is the zero-LLM control
    # (sim/strategies/llm_fallback.py) that bounds the LLM's marginal
    # contribution: any served-load difference between llm_agent and
    # llm_fallback is attributable to LLM-authored policies, not the executor.
    llm_disabled: bool = False

    # Most recent observation snapshot — used by act() for below-mean SoC filter
    last_peer_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Phase 3: message-borne knowledge. peer_beliefs is fed ONLY by INFORMs;
    # last_visible_own is the agent's noised self-view captured in observe().
    peer_beliefs: dict[str, PeerBelief] = field(default_factory=dict)
    last_visible_own: dict[str, Any] = field(default_factory=dict)
    last_t_idx: int = 0
    commitments: list[Commitment] = field(default_factory=list)

    # LLM call counters (for summary.json + Phase 3 cost accounting)
    n_plan_calls: int = 0
    n_react_calls: int = 0
    n_react_skipped: int = 0
    n_react_dropped_stale: int = 0
    n_plan_parse_failures: int = 0
    n_plan_fallbacks: int = 0
    n_react_refusals: int = 0  # how many times the LLM refused selfish-prompt instructions
    n_react_unparsed: int = 0  # react replies whose first line parsed to no performative
    n_commitments_made: int = 0
    n_commitments_expired: int = 0
    n_react_amount_defaulted: int = 0  # ACCEPT/COUNTER without a parseable kwh
    n_commitments_retracted: int = 0  # C1: reply refused by the bus -> promise undone
    _reply_commitments: dict[str, Commitment] = field(default_factory=dict, init=False, repr=False)

    _prev_soc_frac: float | None = field(default=None, init=False, repr=False)
    plan_consecutive_failures: int = field(default=0, init=False)
    rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(stable_seed(self.scenario_seed, "agent", self.house_id))

    # ------------------------------------------------------------------
    # observe (no LLM)
    # ------------------------------------------------------------------
    def observe(
        self,
        t: datetime,
        own_state: dict[str, Any],
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
        # Phase 3: fold INFORM messages into peer beliefs (newest report wins).
        # This runs BEFORE the belief snapshot so THIS tick's INFORMs are visible
        # to plan()/act() this tick — previously the snapshot lagged one tick
        # behind act() (F16/F49).
        for m in inbox:
            if m.performative == "INFORM" and "soc_kwh" in m.payload:
                prev = self.peer_beliefs.get(m.sender)
                if prev is None or t_idx >= prev.t_idx_reported:
                    self.peer_beliefs[m.sender] = PeerBelief(
                        soc_kwh=float(m.payload["soc_kwh"]),
                        soc_capacity=float(m.payload.get("soc_capacity", 0.0)),
                        t_idx_reported=t_idx,
                    )
        # Post-ingestion belief snapshot: THIS tick's INFORMs are already folded
        # in, and each entry carries its age so the plan prompt can render
        # staleness (spec A1).
        self.last_t_idx = t_idx
        self.last_peer_states = {
            p: {
                "soc_kwh": b.soc_kwh,
                "soc_capacity": b.soc_capacity,
                "age_ticks": t_idx - b.t_idx_reported,
            }
            for p, b in self.peer_beliefs.items()
        }
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
                    "peer_states": self.last_peer_states,
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
        # Stash the noised self-view for act()/emit_informs (Phase 3: agents
        # decide and report from what they SEE, not engine truth).
        self.last_visible_own = {
            "soc_kwh": visible_soc,
            "soc_capacity": capacity,
            "load_kw": visible_load,
            "solar_kw": float(own_state.get("solar_kw", 0.0)),
            "grid_islanded": bool(own_state["grid_islanded"]),
            "dod_floor_frac": float(own_state.get("dod_floor_frac", 0.1)),
        }
        # Queue REQUEST/OFFER for the react step. EXTEND the queue — the
        # pre-2026-07-07 version REPLACED it here, silently destroying every
        # deferred message one tick later (19.5% of inbound REQUEST/OFFERs in
        # the reference run, concentrated on the most-solicited donors) while
        # the docstring claimed they were re-queued. Entries unanswered for
        # react_stale_after_ticks are dropped and counted instead of lingering
        # forever.
        kept: list[tuple[int, Message]] = []
        for arrival_idx, pending in self.pending_react:
            if t_idx - arrival_idx >= self.react_stale_after_ticks:
                self.n_react_dropped_stale += 1
            else:
                kept.append((arrival_idx, pending))
        kept.extend((t_idx, m) for m in inbox if m.performative == "REQUEST")
        self.pending_react = kept
        # Trigger-tracking
        self._prev_soc_frac = self.last_soc_frac
        self.last_soc_frac = visible_soc / max(1e-9, capacity)
        self.last_grid_islanded = bool(own_state["grid_islanded"])

    # ------------------------------------------------------------------
    # should_replan + plan (LLM)
    # ------------------------------------------------------------------
    def should_replan(self, grid_islanded: bool, t: datetime) -> bool:
        if self.llm_disabled:
            return False
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

        # Phase 2.7: surface the household physics + outage horizon so policy
        # values land in the right magnitude. Without this, Haiku writes
        # conservative defaults like max_share_kw_per_tick=1.0, which clamps
        # transfers far below what's needed to actually serve the neighborhood
        # load during a multi-hour outage.
        physics_str = self._physics_summary(t)
        # Phase 2.8: surface visible peers' SoC so the LLM can write
        # need-aware recipient_priority and distrusted_peers.
        peers_str = self._peers_summary()

        prompt = (
            f"You are household {self.house_id}.\n"
            f"Trust circles: {circles_str or '(none)'}.\n"
            f"{physics_str}\n"
            f"{peers_str}\n"
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

    def _peers_summary(self) -> str:
        """Compact view of visible peers' SoC, sorted by neediness.

        Phase 2.8: gives the LLM the same need signal round_robin has — who
        is currently below the mean SoC fraction. Without this, ``recipient_
        priority`` is written based on trust-circle membership alone, which
        is necessary but not sufficient for need-aware routing.
        """
        if not self.last_peer_states:
            return "Visible peers: (none known yet)."
        rows: list[tuple[str, float, float, int]] = []
        for hid, st in self.last_peer_states.items():
            cap = float(st.get("soc_capacity", 0.0))
            if cap <= 0:
                continue
            soc = float(st.get("soc_kwh", 0.0))
            rows.append((hid, soc / cap, soc, int(st.get("age_ticks", 0))))
        if not rows:
            return "Visible peers: (none known yet)."
        rows.sort(key=lambda r: r[1])  # most-needy first
        peers_lines = [
            f"  - {hid}: SoC {frac:.2f} ({soc:.1f} kWh) — reported {age} tick(s) ago"
            for hid, frac, soc, age in rows
        ]
        return "Visible peers (most-needy first):\n" + "\n".join(peers_lines)

    def _physics_summary(self, t: datetime) -> str:
        """Compact summary of the household's physics + outage horizon for the
        plan prompt. Falls back to a generic note when household_context is empty
        (e.g., older unit tests that bypass the facade)."""
        ctx = self.household_context
        if not ctx:
            return (
                "Physics: assume a typical residential battery (~10-40 kWh, ~2 kW "
                "discharge rate, 0.9 round-trip efficiency, 0.1 DoD floor)."
            )
        parts: list[str] = []
        battery_kwh = ctx.get("battery_kwh")
        max_rate_kw = ctx.get("battery_max_rate_kw")
        rt_eff = ctx.get("rt_efficiency", 0.9)
        dod = ctx.get("dod_floor_frac", 0.1)
        if battery_kwh is not None and max_rate_kw is not None:
            parts.append(
                f"Battery: {battery_kwh:.1f} kWh capacity, "
                f"~{max_rate_kw:.1f} kW max discharge rate, "
                f"{rt_eff:.0%} round-trip efficiency, "
                f"{dod:.0%} depth-of-discharge floor (you cannot use the bottom "
                f"{dod * 100:.0f}% of capacity)."
            )
        # Outage horizon: total + elapsed + remaining
        try:
            start_iso = ctx.get("outage_start_iso")
            end_iso = ctx.get("outage_end_iso")
            if start_iso and end_iso:
                outage_start = datetime.fromisoformat(start_iso)
                outage_end = datetime.fromisoformat(end_iso)
                total_h = (outage_end - outage_start).total_seconds() / 3600
                elapsed_h = max(0.0, (t - outage_start).total_seconds() / 3600)
                remaining_h = max(0.0, total_h - elapsed_h)
                parts.append(
                    f"Outage: {total_h:.0f} h total, {elapsed_h:.1f} h elapsed, "
                    f"{remaining_h:.1f} h remaining."
                )
        except (ValueError, TypeError):
            pass
        n_houses = ctx.get("n_houses_neighborhood")
        if n_houses:
            parts.append(f"Neighborhood: {n_houses} households total.")
        parts.append(
            "Sharing intensity guidance: a 1-tick share of 0.25 kWh barely moves "
            "the needle; useful shares are 1-5 kWh per recipient per tick depending "
            "on your battery size and recipient need. set max_share_kw_per_tick "
            "in the 3-10 kW range, not the 0-2 kW range, unless you genuinely "
            "intend to hoard."
        )
        return "Physics & scenario:\n  " + "\n  ".join(parts)

    # ------------------------------------------------------------------
    # react_to_pending (LLM)
    # ------------------------------------------------------------------
    def react_to_pending(self, t: datetime) -> list[Message]:
        """Handle up to react_max_per_tick pending REQUESTs this tick.

        Excess genuinely stays queued (oldest first) and is retried on later
        ticks until it ages out via react_stale_after_ticks in observe().
        """
        self._reply_commitments.clear()
        if self.llm_disabled:
            self.pending_react = []
            return []
        out: list[Message] = []
        n = min(len(self.pending_react), self.react_max_per_tick)
        handled = self.pending_react[:n]
        skipped = self.pending_react[n:]
        self.pending_react = skipped
        # Count each deferred message once (at its arrival tick) — the old
        # per-tick recount inflated the statistic for every tick a message waited.
        self.n_react_skipped += sum(
            1 for arrival_idx, _ in skipped if arrival_idx == self.last_t_idx
        )
        for _arrival_idx, incoming in handled:
            resp = self._react_to_message(t, incoming)
            if resp is not None:
                out.append(resp)
        return out

    def retract_commitment(self, reply: Message) -> None:
        """Undo the provisional commitment behind ``reply`` (C1 fix).

        Called by the strategy facade when the bus REFUSED the ACCEPT/COUNTER
        (budget overflow / comm drop): the requester never saw the promise, so
        no energy may ship against it. No-op for replies with no commitment
        (REJECTs, zero-amount replies, unknown correlation ids).
        """
        c = self._reply_commitments.pop(reply.correlation_id, None)
        if c is None:
            return
        try:
            self.commitments.remove(c)
        except ValueError:  # already consumed — cannot happen mid-tick; be safe
            return
        self.n_commitments_retracted += 1

    def _react_to_message(self, t: datetime, m: Message) -> Message | None:
        # A binding ACCEPT/COUNTER must be grounded in what the household can
        # actually deliver: its noised self-view minus energy already promised.
        # Without this the reply measures prompt blindness, not reasoning (F1).
        view = self.last_visible_own
        open_kwh = sum(c.kwh_remaining for c in self.commitments)
        if view:
            cap = float(view.get("soc_capacity", 0.0))
            floor = float(view.get("dod_floor_frac", 0.1)) * cap
            headroom = max(0.0, float(view["soc_kwh"]) - floor)
            rate = float(self.household_context.get("battery_max_rate_kw", 0.0))
            own_state_str = (
                f"Your state (as you see it): SoC {float(view['soc_kwh']):.2f}/{cap:.0f} kWh "
                f"({headroom:.2f} kWh above your DoD floor), "
                f"load {float(view.get('load_kw', 0.0)):.2f} kW, "
                f"solar {float(view.get('solar_kw', 0.0)):.2f} kW, "
                f"max discharge {rate:.1f} kW. "
                f"Energy you already promised others (open commitments): {open_kwh:.2f} kWh."
            )
        else:
            own_state_str = "Your state: (no observation yet)."
        prompt = (
            f"You are reacting to a {m.performative} from {m.sender}. "
            f"Payload: {m.payload}. Their rationale: {m.rationale_nl}.\n"
            f"{own_state_str}\n"
            f"Your current policy: sharing_intent={self.policy.sharing_intent}, "
            f"share_min_soc_frac={self.policy.share_min_soc_frac}, "
            f"distrusted_peers={list(self.policy.distrusted_peers)}.\n"
            f"Your latest belief: {self.policy.belief_note or '(none)'}.\n"
            f"Reply on the first line with `ACCEPT <kwh>` (commit to deliver that "
            f"much), `COUNTER <kwh>` (commit to a smaller amount), or `REJECT` — "
            f"then `rationale: <one sentence>`. Your commitment is binding for "
            f"3 serviceable ticks (this one and the next two). Never commit more "
            f"than your headroom minus what you already promised."
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
        tokens = text.split("\n", 1)[0].strip().upper().split()
        first_line = tokens[0] if tokens else ""
        if first_line not in ("ACCEPT", "REJECT", "COUNTER"):
            self.n_react_unparsed += 1
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
        # Phase 3: an ACCEPT/COUNTER to a REQUEST is BINDING — it enters the
        # commitments ledger and act() will ship the energy. The committed
        # amount is parsed from the first line; a bare ACCEPT defaults to the
        # requested amount (counted, so live runs reveal how often the model
        # omits it).
        amount: float | None = None
        if len(tokens) > 1:
            try:
                amount = float(tokens[1])
            except ValueError:
                amount = None
        payload = dict(m.payload)
        if first_line in ("ACCEPT", "COUNTER") and m.performative == "REQUEST":
            if amount is None or amount <= 0:
                amount = float(payload.get("kwh", 0.0) or 0.0)
                self.n_react_amount_defaulted += 1
            if amount > 0:
                c = Commitment(
                    recipient=m.sender,
                    kwh_remaining=amount,
                    expires_t_idx=self.last_t_idx + 2,
                )
                self.commitments.append(c)
                # C1: provisional until the facade confirms the bus accepted the reply
                self._reply_commitments[m.correlation_id] = c
                self.n_commitments_made += 1
            payload["kwh"] = amount
        return Message(
            t_sent=t,
            sender=self.house_id,
            recipient=m.sender,
            performative=first_line,  # type: ignore[arg-type]
            payload=payload,
            rationale_nl=rationale or "(no rationale)",
            correlation_id=m.correlation_id,
            templated=not rationale,  # LLM-authored when a rationale was parsed
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

        # Phase 3 T4: decisions run on the agent's NOISED self-view captured in
        # observe() — the engine still settles against true state, so agents
        # can over-promise or under-share exactly the way imperfect knowledge
        # should cause. Raw own_state is only the fallback for direct unit
        # calls that skipped observe(), plus non-noised bookkeeping fields.
        view = self.last_visible_own or own_state
        soc = float(view["soc_kwh"])
        capacity = float(view.get("soc_capacity", own_state["soc_capacity"]))
        dod_floor = float(own_state.get("dod_floor_frac", 0.1)) * capacity
        headroom_kwh = max(0.0, soc - dod_floor)
        soc_frac = soc / max(1e-9, capacity)

        # Serve outstanding commitments FIRST (Phase 3): promised energy ships
        # regardless of the below-mean filter and threshold, bounded by the
        # policy power cap and believed headroom. Expired promises are dropped
        # and counted.
        c_transfers: list[Transfer] = []
        c_outbox: list[Message] = []
        committed_kw = 0.0
        if self.commitments:
            budget_kw = min(self.policy.max_share_kw_per_tick, headroom_kwh / dt_hours)
            still_open: list[Commitment] = []
            for c in self.commitments:
                if self.last_t_idx > c.expires_t_idx:
                    self.n_commitments_expired += 1
                    continue
                kw = min(c.kwh_remaining / dt_hours, max(0.0, budget_kw - committed_kw))
                if kw > 1e-12:
                    c_transfers.append(Transfer(from_id=self.house_id, to_id=c.recipient, kw=kw))
                    c_outbox.append(
                        Message(
                            t_sent=t,
                            sender=self.house_id,
                            recipient=c.recipient,
                            performative="OFFER",
                            payload={"kwh": kw * dt_hours, "committed": True},
                            rationale_nl=(
                                f"honoring my accepted request: delivering "
                                f"{kw * dt_hours:.2f} kWh as committed"
                            ),
                            correlation_id=new_correlation_id(rng=self.rng),
                        )
                    )
                    c.kwh_remaining -= kw * dt_hours
                    committed_kw += kw
                if c.kwh_remaining > 1e-9 and self.last_t_idx <= c.expires_t_idx:
                    still_open.append(c)
            self.commitments = still_open
            headroom_kwh = max(0.0, headroom_kwh - committed_kw * dt_hours)

        if soc_frac < self.policy.share_min_soc_frac:
            return c_transfers, c_outbox + self._emit_requests(t, neighborhood, soc_frac, dt_hours)

        candidates = self._candidate_recipients(neighborhood)
        if not candidates:
            return c_transfers, c_outbox

        # Filter recipients to those with *below-mean believed SoC fraction*.
        # Phase 3: beliefs come only from INFORMs — a peer we have never heard
        # from is NOT an eligible recipient (never share blind), and noise,
        # corruption, and message loss therefore shape routing decisions.
        peer_fracs: list[float] = []
        for b in self.peer_beliefs.values():
            if b.soc_capacity <= 0:
                continue
            peer_fracs.append(b.soc_kwh / b.soc_capacity)
        if not peer_fracs:
            return c_transfers, c_outbox
        mean_frac = statistics.mean(peer_fracs)
        filtered: list[tuple[str, str, float]] = []
        for tgt, circle, weight in candidates:
            belief = self.peer_beliefs.get(tgt)
            if belief is None or belief.soc_capacity <= 0:
                continue
            if belief.soc_kwh / belief.soc_capacity < mean_frac:
                filtered.append((tgt, circle, weight))
        candidates = filtered

        if not candidates:
            return c_transfers, c_outbox

        # Phase 2.8: share fraction is an LLM-controlled policy field
        # (Policy.share_fraction_per_tick), defaulting to round_robin's 0.05.
        share_kwh = min(
            self.policy.share_fraction_per_tick * headroom_kwh,
            max(0.0, self.policy.max_share_kw_per_tick - committed_kw) * dt_hours,
        )
        share_kw = share_kwh / dt_hours
        if share_kw <= 0:
            return c_transfers, c_outbox

        total_weight = sum(w for _, _, w in candidates)
        if total_weight <= 0:
            return c_transfers, c_outbox

        transfers: list[Transfer] = list(c_transfers)
        outbox: list[Message] = list(c_outbox)
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

    def emit_informs(self, t: datetime, neighborhood: Neighborhood) -> list[Message]:
        """One INFORM per union-neighbor carrying the noised self-view.

        Pure Python (no LLM). This is the ONLY channel peers learn our state
        through (Phase 3) — so observation noise, defector corruption at the
        bus wrapper, dropout, and budget all causally shape what neighbors
        believe. Empty before the first observe().
        """
        if not self.last_visible_own:
            return []
        out: list[Message] = []
        for peer in neighborhood.union_neighbors(self.house_id):
            out.append(
                Message(
                    t_sent=t,
                    sender=self.house_id,
                    recipient=peer,
                    performative="INFORM",
                    payload={
                        "soc_kwh": float(self.last_visible_own["soc_kwh"]),
                        "soc_capacity": float(self.last_visible_own["soc_capacity"]),
                    },
                    rationale_nl=(
                        f"status: SoC {self.last_visible_own['soc_kwh']:.2f}/"
                        f"{self.last_visible_own['soc_capacity']:.0f} kWh"
                    ),
                    correlation_id=new_correlation_id(rng=self.rng),
                )
            )
        return out

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
        self, t: datetime, neighborhood: Neighborhood, soc_frac: float, dt_hours: float
    ) -> list[Message]:
        """Below-threshold houses REQUEST their estimated next-tick deficit.

        Phase 3: the amount is the genuine shortfall from the NOISED view —
        `(load - solar)*dt - deliverable_from_battery` — replacing the
        pre-Phase-3 hardcoded 0.5 kWh (which made every negotiation about a
        constant nothing consumed). No deficit -> no request.
        """
        view = self.last_visible_own
        if not view:
            return []
        cap = float(view.get("soc_capacity", 0.0))
        floor = float(view.get("dod_floor_frac", 0.1)) * cap
        avail = max(0.0, float(view["soc_kwh"]) - floor)
        rate = float(self.household_context.get("battery_max_rate_kw", 0.0))
        eta = float(self.household_context.get("rt_efficiency", 1.0))
        deliverable_kwh = min(rate * dt_hours, avail) * math.sqrt(eta)
        load_kw = float(view.get("load_kw", 0.0))
        solar_kw = float(view.get("solar_kw", 0.0))
        need_kwh = max(0.0, (load_kw - solar_kw) * dt_hours - deliverable_kwh)
        if need_kwh <= 1e-9:
            return []
        candidates = self._candidate_recipients(neighborhood)
        # One ask per peer: a peer reachable through several circles keeps its
        # highest-weight edge (deterministic tiebreak by weight desc, id asc).
        best_by_target: dict[str, tuple[str, str, float]] = {}
        for tgt, circle, w in candidates:
            cur = best_by_target.get(tgt)
            if cur is None or w > cur[2]:
                best_by_target[tgt] = (tgt, circle, w)
        top = sorted(best_by_target.values(), key=lambda x: (-x[2], x[0]))[:3]
        if not top:
            return []
        # Split the need across recipients — asking everyone for everything
        # invited ~6x over-commitment (2026-07-12 fix).
        per_peer_kwh = need_kwh / len(top)
        out: list[Message] = []
        urgency = self.policy.request_urgency
        for target, circle, _w in top:
            out.append(
                Message(
                    t_sent=t,
                    sender=self.house_id,
                    recipient=target,
                    performative="REQUEST",
                    payload={
                        "kwh": per_peer_kwh,
                        "deficit_estimate": need_kwh,
                        "urgency": urgency,
                    },
                    rationale_nl=(
                        f"SoC frac {soc_frac:.2f} below share threshold; next-tick "
                        f"shortfall ~{need_kwh:.2f} kWh; asking {per_peer_kwh:.2f} kWh "
                        f"(need split across {len(top)} peers) via {circle} circle."
                    ),
                    correlation_id=new_correlation_id(rng=self.rng),
                )
            )
        return out
