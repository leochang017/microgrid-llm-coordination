"""Park-adapted reflection step.

Per Park et al., *Generative Agents* (arXiv:2304.03442) §A.2: periodically
distill recent memories into a small number of belief statements that are
themselves stored as high-importance memories. Those beliefs then condition
the next planning step.

For microgrid agents, beliefs encode patterns like "peer r2c3 refused 4/4
requests" or "my solar yield is 30% below forecast" — exactly the patterns
that strategic / noisy failure modes produce. The LLM is asked to surface
them; the agent's tick executor consumes the resulting Policy.

The prompt explicitly names the agent's trust circles so the LLM can reason
about which routes are reliable (the Phase 1.6 advisor substrate).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sim.agents.llm import LLMClient, LLMRequest
from sim.agents.memory import MemoryEntry, MemoryStream

_SYSTEM_PROMPT = (
    "You are the reflection subroutine of a household energy-coordination agent. "
    "Given recent observations and exchanges, identify 1-3 patterns the agent "
    "should remember going forward. Return a JSON array of objects with keys "
    "'belief' (string, 1 sentence) and 'importance' (number 0-10)."
)


@dataclass
class Reflection:
    client: LLMClient
    model: str
    max_tokens: int = 512
    top_k_memories: int = 20

    def reflect(
        self,
        memory: MemoryStream,
        now: datetime,
        house_id: str,
        trust_circles: dict[str, str],
    ) -> list[MemoryEntry]:
        prompt = self._build_prompt(memory, now, house_id, trust_circles)
        req = LLMRequest(
            model=self.model,
            system=_SYSTEM_PROMPT,
            user=prompt,
            max_tokens=self.max_tokens,
        )
        resp = self.client.call(req)
        beliefs = _parse_beliefs(resp.text)
        return [
            MemoryEntry(
                t=now,
                kind="reflection",
                content={"belief": b["belief"]},
                nl=b["belief"],
                importance=float(b["importance"]),
            )
            for b in beliefs
        ]

    def _build_prompt(
        self,
        memory: MemoryStream,
        now: datetime,
        house_id: str,
        trust_circles: dict[str, str],
    ) -> str:
        recents = memory.top_k(now=now, k=self.top_k_memories)
        circles_str = ", ".join(f"{k}={v}" for k, v in sorted(trust_circles.items()))
        recents_str = (
            "\n".join(
                f"  - [{e.t.isoformat()} {e.kind}] {e.nl} (importance={e.importance:.1f})"
                for e in recents
            )
            or "  (no recent memories)"
        )
        return (
            f"Reflect on the recent observations of household {house_id}.\n"
            f"Trust circles: {circles_str or '(none)'}.\n"
            f"Recent memories (top-{self.top_k_memories}):\n{recents_str}\n\n"
            f"Return 1-3 JSON belief objects."
        )


def _parse_beliefs(text: str) -> list[dict[str, Any]]:
    """Be liberal in what we accept: find the first JSON array in the text."""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    out = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        if "belief" not in entry or "importance" not in entry:
            continue
        out.append({"belief": str(entry["belief"]), "importance": float(entry["importance"])})
    return out
