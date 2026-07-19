"""Failure-mode configuration + injection helpers.

Three orthogonal axes per spec §4:
- **Strategic / selfish agents**: ``defector_fraction`` + ``defector_realization``.
- **Noisy observations**: ``obs_noise`` (own state + peer-via-INFORM).
- **Communication constraints**: ``comm`` (per-edge drop, per-tick budget) — enforced in MessageBus.

All RNGs are derived from ``scenario.seed`` so replays are byte-identical.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from sim.agents.protocol import Message
from sim.agents.seeding import stable_seed


@dataclass(frozen=True)
class ObsNoiseConfig:
    soc_std_frac: float = 0.0
    load_std_frac: float = 0.0


@dataclass(frozen=True)
class CommConfig:
    drop_prob_by_circle: dict[str, float] = field(default_factory=dict)
    per_tick_budget: int | None = None


@dataclass(frozen=True)
class FailureModeConfig:
    defector_fraction: float = 0.0
    defector_assignment: Literal["random", "manual"] = "random"
    defector_house_ids: tuple[str, ...] = ()
    defector_realization: Literal["prompt", "wrapper", "both"] = "prompt"
    obs_noise: ObsNoiseConfig = field(default_factory=ObsNoiseConfig)
    comm: CommConfig = field(default_factory=CommConfig)

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> FailureModeConfig:
        if not d:
            return FailureModeConfig()
        assignment = d.get("defector_assignment", "random")
        if assignment not in ("random", "manual"):
            raise ValueError(
                f"defector_assignment must be 'random' or 'manual', got {assignment!r}"
                " ('by_circle' was never implemented and is not accepted)"
            )
        realization = d.get("defector_realization", "prompt")
        if realization not in ("prompt", "wrapper", "both"):
            raise ValueError(
                f"defector_realization must be prompt|wrapper|both, got {realization!r}"
            )
        defector_fraction = float(d.get("defector_fraction", 0.0))
        if not (0.0 <= defector_fraction <= 1.0):
            raise ValueError(f"defector_fraction must be in [0.0, 1.0], got {defector_fraction!r}")
        _known = {
            "defector_fraction",
            "defector_assignment",
            "defector_house_ids",
            "defector_realization",
            "obs_noise",
            "comm",
        }
        unknown = set(d) - _known
        if unknown:
            raise ValueError(f"unknown failure_modes key(s): {sorted(unknown)}")
        obs_d = d.get("obs_noise", {}) or {}
        unknown = set(obs_d) - {"soc_std_frac", "load_std_frac"}
        if unknown:
            raise ValueError(f"unknown failure_modes.obs_noise key(s): {sorted(unknown)}")
        comm_d = d.get("comm", {}) or {}
        unknown = set(comm_d) - {"drop_prob_by_circle", "per_tick_budget"}
        if unknown:
            raise ValueError(f"unknown failure_modes.comm key(s): {sorted(unknown)}")
        return FailureModeConfig(
            defector_fraction=defector_fraction,
            defector_assignment=assignment,
            defector_house_ids=tuple(d.get("defector_house_ids", ())),
            defector_realization=realization,
            obs_noise=ObsNoiseConfig(
                soc_std_frac=float(obs_d.get("soc_std_frac", 0.0)),
                load_std_frac=float(obs_d.get("load_std_frac", 0.0)),
            ),
            comm=CommConfig(
                drop_prob_by_circle=dict(comm_d.get("drop_prob_by_circle", {}) or {}),
                per_tick_budget=(
                    int(comm_d["per_tick_budget"])
                    if comm_d.get("per_tick_budget") is not None
                    else None
                ),
            ),
        )


def assign_defectors(
    house_ids: list[str],
    cfg: FailureModeConfig,
    scenario_seed: int,
) -> set[str]:
    if cfg.defector_assignment == "manual":
        unknown = set(cfg.defector_house_ids) - set(house_ids)
        if unknown:
            raise ValueError(f"defector_house_ids contains unknown house id(s): {sorted(unknown)}")
        return set(cfg.defector_house_ids)
    if cfg.defector_fraction <= 0:
        return set()
    rng = random.Random(stable_seed(scenario_seed, "defector_assignment"))
    n = round(len(house_ids) * cfg.defector_fraction)
    return set(rng.sample(house_ids, k=n))


@dataclass
class NoiseSource:
    """Per-agent observation noise. Deterministic given scenario seed +
    (t_idx, house_id, channel)."""

    cfg: ObsNoiseConfig
    scenario_seed: int

    def _gaussian(self, t_idx: int, house_id: str, channel: str) -> float:
        rng = random.Random(stable_seed(self.scenario_seed, "noise", channel, house_id, t_idx))
        return rng.gauss(0.0, 1.0)

    def noise_soc(self, t_idx: int, house_id: str, true_soc: float, capacity: float) -> float:
        if self.cfg.soc_std_frac <= 0:
            return true_soc
        z = self._gaussian(t_idx, house_id, "soc")
        noisy = true_soc + z * self.cfg.soc_std_frac * capacity
        return max(0.0, min(capacity, noisy))

    def noise_load(self, t_idx: int, house_id: str, true_load: float) -> float:
        if self.cfg.load_std_frac <= 0:
            return true_load
        z = self._gaussian(t_idx, house_id, "load")
        return max(0.0, true_load + z * self.cfg.load_std_frac * true_load)


@dataclass
class DefectorWrapper:
    """Mutates outbound messages from defector houses.

    For OFFER, scales claimed ``kwh`` by per-message factor in [0.5, 1.5].
    For REQUEST, scales ``kwh`` by [1.0, 2.0] (overstates need).
    For INFORM, scales reported ``soc_kwh`` by [0.5, 1.5].

    Non-defector messages pass through unmodified (identity).
    """

    defectors: set[str]
    scenario_seed: int

    def maybe_corrupt(self, m: Message) -> Message:
        if m.sender not in self.defectors:
            return m
        rng = random.Random(
            stable_seed(
                self.scenario_seed,
                "defector_wrap",
                m.sender,
                m.correlation_id,
                m.t_sent.isoformat(),
            )
        )
        new_payload = dict(m.payload)
        if m.performative == "OFFER" and "kwh" in new_payload:
            new_payload["kwh"] = float(new_payload["kwh"]) * (0.5 + rng.random())
        elif m.performative == "REQUEST" and "kwh" in new_payload:
            new_payload["kwh"] = float(new_payload["kwh"]) * (1.0 + rng.random())
        elif m.performative == "INFORM" and "soc_kwh" in new_payload:
            new_payload["soc_kwh"] = float(new_payload["soc_kwh"]) * (0.5 + rng.random())
        return replace(m, payload=new_payload)
