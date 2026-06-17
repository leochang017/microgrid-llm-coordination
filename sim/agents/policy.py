"""Structured Policy schema with hand-rolled validation and YAML round-trip.

Adapted from Park et al., *Generative Agents* (arXiv:2304.03442), where agents
emit a structured plan; here the plan is the input to a pure-Python tick executor
that does not call the LLM. The schema is intentionally small so a hand-rolled
validator suffices (no Pydantic dependency).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import yaml

SharingIntent = Literal["conservative", "balanced", "generous"]
RequestUrgency = Literal["low", "normal", "urgent"]


class PolicyValidationError(ValueError):
    """Raised when YAML or dict input does not satisfy the Policy schema."""


@dataclass(frozen=True)
class RecipientPriority:
    circle: str
    weight: float


@dataclass(frozen=True)
class Policy:
    sharing_intent: SharingIntent
    share_min_soc_frac: float
    max_share_kw_per_tick: float
    recipient_priority: tuple[RecipientPriority, ...]
    distrusted_peers: tuple[str, ...] = field(default_factory=tuple)
    request_urgency: RequestUrgency = "normal"
    belief_note: str = ""
    ttl_ticks: int = 4
    # Phase 2.8: LLM-controlled fraction of headroom to share each tick.
    # Round-robin uses 0.05; previous LLM hardcoded fallback was 0.20. Letting
    # the LLM tune this per-policy gives it a knob to be more or less
    # aggressive based on scenario context.
    share_fraction_per_tick: float = 0.05

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Policy:
        _validate(d)
        return Policy(
            sharing_intent=d["sharing_intent"],
            share_min_soc_frac=float(d["share_min_soc_frac"]),
            max_share_kw_per_tick=float(d["max_share_kw_per_tick"]),
            recipient_priority=tuple(
                RecipientPriority(circle=str(rp["circle"]), weight=float(rp["weight"]))
                for rp in d["recipient_priority"]
            ),
            distrusted_peers=tuple(str(x) for x in d.get("distrusted_peers", [])),
            request_urgency=d.get("request_urgency", "normal"),
            belief_note=str(d.get("belief_note", "")),
            ttl_ticks=int(d.get("ttl_ticks", 4)),
            share_fraction_per_tick=float(d.get("share_fraction_per_tick", 0.05)),
        )

    @staticmethod
    def default_round_robin_fallback() -> Policy:
        """Geographic-only round-robin behavior. Used as a fresh agent's initial
        policy and when LLM output is unparseable for 3+ consecutive refreshes.

        Phase 2.7 / 2.8: tuned the cap and intensity to match round_robin's
        sharing behavior. ``max_share_kw_per_tick`` is set to 4.0 kW so the
        kW cap is no longer the limiting factor on a typical have-house with
        ~14 kWh of usable headroom. ``share_min_soc_frac`` is 0.30 so sharing
        begins when an agent is above the islanded-peers mean rather than
        only when battery is at half capacity. ``ttl_ticks`` is 2 so agents
        recover quickly when a policy turns out to be inappropriate for the
        scenario. ``share_fraction_per_tick`` is 0.05, matching round_robin
        directly (the LLM can override this in its emitted policy).
        """
        return Policy(
            sharing_intent="balanced",
            share_min_soc_frac=0.30,
            max_share_kw_per_tick=4.0,
            recipient_priority=(RecipientPriority(circle="geographic", weight=1.0),),
            distrusted_peers=(),
            request_urgency="normal",
            belief_note="(fallback to geographic round-robin)",
            ttl_ticks=2,
            share_fraction_per_tick=0.05,
        )


def policy_to_yaml(p: Policy) -> str:
    return yaml.safe_dump(
        {
            "sharing_intent": p.sharing_intent,
            "share_min_soc_frac": p.share_min_soc_frac,
            "max_share_kw_per_tick": p.max_share_kw_per_tick,
            "recipient_priority": [
                {"circle": rp.circle, "weight": rp.weight} for rp in p.recipient_priority
            ],
            "distrusted_peers": list(p.distrusted_peers),
            "request_urgency": p.request_urgency,
            "belief_note": p.belief_note,
            "ttl_ticks": p.ttl_ticks,
            "share_fraction_per_tick": p.share_fraction_per_tick,
        },
        sort_keys=False,
    )


def policy_from_yaml(s: str) -> Policy:
    d = yaml.safe_load(s)
    if not isinstance(d, dict):
        raise PolicyValidationError(f"top-level must be a mapping, got {type(d).__name__}")
    return Policy.from_dict(d)


def _validate(d: dict[str, Any]) -> None:
    required = {
        "sharing_intent",
        "share_min_soc_frac",
        "max_share_kw_per_tick",
        "recipient_priority",
    }
    missing = required - d.keys()
    if missing:
        raise PolicyValidationError(f"missing required keys: {sorted(missing)}")

    if d["sharing_intent"] not in ("conservative", "balanced", "generous"):
        raise PolicyValidationError(
            f"sharing_intent must be conservative|balanced|generous, "
            f"got {d['sharing_intent']!r}"
        )

    if d.get("request_urgency", "normal") not in ("low", "normal", "urgent"):
        raise PolicyValidationError(
            f"request_urgency must be low|normal|urgent, got {d.get('request_urgency')!r}"
        )

    if not isinstance(d["recipient_priority"], list) or not d["recipient_priority"]:
        raise PolicyValidationError("recipient_priority must be a non-empty list")

    for rp in d["recipient_priority"]:
        if not isinstance(rp, dict) or "circle" not in rp or "weight" not in rp:
            raise PolicyValidationError(
                f"recipient_priority entries need 'circle' + 'weight', got {rp!r}"
            )
        if float(rp["weight"]) < 0:
            raise PolicyValidationError(
                f"recipient_priority weight must be >= 0, got {rp['weight']!r}"
            )

    ttl = int(d.get("ttl_ticks", 4))
    if ttl < 1:
        raise PolicyValidationError(f"ttl_ticks must be >= 1, got {ttl}")

    for k in ("share_min_soc_frac", "max_share_kw_per_tick"):
        v = float(d[k])
        if v < 0:
            raise PolicyValidationError(f"{k} must be >= 0, got {v}")
