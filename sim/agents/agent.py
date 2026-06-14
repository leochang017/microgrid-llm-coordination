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
