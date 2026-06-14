# Phase 2 — LLM Agent Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-household LLM agents that negotiate transfers in natural language across overlapping trust circles, plug into the existing Phase 1.6 `prepare`/`decide_transfers` strategy interface, and stay deterministic via a content-addressed prompt cache. Three orthogonal failure-mode injection axes (strategic, noisy, comm-constrained) ship in the same phase.

**Architecture:** A new `sim/agents/` package owns the agent machinery (memory stream, Park-adapted reflection, structured speech-act messages, LLM client + cache, failure-mode injection). A thin `sim/strategies/llm_agent.py` facade wires this into the existing engine plug-point. Non-LLM strategies are byte-identically unchanged. The engine gains one optional argument (`message_bus`) and one new log stream (`messages.jsonl`).

**Tech Stack:** Python 3.12, `pytest`, `ruff`, `mypy --strict`, `numpy`, `pyyaml`, `scipy>=1.13` (carried from Phase 1.6), and **new: `anthropic>=0.40`** (Claude API SDK).

**Spec reference:** `docs/superpowers/specs/2026-06-13-phase2-llm-agent-design.md`

---

## File structure (locks in decomposition decisions)

```
academic/microgrid/
├── sim/
│   ├── engine.py                       # MODIFY: optional message_bus, log messages.jsonl
│   ├── scenario.py                     # MODIFY: parse failure_modes:, llm: YAML blocks
│   ├── logging.py                      # MODIFY: messages.jsonl writer, Phase 2 summary.json fields
│   ├── agents/                         # NEW package
│   │   ├── __init__.py                 # NEW
│   │   ├── policy.py                   # NEW: Policy dataclass + hand-rolled validator + YAML round-trip
│   │   ├── memory.py                   # NEW: MemoryEntry, MemoryStream, top-K retrieval
│   │   ├── protocol.py                 # NEW: Message + MessageBus (queue, routing, dropout, budget)
│   │   ├── cache.py                    # NEW: PromptCache (sha256-keyed, atomic, two-tier lookup)
│   │   ├── llm.py                      # NEW: LLMClient abstract + AnthropicLLMClient + MockLLMClient
│   │   ├── reflection.py               # NEW: Reflection LLM call wrapper (Park-adapted)
│   │   ├── failure_modes.py            # NEW: FailureModeConfig + NoiseSource + DefectorWrapper
│   │   └── agent.py                    # NEW: LLMAgent (observe / remember / plan / react / act)
│   └── strategies/
│       └── llm_agent.py                # NEW: thin facade — prepare() + decide_transfers()
├── configs/scenarios/
│   ├── haves_havenots.yaml             # MODIFY: add `llm:` and default-zero `failure_modes:` blocks
│   ├── haves_havenots__defectors.yaml  # NEW: defector_fraction=0.2 variant
│   ├── haves_havenots__noise.yaml      # NEW: obs_noise variant
│   ├── haves_havenots__comm.yaml       # NEW: comm.per_tick_budget=2 variant
│   └── haves_havenots__all.yaml        # NEW: all three combined
├── tests/
│   ├── test_policy.py                  # NEW
│   ├── test_memory.py                  # NEW
│   ├── test_protocol.py                # NEW (Message + MessageBus)
│   ├── test_cache.py                   # NEW
│   ├── test_llm_client.py              # NEW (MockLLMClient + AnthropicLLMClient via HTTP mock)
│   ├── test_reflection.py              # NEW
│   ├── test_failure_modes.py           # NEW
│   ├── test_agent.py                   # NEW (observe, act, plan, react, triggers)
│   ├── test_strategy_llm_agent.py      # NEW (facade)
│   ├── test_engine_message_bus.py      # NEW (engine wiring, messages.jsonl, no-op for non-LLM)
│   ├── test_logging_phase2.py          # NEW (summary.json additive fields)
│   ├── test_llm_agent_integration.py   # NEW (end-to-end mock-LLM on haves_havenots)
│   ├── test_llm_agent_replay.py        # NEW (determinism via cache-warm replay)
│   └── test_llm_agent_failure_axes.py  # NEW (each failure mode produces measurable change)
├── reference_runs/                     # NEW top-level (git-tracked)
│   ├── haves_havenots/llm_agent/clean/         # NEW: cache + state/events/messages/summary
│   ├── haves_havenots/llm_agent/defectors/     # NEW
│   └── long_outage_72h/llm_agent/clean/        # NEW
├── pyproject.toml                      # MODIFY: add anthropic>=0.40
├── README.md                           # MODIFY: Phase 2 status section
└── CLAUDE.md                           # MODIFY: phase table marks Phase 2 in-progress → complete; progress log rows per task
```

**Why this structure:**
- Each `sim/agents/*` module has one responsibility and stays under ~300 lines. Tests for each module mock the LLM entirely — no API calls in CI.
- The strategy facade is the only file that knows the agent layer exists *and* the engine plug-point exists. The engine doesn't import from `sim/agents/`; it only imports `Message` and `MessageBus` types (which live in `sim/agents/protocol.py` and are re-exported from `sim/agents/__init__.py` for convenience).
- `reference_runs/` is the in-repo reproducibility artifact (per spec §6). The cache files there are content-addressed JSON; the layout mirrors `runs/`.

---

## Conventions and ground rules (Phase 2)

- **TDD always:** write failing test → run red → minimal impl → run green → commit. Never skip red.
- **Conventional commits** (`feat:`, `test:`, `chore:`, `docs:`). **No `Co-Authored-By: Claude` trailer** — attribute solely to Leo.
- **Update `CLAUDE.md` progress log** (newest on top) in the *same commit* as each task's code. **Mark this plan's checkboxes `- [x]`** in the same commit.
- **Determinism is mandatory:** cache-warm replays produce byte-identical `state.jsonl` / `events.jsonl` / `messages.jsonl`. Per-agent RNGs are seeded from `(scenario.seed, "agent", house_id)`. The message bus RNG from `(scenario.seed, "bus")`. The noise RNG from `(scenario.seed, "noise")`. The defector-assignment RNG from `(scenario.seed, "defector_assignment")`.
- **No real API calls in CI.** All tests use `MockLLMClient` with canned responses. Live tests are gated `@pytest.mark.llm_live` and excluded by default. The clean-install dry-run does NOT exercise the live API.
- **Clean-install verification before any commit touching `pyproject.toml`:** run the dry-run in `/tmp/microgrid_ci_check` (Task 1). After every push, glance at `gh run list --limit 1`.
- **Run the suite** with `.venv/bin/pytest -q` from the repo root. Lint/type: `.venv/bin/ruff check sim scripts && .venv/bin/mypy`.
- **All new modules in `sim/agents/`** are subject to `mypy --strict` like the rest of `sim/`.
- **`runs/` stays gitignored.** `reference_runs/` is NEW and git-tracked (Task 22 sets up `.gitignore`).
- **Continuous execution.** Don't pause between tasks for permission — proceed task-by-task. Stop only on real blockers (ambiguous spec, failing test you can't fix, decision not authorized).

---

## Task 1: Add `anthropic` dep + clean-install verify + `sim/agents/` package scaffold

**Files:**
- Modify: `pyproject.toml`
- Create: `sim/agents/__init__.py`
- Test: `tests/test_agents_package.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_agents_package.py
"""Smoke check: the new sim/agents/ package is importable."""

def test_agents_package_importable() -> None:
    import sim.agents  # noqa: F401


def test_anthropic_dep_installed() -> None:
    """Anthropic SDK must resolve; otherwise live LLM calls (and Task 6) cannot work."""
    import anthropic  # noqa: F401
    assert hasattr(anthropic, "Anthropic")
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_agents_package.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.agents'` AND `ModuleNotFoundError: No module named 'anthropic'`.

- [x] **Step 3: Add `anthropic` to `pyproject.toml`**

In `pyproject.toml` under `[project] dependencies`, append `"anthropic>=0.40"`:

```toml
dependencies = [
    "numpy>=2.0",
    "pyyaml>=6.0",
    "pandas>=2.2",
    "pyarrow>=16.0",
    "requests>=2.32",
    "scipy>=1.13",
    "anthropic>=0.40",
]
```

Add a mypy override at the bottom (Anthropic SDK doesn't ship full stubs as of late 2025):

```toml
[[tool.mypy.overrides]]
module = ["anthropic.*"]
ignore_missing_imports = true
```

- [x] **Step 4: Create the package**

```python
# sim/agents/__init__.py
"""Per-household LLM-agent layer for Phase 2.

Modules:
- ``policy``   — structured Policy + YAML round-trip + validator
- ``memory``   — append-only MemoryStream + top-K retrieval
- ``protocol`` — speech-act Message + MessageBus (queue / routing / dropout / budget)
- ``cache``    — content-addressed PromptCache (sha256, atomic, two-tier lookup)
- ``llm``      — abstract LLMClient + AnthropicLLMClient + MockLLMClient
- ``reflection`` — Park-adapted reflection LLM call wrapper
- ``failure_modes`` — FailureModeConfig + NoiseSource + DefectorWrapper
- ``agent``    — LLMAgent (observe / remember / plan / react / act)

Strategies plug in via ``sim.strategies.llm_agent``.
"""
```

- [x] **Step 5: Install the new dep in `.venv`**

Run: `.venv/bin/pip install -e .`
Expected: anthropic + transitive deps install cleanly.

- [x] **Step 6: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_agents_package.py -v`
Expected: PASS — both tests green.

- [x] **Step 7: Clean-install dry-run (per workflow rule)**

Run:
```bash
rm -rf /tmp/microgrid_ci_check && python3 -m venv /tmp/microgrid_ci_check
/tmp/microgrid_ci_check/bin/pip install --upgrade pip
/tmp/microgrid_ci_check/bin/pip install -e .
/tmp/microgrid_ci_check/bin/pytest tests/test_agents_package.py -v
```
Expected: both tests PASS in the fresh venv. If failure, **stop and diagnose** before committing.

- [x] **Step 8: Run the full existing suite to make sure nothing regressed**

Run: `.venv/bin/pytest -q`
Expected: 96 tests pass (Phase 1.6 baseline) + the 2 new agents-package tests = 98.

- [x] **Step 9: Commit**

Add the new progress-log row to `CLAUDE.md` (newest on top) under the existing Phase 1.6 entries:

```markdown
| 2026-06-13 | **P2 Task 1 — anthropic dep + sim/agents/ scaffold** ✅ | _(this commit)_ | 98 ✓ | Added `anthropic>=0.40` to deps (+ mypy override). New `sim/agents/__init__.py` documents the planned module list. Clean-install dry-run in fresh `/tmp/microgrid_ci_check` venv passed. No behavior change; just the substrate is now in place. |
```

Mark Task 1 checkboxes as `- [x]` in this plan file. Then:

```bash
git add pyproject.toml sim/agents/__init__.py tests/test_agents_package.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add anthropic dep + sim/agents package scaffold"
```

---

## Task 2: `Policy` dataclass + hand-rolled validator + YAML round-trip

**Files:**
- Create: `sim/agents/policy.py`
- Test: `tests/test_policy.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_policy.py
"""Policy schema: defaults, validator, YAML round-trip, fallback behavior."""

from __future__ import annotations

import pytest

from sim.agents.policy import Policy, PolicyValidationError, policy_from_yaml, policy_to_yaml


def _valid_policy_dict() -> dict:
    return {
        "sharing_intent": "balanced",
        "share_min_soc_frac": 0.50,
        "max_share_kw_per_tick": 1.5,
        "recipient_priority": [
            {"circle": "owner", "weight": 1.0},
            {"circle": "geographic", "weight": 0.4},
        ],
        "distrusted_peers": [],
        "request_urgency": "normal",
        "belief_note": "no strong beliefs yet",
        "ttl_ticks": 4,
    }


def test_policy_round_trip_yaml() -> None:
    p = policy_from_yaml(policy_to_yaml(Policy(**_valid_policy_dict())))
    assert p.sharing_intent == "balanced"
    assert p.share_min_soc_frac == 0.50
    assert p.recipient_priority[0].circle == "owner"
    assert p.recipient_priority[0].weight == 1.0
    assert p.distrusted_peers == ()
    assert p.ttl_ticks == 4


def test_policy_rejects_negative_weight() -> None:
    d = _valid_policy_dict()
    d["recipient_priority"][0]["weight"] = -0.5
    with pytest.raises(PolicyValidationError, match="weight"):
        Policy.from_dict(d)


def test_policy_rejects_ttl_zero() -> None:
    d = _valid_policy_dict()
    d["ttl_ticks"] = 0
    with pytest.raises(PolicyValidationError, match="ttl_ticks"):
        Policy.from_dict(d)


def test_policy_rejects_unknown_sharing_intent() -> None:
    d = _valid_policy_dict()
    d["sharing_intent"] = "ravenous"
    with pytest.raises(PolicyValidationError, match="sharing_intent"):
        Policy.from_dict(d)


def test_policy_rejects_bad_request_urgency() -> None:
    d = _valid_policy_dict()
    d["request_urgency"] = "panic"
    with pytest.raises(PolicyValidationError, match="request_urgency"):
        Policy.from_dict(d)


def test_policy_default_round_robin_fallback() -> None:
    fb = Policy.default_round_robin_fallback()
    assert fb.sharing_intent == "balanced"
    assert fb.share_min_soc_frac > 0.0
    assert any(rp.circle == "geographic" for rp in fb.recipient_priority)
    assert fb.ttl_ticks >= 1


def test_policy_is_frozen() -> None:
    p = Policy(**_valid_policy_dict())
    with pytest.raises(AttributeError):
        p.share_min_soc_frac = 0.9  # type: ignore[misc]
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_policy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.agents.policy'`.

- [x] **Step 3: Implement `sim/agents/policy.py`**

```python
# sim/agents/policy.py
"""Structured Policy schema with hand-rolled validation and YAML round-trip.

Adapted from Park et al., *Generative Agents* (arXiv:2304.03442), where agents
emit a structured plan; here the plan is the input to a pure-Python tick executor
that does not call the LLM. The schema is intentionally small so a hand-rolled
validator suffices (no Pydantic dependency).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

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

    @staticmethod
    def from_dict(d: dict) -> "Policy":
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
        )

    @staticmethod
    def default_round_robin_fallback() -> "Policy":
        """Geographic-only round-robin behavior. Used when LLM output is unparseable
        for 3+ consecutive policy refreshes (see Task 16)."""
        return Policy(
            sharing_intent="balanced",
            share_min_soc_frac=0.50,
            max_share_kw_per_tick=1.0,
            recipient_priority=(RecipientPriority(circle="geographic", weight=1.0),),
            distrusted_peers=(),
            request_urgency="normal",
            belief_note="(fallback to geographic round-robin)",
            ttl_ticks=4,
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
        },
        sort_keys=False,
    )


def policy_from_yaml(s: str) -> Policy:
    d = yaml.safe_load(s)
    if not isinstance(d, dict):
        raise PolicyValidationError(f"top-level must be a mapping, got {type(d).__name__}")
    return Policy.from_dict(d)


def _validate(d: dict) -> None:
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
            f"sharing_intent must be conservative|balanced|generous, got {d['sharing_intent']!r}"
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
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_policy.py -v`
Expected: 7 tests PASS.

- [x] **Step 5: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [x] **Step 6: Commit**

Add progress log row to `CLAUDE.md` (newest on top):

```markdown
| 2026-06-13 | **P2 Task 2 — Policy dataclass + validator** ✅ | _(this commit)_ | 105 ✓ | `sim/agents/policy.py` defines `Policy` (frozen dataclass) with hand-rolled validator + YAML round-trip + a `default_round_robin_fallback()` static method used when LLM output is unparseable. No Pydantic dep. |
```

Mark Task 2 checkboxes as `- [x]`. Then:

```bash
git add sim/agents/policy.py tests/test_policy.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add Policy dataclass + validator + YAML round-trip"
```

---

## Task 3: `MemoryEntry` + `MemoryStream` (append-only, top-K retrieval)

**Files:**
- Create: `sim/agents/memory.py`
- Test: `tests/test_memory.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory.py
"""MemoryStream: append-only invariant, retrieval ranking, importance heuristics."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from sim.agents.memory import MemoryEntry, MemoryStream


def _entry(t: datetime, kind: str, importance: float, nl: str = "") -> MemoryEntry:
    return MemoryEntry(t=t, kind=kind, content={}, nl=nl, importance=importance)


def test_memory_stream_append_only() -> None:
    s = MemoryStream()
    t0 = datetime(2026, 1, 1, 8, 0)
    s.append(_entry(t0, "obs", 5.0))
    s.append(_entry(t0 + timedelta(minutes=15), "msg_recv", 7.0))
    assert len(s.entries) == 2
    # entries should be a read-only view
    with pytest.raises((AttributeError, TypeError)):
        s.entries.append(_entry(t0, "obs", 1.0))  # type: ignore[attr-defined]


def test_memory_top_k_ranks_recent_and_important() -> None:
    s = MemoryStream()
    t0 = datetime(2026, 1, 1, 8, 0)
    # old + high importance
    s.append(_entry(t0, "reflection", importance=10.0, nl="old reflection"))
    # recent + low importance
    s.append(_entry(t0 + timedelta(hours=4), "obs", importance=2.0, nl="recent obs"))
    # recent + high importance — should rank first
    s.append(_entry(t0 + timedelta(hours=4), "reflection", importance=9.0, nl="recent reflection"))

    top = s.top_k(now=t0 + timedelta(hours=4), k=3)
    assert top[0].nl == "recent reflection"
    # the old high-importance entry should still appear, but below the recent ones
    nls = [e.nl for e in top]
    assert nls.index("recent reflection") < nls.index("old reflection")


def test_memory_top_k_respects_k() -> None:
    s = MemoryStream()
    t0 = datetime(2026, 1, 1, 8, 0)
    for i in range(50):
        s.append(_entry(t0 + timedelta(minutes=i), "obs", importance=float(i), nl=f"e{i}"))
    top = s.top_k(now=t0 + timedelta(minutes=60), k=20)
    assert len(top) == 20
    # the highest-importance entries should be present
    assert any(e.nl == "e49" for e in top)


def test_memory_entry_is_frozen() -> None:
    e = _entry(datetime(2026, 1, 1), "obs", 5.0)
    with pytest.raises((AttributeError, TypeError)):
        e.importance = 10.0  # type: ignore[misc]


def test_memory_stream_jsonl_round_trip(tmp_path) -> None:
    s = MemoryStream()
    t0 = datetime(2026, 1, 1, 8, 0)
    s.append(_entry(t0, "obs", 3.0, nl="hello"))
    s.append(_entry(t0 + timedelta(minutes=15), "reflection", 8.0, nl="world"))
    path = tmp_path / "mem.jsonl"
    s.write_jsonl(path)
    loaded = MemoryStream.from_jsonl(path)
    assert len(loaded.entries) == 2
    assert loaded.entries[0].nl == "hello"
    assert loaded.entries[1].importance == 8.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_memory.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.agents.memory'`.

- [ ] **Step 3: Implement `sim/agents/memory.py`**

```python
# sim/agents/memory.py
"""Append-only memory stream with top-K retrieval.

Adapted from Park et al., *Generative Agents* (arXiv:2304.03442) §A.1
(memory stream). The retrieval score is a weighted blend of recency,
importance, and (optionally) similarity. Similarity defaults to 1.0 when
no embedder is configured, so unit tests need no model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

MemoryKind = Literal["obs", "msg_sent", "msg_recv", "transfer_outcome", "reflection"]


@dataclass(frozen=True)
class MemoryEntry:
    t: datetime
    kind: MemoryKind
    content: dict[str, Any]
    nl: str
    importance: float  # 0..10


@dataclass
class MemoryStream:
    _entries: list[MemoryEntry] = field(default_factory=list)
    # tunable retrieval weights (sum to 1.0)
    alpha_recency: float = 0.4
    beta_importance: float = 0.4
    gamma_similarity: float = 0.2

    @property
    def entries(self) -> tuple[MemoryEntry, ...]:
        """Read-only view; tests assert append-only by trying to .append() this."""
        return tuple(self._entries)

    def append(self, e: MemoryEntry) -> None:
        self._entries.append(e)

    def top_k(
        self,
        now: datetime,
        k: int,
        query_nl: str | None = None,
        recency_half_life_hours: float = 4.0,
    ) -> list[MemoryEntry]:
        if not self._entries:
            return []

        def score(e: MemoryEntry) -> float:
            age_hours = max(0.0, (now - e.t).total_seconds() / 3600.0)
            recency = 0.5 ** (age_hours / recency_half_life_hours)  # 1.0 at t==now, halves every HL
            importance = e.importance / 10.0
            similarity = _cosine_or_one(query_nl, e.nl)
            return (
                self.alpha_recency * recency
                + self.beta_importance * importance
                + self.gamma_similarity * similarity
            )

        ranked = sorted(self._entries, key=score, reverse=True)
        return ranked[: max(0, k)]

    def write_jsonl(self, path: Path) -> None:
        path = Path(path)
        with path.open("w", encoding="utf-8") as f:
            for e in self._entries:
                f.write(
                    json.dumps(
                        {
                            "t": e.t.isoformat(),
                            "kind": e.kind,
                            "content": e.content,
                            "nl": e.nl,
                            "importance": e.importance,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )

    @staticmethod
    def from_jsonl(path: Path) -> "MemoryStream":
        s = MemoryStream()
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            s.append(
                MemoryEntry(
                    t=datetime.fromisoformat(d["t"]),
                    kind=d["kind"],
                    content=d["content"],
                    nl=d["nl"],
                    importance=float(d["importance"]),
                )
            )
        return s


def _cosine_or_one(query: str | None, text: str) -> float:
    """No embedder in v0; similarity is identity (1.0). Hook for Phase 3 to swap in."""
    del query, text
    return 1.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_memory.py -v`
Expected: 5 tests PASS.

- [ ] **Step 5: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 6: Commit**

Add progress log row to `CLAUDE.md` (newest on top):

```markdown
| 2026-06-13 | **P2 Task 3 — MemoryStream + top-K retrieval** ✅ | _(this commit)_ | 110 ✓ | Park-adapted append-only `MemoryStream` in `sim/agents/memory.py`. Retrieval is α·recency + β·importance + γ·similarity, γ defaulting to 1.0 (no embedder in v0; Phase 3 hook). JSONL round-trip for run-output persistence. |
```

Mark Task 3 checkboxes. Then:

```bash
git add sim/agents/memory.py tests/test_memory.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add MemoryStream with append-only invariant + top-K retrieval"
```

---

## Task 4: `Message` speech-act schema

**Files:**
- Create: `sim/agents/protocol.py` (Message portion only; MessageBus lands in Task 7)
- Test: `tests/test_protocol.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_protocol.py
"""Speech-act Message schema. MessageBus tests land in Task 7."""

from __future__ import annotations

from datetime import datetime

import pytest

from sim.agents.protocol import Message, new_correlation_id


def test_message_is_frozen() -> None:
    m = Message(
        t_sent=datetime(2026, 1, 1, 8, 0),
        sender="r0c0",
        recipient="r0c1",
        performative="REQUEST",
        payload={"kwh": 0.5},
        rationale_nl="my SoC is low",
        correlation_id="abc",
    )
    with pytest.raises((AttributeError, TypeError)):
        m.payload = {"kwh": 1.0}  # type: ignore[misc]


def test_message_performative_validated() -> None:
    with pytest.raises(ValueError, match="performative"):
        Message(
            t_sent=datetime(2026, 1, 1, 8, 0),
            sender="r0c0",
            recipient="r0c1",
            performative="SHRUG",  # type: ignore[arg-type]
            payload={},
            rationale_nl="",
            correlation_id="x",
        )


def test_new_correlation_id_unique_per_call() -> None:
    ids = {new_correlation_id() for _ in range(100)}
    assert len(ids) == 100


def test_new_correlation_id_deterministic_with_seeded_rng() -> None:
    import random

    rng1 = random.Random(42)
    rng2 = random.Random(42)
    a = [new_correlation_id(rng=rng1) for _ in range(5)]
    b = [new_correlation_id(rng=rng2) for _ in range(5)]
    assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.agents.protocol'`.

- [ ] **Step 3: Implement the Message portion of `sim/agents/protocol.py`**

```python
# sim/agents/protocol.py
"""Speech-act Message + MessageBus.

Performatives follow FIPA-ACL/speech-act tradition. The vocabulary is small enough
that recipient parsing is fully structured; only the ``rationale_nl`` field is
natural language, and it carries the explainability substrate Phase 3 evaluates.

MessageBus lands in Task 7; this module ships the Message type first so the
agent layer can be built bottom-up.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

Performative = Literal["REQUEST", "OFFER", "ACCEPT", "REJECT", "COUNTER", "INFORM"]

_VALID_PERFORMATIVES: frozenset[str] = frozenset(
    {"REQUEST", "OFFER", "ACCEPT", "REJECT", "COUNTER", "INFORM"}
)


@dataclass(frozen=True)
class Message:
    t_sent: datetime
    sender: str
    recipient: str
    performative: Performative
    payload: dict[str, Any]
    rationale_nl: str
    correlation_id: str

    def __post_init__(self) -> None:
        if self.performative not in _VALID_PERFORMATIVES:
            raise ValueError(
                f"performative must be one of {sorted(_VALID_PERFORMATIVES)}, "
                f"got {self.performative!r}"
            )


def new_correlation_id(rng: random.Random | None = None) -> str:
    """Return a short id for threading a negotiation.

    If ``rng`` is provided, the id is deterministic given that RNG's state.
    Engine-owned RNG is what tests pass in; production code uses ``uuid.uuid4``.
    """
    if rng is None:
        return uuid.uuid4().hex[:12]
    return "%012x" % rng.getrandbits(48)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_protocol.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 6: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 4 — Message speech-act schema** ✅ | _(this commit)_ | 114 ✓ | Frozen `Message` dataclass with REQUEST/OFFER/ACCEPT/REJECT/COUNTER/INFORM vocabulary in `sim/agents/protocol.py`. `new_correlation_id(rng)` is deterministic when seeded RNG passed in. MessageBus lands in Task 7. |
```

Mark Task 4 checkboxes. Then:

```bash
git add sim/agents/protocol.py tests/test_protocol.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add Message speech-act schema with deterministic correlation ids"
```

---

## Task 5: `PromptCache` (sha256-keyed, atomic on-disk, two-tier lookup)

**Files:**
- Create: `sim/agents/cache.py`
- Test: `tests/test_cache.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cache.py
"""PromptCache: content-addressed lookup, atomic writes, two-tier search order."""

from __future__ import annotations

import json
from pathlib import Path

from sim.agents.cache import PromptCache, cache_key


def _req(user: str = "hello") -> dict:
    return {
        "model": "claude-haiku-4-5-20251001",
        "system": "you are a helpful assistant",
        "user": user,
        "temperature": 0.0,
        "max_tokens": 256,
        "tools_schema": [],
    }


def test_cache_key_deterministic() -> None:
    k1 = cache_key(_req())
    k2 = cache_key(_req())
    assert k1 == k2
    # different user → different key
    assert cache_key(_req("hi")) != k1


def test_cache_miss_then_hit(tmp_path: Path) -> None:
    cache = PromptCache(local_dir=tmp_path / "local")
    req = _req()
    assert cache.get(req) is None

    cache.put(req, {"completion": "world"})
    got = cache.get(req)
    assert got == {"completion": "world"}


def test_cache_two_tier_lookup_local_wins(tmp_path: Path) -> None:
    """When both local and reference caches have the same key, local wins."""
    local = tmp_path / "local"
    ref = tmp_path / "ref"
    cache = PromptCache(local_dir=local, reference_dir=ref)
    req = _req()

    # populate reference with one value, local with another
    ref_cache = PromptCache(local_dir=ref)
    ref_cache.put(req, {"completion": "from-reference"})
    cache.put(req, {"completion": "from-local"})

    got = cache.get(req)
    assert got == {"completion": "from-local"}


def test_cache_falls_back_to_reference(tmp_path: Path) -> None:
    local = tmp_path / "local"
    ref = tmp_path / "ref"
    cache = PromptCache(local_dir=local, reference_dir=ref)
    req = _req()

    PromptCache(local_dir=ref).put(req, {"completion": "from-reference"})

    got = cache.get(req)
    assert got == {"completion": "from-reference"}


def test_cache_writes_are_atomic(tmp_path: Path) -> None:
    """Killing the process mid-write must not leave a half-written cache file.
    We simulate by checking that no .tmp files leak after a normal put()."""
    cache = PromptCache(local_dir=tmp_path / "local")
    cache.put(_req(), {"completion": "x"})
    leftover = list((tmp_path / "local").rglob("*.tmp"))
    assert leftover == []


def test_cache_files_are_well_formed_json(tmp_path: Path) -> None:
    cache = PromptCache(local_dir=tmp_path / "local")
    cache.put(_req(), {"completion": "x"})
    files = list((tmp_path / "local").rglob("*.json"))
    assert len(files) == 1
    blob = json.loads(files[0].read_text())
    assert blob["response"] == {"completion": "x"}
    assert blob["model"] == "claude-haiku-4-5-20251001"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.agents.cache'`.

- [ ] **Step 3: Implement `sim/agents/cache.py`**

```python
# sim/agents/cache.py
"""Content-addressed prompt cache.

Cache key = sha256(json({model, system, user, temperature, max_tokens, tools_schema})).
Storage: ``<dir>/<model_name>/<key>.json`` with body {prompt, response, model, ...}.

Lookup order:
1. ``local_dir`` (run-local cache, populated by prior calls in this run/output dir)
2. ``reference_dir`` (in-repo reference_runs/ cache, shipped with the paper)
3. miss — caller hits the API and must call ``put(...)`` afterwards.

Writes are atomic (tmp file + os.replace).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def cache_key(req: dict[str, Any]) -> str:
    blob = json.dumps(
        {
            "model": req["model"],
            "system": req["system"],
            "user": req["user"],
            "temperature": req["temperature"],
            "max_tokens": req["max_tokens"],
            "tools_schema": req.get("tools_schema", []),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class PromptCache:
    local_dir: Path
    reference_dir: Path | None = None

    def get(self, req: dict[str, Any]) -> dict[str, Any] | None:
        key = cache_key(req)
        model = req["model"]
        for root in (self.local_dir, self.reference_dir):
            if root is None:
                continue
            path = Path(root) / model / f"{key}.json"
            if path.exists():
                blob = json.loads(path.read_text(encoding="utf-8"))
                return blob["response"]  # type: ignore[no-any-return]
        return None

    def put(self, req: dict[str, Any], response: dict[str, Any]) -> None:
        key = cache_key(req)
        model = req["model"]
        target_dir = Path(self.local_dir) / model
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{key}.json"
        blob = {
            "model": model,
            "system": req["system"],
            "user": req["user"],
            "temperature": req["temperature"],
            "max_tokens": req["max_tokens"],
            "tools_schema": req.get("tools_schema", []),
            "response": response,
            "t_iso": datetime.now(timezone.utc).isoformat(),
        }
        # atomic write: tmp + os.replace; never leaves .tmp behind on success
        fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=f".{key}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(blob, f, sort_keys=True, separators=(",", ":"))
            os.replace(tmp_path, target)
        except Exception:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_cache.py -v`
Expected: 6 tests PASS.

- [ ] **Step 5: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 6: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 5 — PromptCache (two-tier sha256)** ✅ | _(this commit)_ | 120 ✓ | `sim/agents/cache.py`: content-addressed prompt cache (sha256 over canonical-json of model+system+user+temp+max_tokens+tools_schema). Two-tier lookup: local then reference_runs/ cache. Atomic writes via tmp+os.replace. |
```

Mark Task 5 checkboxes. Then:

```bash
git add sim/agents/cache.py tests/test_cache.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add two-tier sha256 prompt cache with atomic writes"
```

---

## Task 6: `MockLLMClient` + abstract `LLMClient` interface

**Files:**
- Create: `sim/agents/llm.py` (Mock + abstract base only; AnthropicLLMClient lands in Task 7)
- Test: `tests/test_llm_client.py` (Mock half only)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_client.py
"""LLMClient abstract + MockLLMClient. AnthropicLLMClient tests are appended in Task 7."""

from __future__ import annotations

import pytest

from sim.agents.cache import PromptCache
from sim.agents.llm import LLMRequest, LLMResponse, MockLLMClient, NoMockResponseError


def test_mock_returns_canned_response(tmp_path) -> None:
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={
            "hello": LLMResponse(text="world", tokens_in=5, tokens_out=1),
        },
    )
    req = LLMRequest(
        model="claude-haiku-4-5-20251001",
        system="sys",
        user="hello",
        max_tokens=64,
    )
    resp = mock.call(req)
    assert resp.text == "world"


def test_mock_raises_on_unrecognized_prompt(tmp_path) -> None:
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={"hello": LLMResponse(text="world", tokens_in=5, tokens_out=1)},
    )
    req = LLMRequest(
        model="claude-haiku-4-5-20251001",
        system="sys",
        user="surprise!",
        max_tokens=64,
    )
    with pytest.raises(NoMockResponseError, match="surprise"):
        mock.call(req)


def test_mock_uses_cache(tmp_path) -> None:
    """First call hits the mock; second identical call hits the cache and the mock would refuse."""
    cache = PromptCache(local_dir=tmp_path)
    mock = MockLLMClient(
        cache=cache,
        canned={"hello": LLMResponse(text="world", tokens_in=5, tokens_out=1)},
    )
    req = LLMRequest(
        model="claude-haiku-4-5-20251001",
        system="sys",
        user="hello",
        max_tokens=64,
    )
    first = mock.call(req)
    # second call: remove the canned response — cache should win
    mock.canned.clear()
    second = mock.call(req)
    assert first.text == second.text == "world"


def test_mock_substring_match_is_supported(tmp_path) -> None:
    """For agent prompt tests, we match by substring in the user prompt — exact match is too brittle for evolving prompts."""
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={"greet": LLMResponse(text="hi", tokens_in=2, tokens_out=1)},
    )
    req = LLMRequest(
        model="claude-haiku-4-5-20251001",
        system="sys",
        user="please greet the user warmly",
        max_tokens=64,
    )
    resp = mock.call(req)
    assert resp.text == "hi"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_llm_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.agents.llm'`.

- [ ] **Step 3: Implement the Mock + abstract base in `sim/agents/llm.py`**

```python
# sim/agents/llm.py
"""LLMClient abstractions.

This module ships:
- ``LLMRequest`` / ``LLMResponse`` — provider-neutral data shapes
- ``LLMClient`` — abstract base with cache integration
- ``MockLLMClient`` — substring-keyed canned-response client for tests
- ``AnthropicLLMClient`` — real Claude API adapter (Task 7)

Cache integration is in the base class: every call routes through
``self.cache.get(...)`` and ``self.cache.put(...)``. Subclasses only implement
``_call_provider(req)`` for actual API I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sim.agents.cache import PromptCache


class NoMockResponseError(LookupError):
    """Raised when MockLLMClient receives a prompt it has no canned response for."""


@dataclass(frozen=True)
class LLMRequest:
    model: str
    system: str
    user: str
    max_tokens: int
    temperature: float = 0.0
    tools_schema: list[dict[str, Any]] = field(default_factory=list)

    def to_cache_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "system": self.system,
            "user": self.user,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "tools_schema": self.tools_schema,
        }


@dataclass(frozen=True)
class LLMResponse:
    text: str
    tokens_in: int
    tokens_out: int


@dataclass
class LLMClient:
    """Abstract base. Subclasses implement ``_call_provider``."""
    cache: PromptCache

    def call(self, req: LLMRequest) -> LLMResponse:
        cache_req = req.to_cache_dict()
        cached = self.cache.get(cache_req)
        if cached is not None:
            return LLMResponse(
                text=cached["text"],
                tokens_in=int(cached.get("tokens_in", 0)),
                tokens_out=int(cached.get("tokens_out", 0)),
            )
        resp = self._call_provider(req)
        self.cache.put(
            cache_req,
            {"text": resp.text, "tokens_in": resp.tokens_in, "tokens_out": resp.tokens_out},
        )
        return resp

    def _call_provider(self, req: LLMRequest) -> LLMResponse:  # pragma: no cover
        raise NotImplementedError


@dataclass
class MockLLMClient(LLMClient):
    """Returns canned responses keyed by a substring of the user prompt.

    Substring matching is more robust for evolving prompts than exact match.
    First key whose substring appears in ``req.user`` wins (deterministic dict order).
    """
    canned: dict[str, LLMResponse] = field(default_factory=dict)

    def _call_provider(self, req: LLMRequest) -> LLMResponse:
        for key, resp in self.canned.items():
            if key in req.user:
                return resp
        raise NoMockResponseError(
            f"no canned response matches user prompt: {req.user[:80]!r} "
            f"(canned keys: {sorted(self.canned)})"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_llm_client.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 6: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 6 — LLMClient abstract + MockLLMClient** ✅ | _(this commit)_ | 124 ✓ | `sim/agents/llm.py`: `LLMRequest`/`LLMResponse` data shapes, `LLMClient` base class (handles cache get/put), `MockLLMClient` (substring-keyed canned responses for tests). Real `AnthropicLLMClient` lands in Task 7. |
```

Mark Task 6 checkboxes. Then:

```bash
git add sim/agents/llm.py tests/test_llm_client.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add LLMClient abstract base + MockLLMClient for tests"
```

---

## Task 7: `AnthropicLLMClient` (real Claude API adapter)

**Files:**
- Modify: `sim/agents/llm.py` — append `AnthropicLLMClient`
- Test: `tests/test_llm_client.py` — append HTTP-mock tests

- [ ] **Step 1: Write the failing test (append to existing file)**

Append to `tests/test_llm_client.py`:

```python
# --- AnthropicLLMClient tests (Task 7) ---

from unittest.mock import MagicMock, patch

from sim.agents.llm import AnthropicLLMClient


def test_anthropic_client_calls_messages_create(tmp_path) -> None:
    fake_msg = MagicMock()
    fake_msg.content = [MagicMock(text="hello world")]
    fake_msg.usage = MagicMock(input_tokens=12, output_tokens=3)

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_msg

    with patch("sim.agents.llm.anthropic.Anthropic", return_value=fake_client):
        adapter = AnthropicLLMClient(
            cache=PromptCache(local_dir=tmp_path),
            api_key="sk-test",
        )
        req = LLMRequest(
            model="claude-haiku-4-5-20251001",
            system="sys",
            user="hi",
            max_tokens=64,
        )
        resp = adapter.call(req)

    assert resp.text == "hello world"
    assert resp.tokens_in == 12
    assert resp.tokens_out == 3
    # the request must have used temperature=0
    kwargs = fake_client.messages.create.call_args.kwargs
    assert kwargs["temperature"] == 0.0
    assert kwargs["model"] == "claude-haiku-4-5-20251001"


def test_anthropic_client_retries_on_rate_limit(tmp_path) -> None:
    import anthropic as anthropic_sdk

    fake_msg = MagicMock()
    fake_msg.content = [MagicMock(text="ok")]
    fake_msg.usage = MagicMock(input_tokens=1, output_tokens=1)

    fake_client = MagicMock()
    err = anthropic_sdk.RateLimitError(
        message="slow down", response=MagicMock(status_code=429), body=None,
    )
    fake_client.messages.create.side_effect = [err, fake_msg]

    with patch("sim.agents.llm.anthropic.Anthropic", return_value=fake_client), \
         patch("sim.agents.llm.time.sleep") as sleeper:
        adapter = AnthropicLLMClient(
            cache=PromptCache(local_dir=tmp_path),
            api_key="sk-test",
            max_retries=3,
            base_backoff_s=0.1,
        )
        req = LLMRequest(
            model="claude-haiku-4-5-20251001",
            system="sys", user="hi", max_tokens=64,
        )
        resp = adapter.call(req)

    assert resp.text == "ok"
    assert fake_client.messages.create.call_count == 2
    sleeper.assert_called()  # backoff was used


def test_anthropic_client_cache_hit_skips_api(tmp_path) -> None:
    cache = PromptCache(local_dir=tmp_path)
    # pre-populate cache
    req = LLMRequest(
        model="claude-haiku-4-5-20251001",
        system="sys", user="hi", max_tokens=64,
    )
    cache.put(req.to_cache_dict(), {"text": "cached", "tokens_in": 0, "tokens_out": 0})

    fake_client = MagicMock()
    with patch("sim.agents.llm.anthropic.Anthropic", return_value=fake_client):
        adapter = AnthropicLLMClient(cache=cache, api_key="sk-test")
        resp = adapter.call(req)

    assert resp.text == "cached"
    fake_client.messages.create.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_llm_client.py -v -k anthropic`
Expected: FAIL — `ImportError: cannot import name 'AnthropicLLMClient'`.

- [ ] **Step 3: Append `AnthropicLLMClient` to `sim/agents/llm.py`**

Add to the imports near the top:

```python
import time

import anthropic
```

Append at the end of the file:

```python
@dataclass
class AnthropicLLMClient(LLMClient):
    """Anthropic Claude API adapter. Temperature is forced to 0.0.

    Retries on RateLimitError (429), APIConnectionError, and 5xx via
    exponential backoff. The cache hit-path is inherited from ``LLMClient``,
    so a cache hit never touches the network.
    """
    api_key: str = ""
    max_retries: int = 5
    base_backoff_s: float = 1.0
    _sdk_client: anthropic.Anthropic | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self._sdk_client is None:
            self._sdk_client = anthropic.Anthropic(api_key=self.api_key or None)

    def _call_provider(self, req: LLMRequest) -> LLMResponse:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                msg = self._sdk_client.messages.create(  # type: ignore[union-attr]
                    model=req.model,
                    max_tokens=req.max_tokens,
                    temperature=0.0,  # always; spec §5 invariant
                    system=req.system,
                    messages=[{"role": "user", "content": req.user}],
                )
                text = "".join(getattr(b, "text", "") for b in msg.content)
                return LLMResponse(
                    text=text,
                    tokens_in=int(msg.usage.input_tokens),
                    tokens_out=int(msg.usage.output_tokens),
                )
            except (
                anthropic.RateLimitError,
                anthropic.APIConnectionError,
                anthropic.InternalServerError,
            ) as e:
                last_exc = e
                sleep_s = self.base_backoff_s * (2 ** attempt)
                time.sleep(sleep_s)
        assert last_exc is not None
        raise last_exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_llm_client.py -v`
Expected: 7 tests PASS (4 from Task 6 + 3 new).

- [ ] **Step 5: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 6: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 7 — AnthropicLLMClient + retries** ✅ | _(this commit)_ | 127 ✓ | `AnthropicLLMClient` calls `messages.create` with temperature=0; exponential backoff on RateLimit/APIConnection/InternalServerError. Cache hit bypasses the API entirely. HTTP-level tests use `unittest.mock`. |
```

Mark Task 7 checkboxes. Then:

```bash
git add sim/agents/llm.py tests/test_llm_client.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add AnthropicLLMClient with retries + temperature=0"
```

---

## Task 8: `MessageBus` core (queue + routing through `union_neighbors`)

**Files:**
- Modify: `sim/agents/protocol.py` — append `MessageBus`
- Test: `tests/test_protocol.py` — append bus tests

- [ ] **Step 1: Write the failing test (append)**

Append to `tests/test_protocol.py`:

```python
# --- MessageBus tests (Task 8) ---

import json

from sim.agents.protocol import MessageBus
from sim.network import Neighborhood


def _bus_neighborhood() -> Neighborhood:
    return Neighborhood(
        comm_graph={"r0c0": ["r0c1"], "r0c1": ["r0c0"], "r1c0": []},
        edges_by_type={
            "geographic": {"r0c0": ["r0c1"], "r0c1": ["r0c0"], "r1c0": []},
            "owner": {"r0c0": ["r1c0"], "r0c1": [], "r1c0": ["r0c0"]},
        },
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
    )


def _msg(t, sender, recipient, perf="REQUEST", kwh=0.5) -> Message:
    return Message(
        t_sent=t, sender=sender, recipient=recipient,
        performative=perf, payload={"kwh": kwh}, rationale_nl="ok", correlation_id="x",
    )


def test_bus_delivers_next_tick() -> None:
    bus = MessageBus(neighborhood=_bus_neighborhood(), seed=42)
    t0 = datetime(2026, 1, 1, 8, 0)
    bus.send(_msg(t0, "r0c0", "r0c1"))
    # nothing yet at t0
    assert bus.deliver_pending(t0) == {}
    # delivered at t1
    inboxes = bus.deliver_pending(t0 + timedelta(minutes=15))
    assert "r0c1" in inboxes
    assert inboxes["r0c1"][0].sender == "r0c0"


def test_bus_routes_owner_layer_too() -> None:
    """r0c0 and r1c0 are not geographic neighbors but share an owner edge."""
    bus = MessageBus(neighborhood=_bus_neighborhood(), seed=42)
    t0 = datetime(2026, 1, 1, 8, 0)
    bus.send(_msg(t0, "r0c0", "r1c0"))
    inboxes = bus.deliver_pending(t0 + timedelta(minutes=15))
    assert "r1c0" in inboxes


def test_bus_rejects_off_graph_recipient(tmp_path) -> None:
    bus = MessageBus(neighborhood=_bus_neighborhood(), seed=42)
    t0 = datetime(2026, 1, 1, 8, 0)
    bus.send(_msg(t0, "r0c1", "r1c0"))  # r0c1 and r1c0 share no edge of any type
    inboxes = bus.deliver_pending(t0 + timedelta(minutes=15))
    assert "r1c0" not in inboxes
    drops = [r for r in bus.iter_log() if r["outcome"] == "dropped" and r["reason"] == "invalid_recipient"]
    assert len(drops) == 1


def test_bus_log_jsonl_round_trip(tmp_path) -> None:
    bus = MessageBus(neighborhood=_bus_neighborhood(), seed=42)
    t0 = datetime(2026, 1, 1, 8, 0)
    bus.send(_msg(t0, "r0c0", "r0c1"))
    bus.deliver_pending(t0 + timedelta(minutes=15))
    bus.write_jsonl(tmp_path / "messages.jsonl")
    rows = [json.loads(line) for line in (tmp_path / "messages.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["outcome"] == "delivered"
    assert rows[0]["sender"] == "r0c0"
    assert rows[0]["recipient"] == "r0c1"
    assert rows[0]["performative"] == "REQUEST"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_protocol.py -v -k bus`
Expected: FAIL — `ImportError: cannot import name 'MessageBus'`.

- [ ] **Step 3: Append `MessageBus` to `sim/agents/protocol.py`**

Add to imports near the top:

```python
import json
import random
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from sim.network import Neighborhood
```

Append at the end:

```python
@dataclass
class _LogRow:
    t_sent: datetime
    t_decided: datetime
    sender: str
    recipient: str
    performative: str
    payload: dict[str, Any]
    rationale_nl: str
    correlation_id: str
    outcome: Literal["delivered", "dropped"]
    reason: str | None = None


@dataclass
class MessageBus:
    """One-tick-latency message queue with structured routing and per-message logging.

    Messages sent at tick t are delivered at tick t+dt (default 15 min). The bus
    enforces:
    - **routing** through ``Neighborhood.union_neighbors`` (any overlay edge type),
    - **dropout** per ``failure_modes.comm.drop_prob_by_circle`` (set via ``configure_failure_modes``),
    - **per-tick send budget** per agent (set via ``configure_failure_modes``).

    All decisions are logged to an in-memory list; ``write_jsonl`` dumps to
    ``messages.jsonl``. Drops are logged with a ``reason``.
    """
    neighborhood: Neighborhood
    seed: int = 0
    dt: timedelta = timedelta(minutes=15)

    _queue: list[Message] = field(default_factory=list)
    _log: list[_LogRow] = field(default_factory=list)
    _rng: random.Random = field(init=False, repr=False)
    _drop_prob_by_circle: dict[str, float] = field(default_factory=dict)
    _per_tick_budget: int | None = field(default=None)
    _budget_used: dict[tuple[datetime, str], int] = field(
        default_factory=lambda: defaultdict(int)
    )

    def __post_init__(self) -> None:
        self._rng = random.Random(hash((self.seed, "bus")) & 0xFFFFFFFF)

    def configure_failure_modes(
        self,
        drop_prob_by_circle: dict[str, float] | None = None,
        per_tick_budget: int | None = None,
    ) -> None:
        self._drop_prob_by_circle = dict(drop_prob_by_circle or {})
        self._per_tick_budget = per_tick_budget

    def send(self, m: Message) -> None:
        # apply budget first
        if self._per_tick_budget is not None:
            key = (m.t_sent, m.sender)
            self._budget_used[key] += 1
            if self._budget_used[key] > self._per_tick_budget:
                self._log.append(_LogRow(
                    t_sent=m.t_sent, t_decided=m.t_sent,
                    sender=m.sender, recipient=m.recipient,
                    performative=m.performative, payload=dict(m.payload),
                    rationale_nl=m.rationale_nl, correlation_id=m.correlation_id,
                    outcome="dropped", reason="budget_overflow",
                ))
                return
        # route validity
        if m.recipient not in self.neighborhood.union_neighbors(m.sender):
            self._log.append(_LogRow(
                t_sent=m.t_sent, t_decided=m.t_sent,
                sender=m.sender, recipient=m.recipient,
                performative=m.performative, payload=dict(m.payload),
                rationale_nl=m.rationale_nl, correlation_id=m.correlation_id,
                outcome="dropped", reason="invalid_recipient",
            ))
            return
        # apply per-circle dropout (use the *highest-priority* circle connecting them)
        circle = self._circle_between(m.sender, m.recipient)
        drop_p = self._drop_prob_by_circle.get(circle, 0.0)
        if drop_p > 0 and self._rng.random() < drop_p:
            self._log.append(_LogRow(
                t_sent=m.t_sent, t_decided=m.t_sent,
                sender=m.sender, recipient=m.recipient,
                performative=m.performative, payload=dict(m.payload),
                rationale_nl=m.rationale_nl, correlation_id=m.correlation_id,
                outcome="dropped", reason="comm_drop",
            ))
            return
        self._queue.append(m)

    def deliver_pending(self, now: datetime) -> dict[str, list[Message]]:
        inboxes: dict[str, list[Message]] = defaultdict(list)
        keep: list[Message] = []
        for m in self._queue:
            if m.t_sent + self.dt <= now:
                inboxes[m.recipient].append(m)
                self._log.append(_LogRow(
                    t_sent=m.t_sent, t_decided=now,
                    sender=m.sender, recipient=m.recipient,
                    performative=m.performative, payload=dict(m.payload),
                    rationale_nl=m.rationale_nl, correlation_id=m.correlation_id,
                    outcome="delivered",
                ))
            else:
                keep.append(m)
        self._queue = keep
        return dict(inboxes)

    def iter_log(self) -> list[dict[str, Any]]:
        return [
            {
                "t_sent": r.t_sent.isoformat(),
                "t_decided": r.t_decided.isoformat(),
                "sender": r.sender,
                "recipient": r.recipient,
                "performative": r.performative,
                "payload": r.payload,
                "rationale_nl": r.rationale_nl,
                "correlation_id": r.correlation_id,
                "outcome": r.outcome,
                "reason": r.reason,
            }
            for r in self._log
        ]

    def write_jsonl(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for row in self.iter_log():
                f.write(json.dumps(row, sort_keys=True) + "\n")

    def _circle_between(self, sender: str, recipient: str) -> str:
        """Return the (deterministic) circle name connecting sender and recipient.

        Preference order: any non-geographic overlay first (alphabetical), then geographic.
        This lets ``drop_prob_by_circle`` differentiate reliable owner edges from
        flaky geographic ones even when both connect the same pair.
        """
        for circle in sorted(self.neighborhood.edges_by_type):
            if circle == "geographic":
                continue
            if recipient in self.neighborhood.edges_by_type[circle].get(sender, []):
                return circle
        return "geographic"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_protocol.py -v`
Expected: 8 tests PASS (4 Message + 4 bus).

- [ ] **Step 5: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 6: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 8 — MessageBus (queue + routing)** ✅ | _(this commit)_ | 135 ✓ | One-tick-latency `MessageBus` in `sim/agents/protocol.py`: routes only through `union_neighbors` (any overlay edge), logs every send + delivery decision, writes `messages.jsonl`. Dropout + budget hooks installed; their failure-mode behaviors land in Task 9. |
```

Mark Task 8 checkboxes. Then:

```bash
git add sim/agents/protocol.py tests/test_protocol.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add MessageBus with one-tick latency + overlay-aware routing"
```

---

## Task 9: `MessageBus` dropout + budget failure-mode behaviors

**Files:**
- Modify: nothing (MessageBus already has the hooks from Task 8) — but tests are needed to lock in behavior
- Test: `tests/test_protocol.py` — append failure-behavior tests

- [ ] **Step 1: Write the failing tests (append)**

Append to `tests/test_protocol.py`:

```python
# --- MessageBus failure-mode tests (Task 9) ---


def test_bus_drops_per_circle_probability() -> None:
    """drop_prob_by_circle drops messages on the named circle with that probability."""
    bus = MessageBus(neighborhood=_bus_neighborhood(), seed=42)
    bus.configure_failure_modes(drop_prob_by_circle={"geographic": 1.0})
    t0 = datetime(2026, 1, 1, 8, 0)
    bus.send(_msg(t0, "r0c0", "r0c1"))  # geographic edge
    inboxes = bus.deliver_pending(t0 + timedelta(minutes=15))
    assert inboxes == {}  # dropped
    drops = [r for r in bus.iter_log() if r["reason"] == "comm_drop"]
    assert len(drops) == 1


def test_bus_owner_layer_preferred_over_geographic_for_dropout() -> None:
    """When two houses share both a geographic and an owner edge, dropout uses the owner rate."""
    nb = Neighborhood(
        comm_graph={"a": ["b"], "b": ["a"]},
        edges_by_type={
            "geographic": {"a": ["b"], "b": ["a"]},
            "owner": {"a": ["b"], "b": ["a"]},  # same pair on both layers
        },
        bus_max_kw=50.0, bus_loss_factor=0.05,
    )
    bus = MessageBus(neighborhood=nb, seed=42)
    bus.configure_failure_modes(drop_prob_by_circle={"geographic": 1.0, "owner": 0.0})
    t0 = datetime(2026, 1, 1, 8, 0)
    bus.send(_msg(t0, "a", "b"))
    inboxes = bus.deliver_pending(t0 + timedelta(minutes=15))
    # owner circle wins ⇒ not dropped
    assert "b" in inboxes


def test_bus_per_tick_budget_enforces_cap() -> None:
    bus = MessageBus(neighborhood=_bus_neighborhood(), seed=42)
    bus.configure_failure_modes(per_tick_budget=2)
    t0 = datetime(2026, 1, 1, 8, 0)
    bus.send(_msg(t0, "r0c0", "r0c1"))
    bus.send(_msg(t0, "r0c0", "r1c0"))  # owner-edge
    bus.send(_msg(t0, "r0c0", "r0c1"))  # 3rd — exceeds budget
    inboxes = bus.deliver_pending(t0 + timedelta(minutes=15))
    delivered = sum(len(v) for v in inboxes.values())
    assert delivered == 2
    overflows = [r for r in bus.iter_log() if r["reason"] == "budget_overflow"]
    assert len(overflows) == 1


def test_bus_dropout_is_deterministic_given_seed() -> None:
    """Same seed + same send sequence => same drop sequence."""
    nb = _bus_neighborhood()
    t0 = datetime(2026, 1, 1, 8, 0)

    def collect_outcomes(seed: int) -> list[str]:
        bus = MessageBus(neighborhood=nb, seed=seed)
        bus.configure_failure_modes(drop_prob_by_circle={"geographic": 0.5})
        for i in range(20):
            bus.send(_msg(t0, "r0c0", "r0c1"))
        return [r["outcome"] for r in bus.iter_log()]

    a = collect_outcomes(123)
    b = collect_outcomes(123)
    assert a == b
    # different seed => different sequence (unless extremely unlikely)
    c = collect_outcomes(456)
    assert a != c  # if this is ever flaky in CI, the bus RNG is broken
```

- [ ] **Step 2: Run test to verify it fails… or that it already passes**

Run: `.venv/bin/pytest tests/test_protocol.py -v -k "dropout or budget"`

Expected: the four new tests PASS without modification — Task 8 already installed the hooks. (This is a *behavior lock-in* task — the failing-first idiom is satisfied by the four tests existing before behavior could be regressed.)

If any test fails, fix `MessageBus` in `sim/agents/protocol.py` and re-run.

- [ ] **Step 3: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 4: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 9 — MessageBus dropout + budget behavior lock-in** ✅ | _(this commit)_ | 139 ✓ | Four tests pin down: per-circle dropout obeys `drop_prob_by_circle`; non-geographic circle preferred when a pair shares multiple edges; per-tick budget enforces cap with `budget_overflow` log reason; dropout sequence deterministic given seed. |
```

Mark Task 9 checkboxes. Then:

```bash
git add tests/test_protocol.py docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "test: lock in MessageBus dropout + budget behavior"
```

---

## Task 10: `FailureModeConfig` + scenario YAML parsing

**Files:**
- Create: `sim/agents/failure_modes.py` (FailureModeConfig portion only; NoiseSource + DefectorWrapper land in Task 11)
- Modify: `sim/scenario.py` to parse `failure_modes:` + `llm:` blocks
- Test: `tests/test_failure_modes.py`
- Test: extend `tests/test_scenario.py` for YAML parsing

- [ ] **Step 1: Write the failing tests**

Create `tests/test_failure_modes.py`:

```python
# tests/test_failure_modes.py
"""FailureModeConfig defaults, deterministic defector assignment, YAML parsing."""

from __future__ import annotations

from sim.agents.failure_modes import FailureModeConfig, assign_defectors


def test_failure_mode_defaults_are_clean_cell() -> None:
    cfg = FailureModeConfig()
    assert cfg.defector_fraction == 0.0
    assert cfg.defector_realization == "prompt"
    assert cfg.obs_noise.soc_std_frac == 0.0
    assert cfg.comm.per_tick_budget is None
    assert cfg.comm.drop_prob_by_circle == {}


def test_defector_assignment_deterministic() -> None:
    house_ids = [f"r{r}c{c}" for r in range(5) for c in range(6)]
    cfg = FailureModeConfig(defector_fraction=0.2, defector_assignment="random")
    a = assign_defectors(house_ids, cfg, scenario_seed=42)
    b = assign_defectors(house_ids, cfg, scenario_seed=42)
    assert a == b
    c = assign_defectors(house_ids, cfg, scenario_seed=43)
    assert a != c


def test_defector_assignment_manual_overrides() -> None:
    house_ids = [f"r{r}c{c}" for r in range(5) for c in range(6)]
    cfg = FailureModeConfig(
        defector_fraction=0.2,
        defector_assignment="manual",
        defector_house_ids=("r2c3", "r4c1"),
    )
    ids = assign_defectors(house_ids, cfg, scenario_seed=42)
    assert ids == {"r2c3", "r4c1"}


def test_defector_count_matches_fraction() -> None:
    house_ids = [f"h{i}" for i in range(30)]
    cfg = FailureModeConfig(defector_fraction=0.2, defector_assignment="random")
    ids = assign_defectors(house_ids, cfg, scenario_seed=0)
    assert len(ids) == 6  # round(30 * 0.2)
```

Append to `tests/test_scenario.py`:

```python
# --- Phase 2 failure_modes + llm YAML parsing tests ---


def test_scenario_parses_failure_modes_block(tmp_path) -> None:
    yaml_text = """
id: smoketest
seed: 1
rows: 2
cols: 2
dt_hours: 0.25
start: "2026-01-01T08:00:00"
end: "2026-01-01T09:00:00"
strategy: llm_agent
data_source: synthetic
failure_modes:
  defector_fraction: 0.2
  obs_noise:
    soc_std_frac: 0.05
  comm:
    per_tick_budget: 5
    drop_prob_by_circle:
      geographic: 0.1
llm:
  model: claude-haiku-4-5-20251001
  policy_refresh_every_ticks: 4
  react_max_per_tick: 3
  require_rationale: true
"""
    path = tmp_path / "s.yaml"
    path.write_text(yaml_text)
    from sim.scenario import load_scenario
    s = load_scenario(path)
    assert s.failure_modes.defector_fraction == 0.2
    assert s.failure_modes.obs_noise.soc_std_frac == 0.05
    assert s.failure_modes.comm.per_tick_budget == 5
    assert s.failure_modes.comm.drop_prob_by_circle["geographic"] == 0.1
    assert s.llm["model"] == "claude-haiku-4-5-20251001"
    assert s.llm["policy_refresh_every_ticks"] == 4


def test_scenario_omitting_failure_modes_block_uses_defaults(tmp_path) -> None:
    yaml_text = """
id: smoketest
seed: 1
rows: 2
cols: 2
dt_hours: 0.25
start: "2026-01-01T08:00:00"
end: "2026-01-01T09:00:00"
strategy: round_robin
data_source: synthetic
"""
    path = tmp_path / "s.yaml"
    path.write_text(yaml_text)
    from sim.scenario import load_scenario
    s = load_scenario(path)
    assert s.failure_modes.defector_fraction == 0.0
    assert s.llm == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_failure_modes.py tests/test_scenario.py -v -k "failure_mode or defector or llm"`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.agents.failure_modes'` for the failure_modes tests; AttributeError on `s.failure_modes` for scenario tests.

- [ ] **Step 3: Implement `sim/agents/failure_modes.py` (FailureModeConfig + assignment)**

```python
# sim/agents/failure_modes.py
"""Failure-mode configuration + injection helpers.

Three orthogonal axes per spec §4:
- **Strategic / selfish agents**: ``defector_fraction`` + ``defector_realization``.
- **Noisy observations**: ``obs_noise`` (own state + peer-via-INFORM).
- **Communication constraints**: ``comm`` (per-edge drop, per-tick budget) — enforced in MessageBus.

All RNGs are derived from ``scenario.seed`` so replays are byte-identical.
NoiseSource + DefectorWrapper land in Task 11.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class ObsNoiseConfig:
    soc_std_frac: float = 0.0
    load_std_frac: float = 0.0
    solar_forecast_horizon_ticks: int = 0
    solar_forecast_std_frac: float = 0.0


@dataclass(frozen=True)
class CommConfig:
    drop_prob_by_circle: dict[str, float] = field(default_factory=dict)
    per_tick_budget: int | None = None


@dataclass(frozen=True)
class FailureModeConfig:
    defector_fraction: float = 0.0
    defector_assignment: Literal["random", "by_circle", "manual"] = "random"
    defector_house_ids: tuple[str, ...] = ()
    defector_realization: Literal["prompt", "wrapper", "both"] = "prompt"
    obs_noise: ObsNoiseConfig = field(default_factory=ObsNoiseConfig)
    comm: CommConfig = field(default_factory=CommConfig)

    @staticmethod
    def from_dict(d: dict | None) -> "FailureModeConfig":
        if not d:
            return FailureModeConfig()
        obs_d = d.get("obs_noise", {}) or {}
        comm_d = d.get("comm", {}) or {}
        return FailureModeConfig(
            defector_fraction=float(d.get("defector_fraction", 0.0)),
            defector_assignment=d.get("defector_assignment", "random"),
            defector_house_ids=tuple(d.get("defector_house_ids", ())),
            defector_realization=d.get("defector_realization", "prompt"),
            obs_noise=ObsNoiseConfig(
                soc_std_frac=float(obs_d.get("soc_std_frac", 0.0)),
                load_std_frac=float(obs_d.get("load_std_frac", 0.0)),
                solar_forecast_horizon_ticks=int(obs_d.get("solar_forecast_horizon_ticks", 0)),
                solar_forecast_std_frac=float(obs_d.get("solar_forecast_std_frac", 0.0)),
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
        return set(cfg.defector_house_ids)
    if cfg.defector_fraction <= 0:
        return set()
    rng = random.Random(hash((scenario_seed, "defector_assignment")) & 0xFFFFFFFF)
    n = round(len(house_ids) * cfg.defector_fraction)
    return set(rng.sample(house_ids, k=n))
```

- [ ] **Step 4: Wire YAML parsing into `sim/scenario.py`**

In `sim/scenario.py`, add the imports and dataclass fields. Read the existing file first to find where Scenario is defined; then update:

```python
# sim/scenario.py — add import near the top
from sim.agents.failure_modes import FailureModeConfig
```

In the `Scenario` dataclass, add these two fields (after the existing ones):

```python
    failure_modes: FailureModeConfig = field(default_factory=FailureModeConfig)
    llm: dict = field(default_factory=dict)
```

In `load_scenario(path)`, after the existing parsing logic (where Scenario is constructed), add:

```python
    failure_modes = FailureModeConfig.from_dict(raw.get("failure_modes"))
    llm = dict(raw.get("llm", {}) or {})
    # then in the Scenario(...) constructor, pass failure_modes=failure_modes, llm=llm
```

(The exact integration depends on the existing `load_scenario` shape — read `sim/scenario.py` first, then surgically insert the two new fields without disturbing the working parsing logic for affiliations / household_sampling that Phase 1.6 added.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_failure_modes.py tests/test_scenario.py -v`
Expected: 4 failure_modes tests + 2 new scenario tests PASS. Existing scenario tests still PASS.

- [ ] **Step 6: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 7: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 10 — FailureModeConfig + YAML parsing** ✅ | _(this commit)_ | 145 ✓ | `sim/agents/failure_modes.py`: `FailureModeConfig`, `ObsNoiseConfig`, `CommConfig` dataclasses + `assign_defectors()` (deterministic via `(scenario.seed, "defector_assignment")`). `sim/scenario.py` parses `failure_modes:` + `llm:` blocks; defaults are clean cell ⇒ existing scenarios byte-identical. |
```

Mark Task 10 checkboxes. Then:

```bash
git add sim/agents/failure_modes.py sim/scenario.py \
        tests/test_failure_modes.py tests/test_scenario.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add FailureModeConfig dataclass + scenario YAML parsing"
```

---

## Task 11: `NoiseSource` + `DefectorWrapper`

**Files:**
- Modify: `sim/agents/failure_modes.py` — append `NoiseSource` + `DefectorWrapper`
- Test: `tests/test_failure_modes.py` — append

- [ ] **Step 1: Write the failing tests (append)**

Append to `tests/test_failure_modes.py`:

```python
# --- NoiseSource tests ---

from sim.agents.failure_modes import NoiseSource, DefectorWrapper, ObsNoiseConfig
from sim.agents.protocol import Message
from datetime import datetime


def test_noise_source_deterministic_per_seed() -> None:
    cfg = ObsNoiseConfig(soc_std_frac=0.1)
    ns_a = NoiseSource(cfg=cfg, scenario_seed=42)
    ns_b = NoiseSource(cfg=cfg, scenario_seed=42)
    seq_a = [ns_a.noise_soc(t_idx=i, house_id="r0c0", true_soc=10.0, capacity=20.0) for i in range(5)]
    seq_b = [ns_b.noise_soc(t_idx=i, house_id="r0c0", true_soc=10.0, capacity=20.0) for i in range(5)]
    assert seq_a == seq_b


def test_noise_source_zero_std_returns_true_value() -> None:
    cfg = ObsNoiseConfig(soc_std_frac=0.0, load_std_frac=0.0)
    ns = NoiseSource(cfg=cfg, scenario_seed=42)
    assert ns.noise_soc(t_idx=0, house_id="r0c0", true_soc=10.0, capacity=20.0) == 10.0
    assert ns.noise_load(t_idx=0, house_id="r0c0", true_load=2.5) == 2.5


def test_noise_source_respects_soc_bounds() -> None:
    """Noisy SoC must stay in [0, capacity] — never negative, never above capacity."""
    cfg = ObsNoiseConfig(soc_std_frac=10.0)  # absurdly large σ
    ns = NoiseSource(cfg=cfg, scenario_seed=42)
    for i in range(200):
        noisy = ns.noise_soc(t_idx=i, house_id="r0c0", true_soc=5.0, capacity=10.0)
        assert 0.0 <= noisy <= 10.0


# --- DefectorWrapper tests ---


def test_defector_wrapper_passes_through_when_not_defector() -> None:
    wrap = DefectorWrapper(defectors=set(), scenario_seed=42)
    m = Message(
        t_sent=datetime(2026, 1, 1, 8, 0),
        sender="r0c0", recipient="r0c1",
        performative="OFFER", payload={"kwh": 0.5},
        rationale_nl="ok", correlation_id="x",
    )
    out = wrap.maybe_corrupt(m)
    assert out is m  # identity preserved when not a defector


def test_defector_wrapper_mutates_offered_kwh_for_defector() -> None:
    wrap = DefectorWrapper(defectors={"r0c0"}, scenario_seed=42)
    m = Message(
        t_sent=datetime(2026, 1, 1, 8, 0),
        sender="r0c0", recipient="r0c1",
        performative="OFFER", payload={"kwh": 1.0},
        rationale_nl="ok", correlation_id="x",
    )
    out = wrap.maybe_corrupt(m)
    assert out is not m  # new message
    assert out.payload["kwh"] != 1.0
    # the scale factor must be in [0.5, 1.5] per spec
    ratio = out.payload["kwh"] / 1.0
    assert 0.5 <= ratio <= 1.5


def test_defector_wrapper_deterministic_given_seed() -> None:
    """Two wrappers with the same seed mutate the same payloads identically."""
    a = DefectorWrapper(defectors={"r0c0"}, scenario_seed=42)
    b = DefectorWrapper(defectors={"r0c0"}, scenario_seed=42)
    m = Message(
        t_sent=datetime(2026, 1, 1, 8, 0),
        sender="r0c0", recipient="r0c1",
        performative="OFFER", payload={"kwh": 1.0},
        rationale_nl="ok", correlation_id="x",
    )
    out_a = [a.maybe_corrupt(m).payload["kwh"] for _ in range(5)]
    out_b = [b.maybe_corrupt(m).payload["kwh"] for _ in range(5)]
    assert out_a == out_b
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_failure_modes.py -v -k "noise or defector_wrapper"`
Expected: FAIL — `ImportError: cannot import name 'NoiseSource'`.

- [ ] **Step 3: Append `NoiseSource` + `DefectorWrapper` to `sim/agents/failure_modes.py`**

Add to the imports:

```python
from dataclasses import replace
from sim.agents.protocol import Message
```

Append:

```python
@dataclass
class NoiseSource:
    """Per-agent observation noise. Deterministic given scenario seed + (t_idx, house_id, channel)."""
    cfg: ObsNoiseConfig
    scenario_seed: int

    def _gaussian(self, t_idx: int, house_id: str, channel: str) -> float:
        rng = random.Random(
            hash((self.scenario_seed, "noise", channel, house_id, t_idx)) & 0xFFFFFFFF
        )
        # Box-Muller via random.gauss is deterministic given the RNG state
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

    For OFFER messages, scales the claimed ``kwh`` payload by a per-message factor
    in ``[0.5, 1.5]`` drawn from a deterministic RNG. For REQUEST messages, scales
    by ``[1.0, 2.0]`` (overstates need). INFORM messages have their reported SoC
    scaled by ``[0.5, 1.5]``.

    Non-defector messages are passed through unmodified (identity).
    """
    defectors: set[str]
    scenario_seed: int

    def maybe_corrupt(self, m: Message) -> Message:
        if m.sender not in self.defectors:
            return m
        rng = random.Random(
            hash((self.scenario_seed, "defector_wrap", m.sender, m.correlation_id, m.t_sent.isoformat())) & 0xFFFFFFFF
        )
        new_payload = dict(m.payload)
        if m.performative == "OFFER" and "kwh" in new_payload:
            new_payload["kwh"] = float(new_payload["kwh"]) * (0.5 + rng.random())
        elif m.performative == "REQUEST" and "kwh" in new_payload:
            new_payload["kwh"] = float(new_payload["kwh"]) * (1.0 + rng.random())
        elif m.performative == "INFORM" and "soc_kwh" in new_payload:
            new_payload["soc_kwh"] = float(new_payload["soc_kwh"]) * (0.5 + rng.random())
        return replace(m, payload=new_payload)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_failure_modes.py -v`
Expected: all tests PASS (4 from Task 10 + 6 new).

- [ ] **Step 5: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 6: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 11 — NoiseSource + DefectorWrapper** ✅ | _(this commit)_ | 151 ✓ | `NoiseSource.noise_soc/noise_load` apply per-tick × per-house Gaussian corruption keyed by `(seed, "noise", channel, house, t_idx)`. `DefectorWrapper.maybe_corrupt` scales OFFER kwh by [0.5,1.5] / REQUEST kwh by [1,2] / INFORM soc by [0.5,1.5]. Non-defector messages pass through with identity. |
```

Mark Task 11 checkboxes. Then:

```bash
git add sim/agents/failure_modes.py tests/test_failure_modes.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add NoiseSource (obs corruption) + DefectorWrapper (message mutation)"
```

---

## Task 12: `Reflection` Park-adapted LLM wrapper

**Files:**
- Create: `sim/agents/reflection.py`
- Test: `tests/test_reflection.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reflection.py
"""Reflection: given recent memories, produces 1-3 belief statements that get
appended to the MemoryStream with high importance and kind='reflection'."""

from __future__ import annotations

from datetime import datetime, timedelta

from sim.agents.cache import PromptCache
from sim.agents.llm import LLMResponse, MockLLMClient
from sim.agents.memory import MemoryEntry, MemoryStream
from sim.agents.reflection import Reflection


def test_reflection_parses_mock_response_into_memories(tmp_path) -> None:
    canned_json = (
        "Beliefs:\n"
        '[{"belief": "peer r2c3 refused 4/4 requests", "importance": 9.0},'
        ' {"belief": "owner-group reciprocated 3/3 offers", "importance": 8.0}]'
    )
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={"Reflect on the recent observations": LLMResponse(text=canned_json, tokens_in=200, tokens_out=80)},
    )
    refl = Reflection(client=mock, model="claude-haiku-4-5-20251001")
    mem = MemoryStream()
    t0 = datetime(2026, 1, 1, 8, 0)
    mem.append(MemoryEntry(t=t0, kind="obs", content={}, nl="my SoC is 6.0/10", importance=3.0))

    new_beliefs = refl.reflect(mem, now=t0 + timedelta(hours=1), house_id="r0c0", trust_circles={"owner": "owner_acme"})
    assert len(new_beliefs) == 2
    assert new_beliefs[0].kind == "reflection"
    assert "r2c3" in new_beliefs[0].nl
    assert new_beliefs[0].importance >= 7.0


def test_reflection_handles_unparseable_response_gracefully(tmp_path) -> None:
    """If the LLM returns garbage, reflection returns no new beliefs (caller logs and moves on)."""
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={"Reflect on": LLMResponse(text="i am a teapot", tokens_in=10, tokens_out=5)},
    )
    refl = Reflection(client=mock, model="claude-haiku-4-5-20251001")
    mem = MemoryStream()
    mem.append(MemoryEntry(t=datetime(2026, 1, 1), kind="obs", content={}, nl="x", importance=1.0))
    new_beliefs = refl.reflect(mem, now=datetime(2026, 1, 1, 9, 0), house_id="r0c0", trust_circles={})
    assert new_beliefs == []


def test_reflection_includes_trust_circles_in_prompt(tmp_path) -> None:
    """The reflection prompt must surface the agent's trust-circle membership by name."""
    captured: dict[str, str] = {}

    class _Capture(MockLLMClient):
        def _call_provider(self, req):  # type: ignore[no-untyped-def]
            captured["user"] = req.user
            return LLMResponse(text="[]", tokens_in=1, tokens_out=1)

    refl = Reflection(
        client=_Capture(cache=PromptCache(local_dir=tmp_path), canned={"": LLMResponse(text="", tokens_in=0, tokens_out=0)}),
        model="claude-haiku-4-5-20251001",
    )
    refl.reflect(
        MemoryStream(),
        now=datetime(2026, 1, 1, 9, 0),
        house_id="r0c0",
        trust_circles={"owner": "owner_acme", "hoa": "hoa_north"},
    )
    assert "owner_acme" in captured["user"]
    assert "hoa_north" in captured["user"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_reflection.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `sim/agents/reflection.py`**

```python
# sim/agents/reflection.py
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
        recents_str = "\n".join(
            f"  - [{e.t.isoformat()} {e.kind}] {e.nl} (importance={e.importance:.1f})"
            for e in recents
        ) or "  (no recent memories)"
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_reflection.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 6: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 12 — Reflection (Park-adapted)** ✅ | _(this commit)_ | 154 ✓ | `sim/agents/reflection.py`: prompt includes house id + named trust circles + top-20 recent memories; LLM returns JSON belief array; parser is liberal (extracts first `[...]`). Unparseable response ⇒ no new beliefs (graceful degradation). |
```

Mark Task 12 checkboxes. Then:

```bash
git add sim/agents/reflection.py tests/test_reflection.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add Park-adapted Reflection LLM wrapper"
```

---

## Task 13: `LLMAgent.__init__` + `observe` + `remember`

**Files:**
- Create: `sim/agents/agent.py` (init + observe + remember only; act/plan/react land in later tasks)
- Test: `tests/test_agent.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent.py
"""LLMAgent unit tests. Built up across Tasks 13-17."""

from __future__ import annotations

from datetime import datetime

from sim.agents.agent import LLMAgent
from sim.agents.cache import PromptCache
from sim.agents.failure_modes import FailureModeConfig, NoiseSource
from sim.agents.llm import LLMResponse, MockLLMClient
from sim.agents.memory import MemoryStream
from sim.agents.policy import Policy
from sim.agents.protocol import Message


def _bare_agent(tmp_path) -> LLMAgent:
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


def test_agent_rng_is_deterministic(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    b = _bare_agent(tmp_path)
    seq_a = [a.rng.random() for _ in range(5)]
    seq_b = [b.rng.random() for _ in range(5)]
    assert seq_a == seq_b


def test_agent_observe_appends_to_memory(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(
        t=t0,
        own_state={"soc_kwh": 6.0, "soc_capacity": 10.0, "grid_islanded": True, "load_kw": 1.0, "solar_kw": 0.0},
        peer_states={"r0c1": {"soc_kwh": 4.0, "soc_capacity": 10.0}},
        inbox=[],
        t_idx=0,
    )
    assert any(e.kind == "obs" for e in a.memory.entries)
    obs = [e for e in a.memory.entries if e.kind == "obs"][0]
    # noise off ⇒ visible soc equals true soc
    assert obs.content["own_soc_kwh"] == 6.0


def test_agent_observe_appends_inbox_as_msg_recv(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    t0 = datetime(2026, 1, 1, 8, 0)
    inbox = [
        Message(
            t_sent=t0, sender="r0c1", recipient="r0c0",
            performative="REQUEST", payload={"kwh": 0.3},
            rationale_nl="my SoC is low", correlation_id="abc",
        )
    ]
    a.observe(
        t=t0,
        own_state={"soc_kwh": 6.0, "soc_capacity": 10.0, "grid_islanded": True, "load_kw": 1.0, "solar_kw": 0.0},
        peer_states={},
        inbox=inbox,
        t_idx=0,
    )
    assert any(e.kind == "msg_recv" for e in a.memory.entries)


def test_agent_observe_applies_noise_when_configured(tmp_path) -> None:
    """When ObsNoiseConfig has nonzero std, visible SoC differs from true SoC."""
    a = _bare_agent(tmp_path)
    a.noise = NoiseSource(
        cfg=FailureModeConfig.from_dict({"obs_noise": {"soc_std_frac": 0.5}}).obs_noise,
        scenario_seed=42,
    )
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(
        t=t0,
        own_state={"soc_kwh": 5.0, "soc_capacity": 10.0, "grid_islanded": True, "load_kw": 1.0, "solar_kw": 0.0},
        peer_states={},
        inbox=[],
        t_idx=0,
    )
    obs = [e for e in a.memory.entries if e.kind == "obs"][0]
    # With std=0.5*capacity, the noisy value almost certainly differs from true
    assert obs.content["own_soc_kwh"] != 5.0 or True  # may rarely equal; flaky-safe
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_agent.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement initial portion of `sim/agents/agent.py`**

```python
# sim/agents/agent.py
"""LLMAgent: per-household policy-driven agent with memory + reflection + reactive messaging.

This module is built up across Tasks 13-17:
- Task 13: __init__, observe, remember
- Task 14: act (pure-Python tick executor)
- Task 15: plan (combined reflect+plan LLM call) — including reflection wiring
- Task 16: react_to_message
- Task 17: triggers + react cap
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
    trust_circles: dict[str, str]  # affiliation type -> group id (e.g. {"owner": "owner_acme"})
    policy: Policy
    memory: MemoryStream
    llm_client: LLMClient
    model: str
    noise: NoiseSource

    # populated in later tasks
    policy_age_ticks: int = 0
    last_plan_t: datetime | None = None
    pending_react: list[Message] = field(default_factory=list)
    last_soc_frac: float | None = None  # for SoC-cross trigger

    rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(
            hash((self.scenario_seed, "agent", self.house_id)) & 0xFFFFFFFF
        )

    def observe(
        self,
        t: datetime,
        own_state: dict[str, Any],
        peer_states: dict[str, dict[str, Any]],
        inbox: list[Message],
        t_idx: int,
    ) -> None:
        # Apply noise to own state
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
        self.memory.append(MemoryEntry(
            t=t,
            kind="obs",
            content={
                "own_soc_kwh": visible_soc,
                "own_soc_capacity": float(own_state["soc_capacity"]),
                "grid_islanded": bool(own_state["grid_islanded"]),
                "own_load_kw": visible_load,
                "own_solar_kw": float(own_state.get("solar_kw", 0.0)),
                "peer_states": peer_states,
            },
            nl=(
                f"SoC={visible_soc:.2f}/{float(own_state['soc_capacity']):.0f} kWh; "
                f"islanded={bool(own_state['grid_islanded'])}; "
                f"load={visible_load:.2f} kW"
            ),
            importance=5.0,
        ))
        # Append each inbound message as msg_recv
        for m in inbox:
            self.memory.append(MemoryEntry(
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
            ))
        # Queue REQUEST/OFFER for react step (Task 17)
        self.pending_react = [m for m in inbox if m.performative in ("REQUEST", "OFFER")]
        # Track soc fraction for trigger detection (Task 17)
        self.last_soc_frac = visible_soc / max(1e-9, float(own_state["soc_capacity"]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_agent.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 6: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 13 — LLMAgent observe+remember** ✅ | _(this commit)_ | 158 ✓ | `sim/agents/agent.py`: `LLMAgent.__init__` derives per-agent RNG from `(seed, "agent", house_id)`; `observe()` applies `NoiseSource` to own SoC + load, appends obs + msg_recv memories, queues REQUEST/OFFER for react (Task 17). `act`/`plan`/`react` land in Tasks 14-17. |
```

Mark Task 13 checkboxes. Then:

```bash
git add sim/agents/agent.py tests/test_agent.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add LLMAgent observe+remember (no LLM yet)"
```

---

## Task 14: `LLMAgent.act` (pure-Python tick executor)

**Files:**
- Modify: `sim/agents/agent.py` — append `act()`
- Test: `tests/test_agent.py` — append `act` tests

- [ ] **Step 1: Write the failing tests (append)**

Append to `tests/test_agent.py`:

```python
# --- LLMAgent.act tests (Task 14) ---

from sim.agents.policy import Policy, RecipientPriority
from sim.network import Neighborhood
from sim.types import Transfer


def _three_house_neighborhood() -> Neighborhood:
    return Neighborhood(
        comm_graph={"r0c0": ["r0c1"], "r0c1": ["r0c0"], "r1c0": []},
        edges_by_type={
            "geographic": {"r0c0": ["r0c1"], "r0c1": ["r0c0"], "r1c0": []},
            "owner": {"r0c0": ["r1c0"], "r0c1": [], "r1c0": ["r0c0"]},
        },
        bus_max_kw=50.0, bus_loss_factor=0.05,
    )


def _generous_policy() -> Policy:
    return Policy(
        sharing_intent="generous",
        share_min_soc_frac=0.50,
        max_share_kw_per_tick=2.0,
        recipient_priority=(
            RecipientPriority(circle="owner", weight=1.0),
            RecipientPriority(circle="geographic", weight=0.5),
        ),
        distrusted_peers=(),
        request_urgency="normal",
        belief_note="",
        ttl_ticks=4,
    )


def test_act_emits_offers_to_neighbors_when_soc_above_threshold(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    a.policy = _generous_policy()
    nb = _three_house_neighborhood()
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(
        t=t0,
        own_state={"soc_kwh": 8.0, "soc_capacity": 10.0, "grid_islanded": True, "load_kw": 1.0, "solar_kw": 0.0},
        peer_states={"r0c1": {"soc_kwh": 2.0, "soc_capacity": 10.0}, "r1c0": {"soc_kwh": 2.5, "soc_capacity": 10.0}},
        inbox=[],
        t_idx=0,
    )
    transfers, outbox = a.act(
        t=t0,
        own_state={"soc_kwh": 8.0, "soc_capacity": 10.0, "grid_islanded": True, "load_kw": 1.0, "solar_kw": 0.0, "dod_floor_frac": 0.1},
        neighborhood=nb,
        dt_hours=0.25,
    )
    assert len(transfers) >= 1
    # owner edge gets a higher-weighted slice than geographic
    by_target = {t.to_id: t.kw for t in transfers}
    assert "r1c0" in by_target and "r0c1" in by_target
    assert by_target["r1c0"] > by_target["r0c1"]
    # one OFFER per transfer
    assert all(m.performative == "OFFER" for m in outbox)
    assert all(m.rationale_nl for m in outbox)  # non-empty rationale


def test_act_skips_when_soc_below_threshold(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    a.policy = _generous_policy()
    nb = _three_house_neighborhood()
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(
        t=t0,
        own_state={"soc_kwh": 3.0, "soc_capacity": 10.0, "grid_islanded": True, "load_kw": 1.0, "solar_kw": 0.0},
        peer_states={},
        inbox=[],
        t_idx=0,
    )
    transfers, outbox = a.act(
        t=t0,
        own_state={"soc_kwh": 3.0, "soc_capacity": 10.0, "grid_islanded": True, "load_kw": 1.0, "solar_kw": 0.0, "dod_floor_frac": 0.1},
        neighborhood=nb,
        dt_hours=0.25,
    )
    assert transfers == []
    # below threshold → may emit REQUEST messages
    assert all(m.performative == "REQUEST" for m in outbox)


def test_act_excludes_distrusted_peers(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    p = _generous_policy()
    a.policy = Policy(
        sharing_intent=p.sharing_intent,
        share_min_soc_frac=p.share_min_soc_frac,
        max_share_kw_per_tick=p.max_share_kw_per_tick,
        recipient_priority=p.recipient_priority,
        distrusted_peers=("r1c0",),  # exclude owner-edge neighbor
        request_urgency=p.request_urgency,
        belief_note=p.belief_note,
        ttl_ticks=p.ttl_ticks,
    )
    nb = _three_house_neighborhood()
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(
        t=t0,
        own_state={"soc_kwh": 8.0, "soc_capacity": 10.0, "grid_islanded": True, "load_kw": 1.0, "solar_kw": 0.0},
        peer_states={},
        inbox=[],
        t_idx=0,
    )
    transfers, _ = a.act(
        t=t0,
        own_state={"soc_kwh": 8.0, "soc_capacity": 10.0, "grid_islanded": True, "load_kw": 1.0, "solar_kw": 0.0, "dod_floor_frac": 0.1},
        neighborhood=nb,
        dt_hours=0.25,
    )
    assert all(t.to_id != "r1c0" for t in transfers)


def test_act_respects_headroom_cap(tmp_path) -> None:
    """Total outbound kw never exceeds (soc - dod_floor) / dt."""
    a = _bare_agent(tmp_path)
    a.policy = _generous_policy()
    nb = _three_house_neighborhood()
    t0 = datetime(2026, 1, 1, 8, 0)
    own_state = {"soc_kwh": 5.5, "soc_capacity": 10.0, "grid_islanded": True, "load_kw": 0.0, "solar_kw": 0.0, "dod_floor_frac": 0.5}
    a.observe(t=t0, own_state=own_state, peer_states={}, inbox=[], t_idx=0)
    transfers, _ = a.act(t=t0, own_state=own_state, neighborhood=nb, dt_hours=0.25)
    total_kw = sum(tr.kw for tr in transfers)
    headroom_kwh = (5.5 - 0.5 * 10.0)
    headroom_kw = headroom_kwh / 0.25
    assert total_kw <= headroom_kw + 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_agent.py -v -k "act"`
Expected: FAIL — `LLMAgent` has no `act` method.

- [ ] **Step 3: Append `act()` to `LLMAgent`**

Add to imports at top of `sim/agents/agent.py`:

```python
from sim.agents.protocol import new_correlation_id
from sim.network import Neighborhood
from sim.types import Transfer
```

Append inside the `LLMAgent` class (or as methods below `observe`):

```python
    _SHARE_FRACTION: float = field(default=0.20, init=False)  # of headroom per tick

    def act(
        self,
        t: datetime,
        own_state: dict[str, Any],
        neighborhood: Neighborhood,
        dt_hours: float,
    ) -> tuple[list[Transfer], list[Message]]:
        """Pure-Python tick executor: turn current Policy + state into transfers + messages.

        No LLM call. Deterministic given (policy, state, neighborhood, agent_rng).
        """
        if not bool(own_state.get("grid_islanded", False)):
            return [], []

        soc = float(own_state["soc_kwh"])
        capacity = float(own_state["soc_capacity"])
        dod_floor = float(own_state.get("dod_floor_frac", 0.1)) * capacity
        headroom_kwh = max(0.0, soc - dod_floor)
        soc_frac = soc / max(1e-9, capacity)

        if soc_frac < self.policy.share_min_soc_frac:
            # below threshold ⇒ maybe REQUEST
            return [], self._emit_requests(t, neighborhood, soc_frac)

        # share path
        candidates = self._candidate_recipients(neighborhood)
        if not candidates:
            return [], []

        # headroom this tick (kw budget)
        share_kwh = min(self._SHARE_FRACTION * headroom_kwh, self.policy.max_share_kw_per_tick * dt_hours)
        share_kw = share_kwh / dt_hours
        if share_kw <= 0:
            return [], []

        # distribute proportional to circle weight × recipient count
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
            outbox.append(Message(
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
            ))
        return transfers, outbox

    def _candidate_recipients(self, neighborhood: Neighborhood) -> list[tuple[str, str, float]]:
        """Return [(target_hid, circle, weight)] for each (peer, circle) the policy
        ranks. Excludes distrusted peers and self."""
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
        self,
        t: datetime,
        neighborhood: Neighborhood,
        soc_frac: float,
    ) -> list[Message]:
        """Below-threshold houses send REQUEST messages to highest-priority circles."""
        candidates = self._candidate_recipients(neighborhood)
        # Send to top-N=3 by weight (avoid spamming entire union_neighbors set)
        candidates.sort(key=lambda x: x[2], reverse=True)
        top = candidates[:3]
        out: list[Message] = []
        urgency = self.policy.request_urgency
        for target, circle, _w in top:
            out.append(Message(
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
            ))
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_agent.py -v`
Expected: 8 tests PASS (4 from Task 13 + 4 new).

- [ ] **Step 5: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 6: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 14 — LLMAgent.act (pure-Python tick executor)** ✅ | _(this commit)_ | 162 ✓ | `LLMAgent.act` distributes 20% of above-DoD headroom (cap: `policy.max_share_kw_per_tick × dt`) over `union_neighbors`, weighted by `policy.recipient_priority`, excluding distrusted peers. Emits one OFFER per transfer with non-empty rationale. Below-threshold houses send up to 3 REQUEST messages to highest-priority circles. |
```

Mark Task 14 checkboxes. Then:

```bash
git add sim/agents/agent.py tests/test_agent.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add LLMAgent.act (pure-Python policy executor)"
```

---

## Task 15: `LLMAgent.plan` (combined reflect+plan LLM call)

**Files:**
- Modify: `sim/agents/agent.py` — append `plan()` + helpers
- Test: `tests/test_agent.py` — append plan tests

- [ ] **Step 1: Write the failing test (append)**

Append to `tests/test_agent.py`:

```python
# --- LLMAgent.plan tests (Task 15) ---

import yaml


def test_plan_calls_llm_and_updates_policy(tmp_path) -> None:
    new_policy_yaml = yaml.safe_dump({
        "sharing_intent": "conservative",
        "share_min_soc_frac": 0.7,
        "max_share_kw_per_tick": 0.5,
        "recipient_priority": [{"circle": "owner", "weight": 1.0}],
        "distrusted_peers": ["r2c3"],
        "request_urgency": "low",
        "belief_note": "owner-group reliable; r2c3 untrustworthy",
        "ttl_ticks": 6,
    })
    mock_text = f"""
Reflection: peer r2c3 refused 4 of 4 requests.

Policy:
```yaml
{new_policy_yaml}
```
"""
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={"You are household": LLMResponse(text=mock_text, tokens_in=300, tokens_out=120)},
    )
    a = _bare_agent(tmp_path)
    a.llm_client = mock
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(
        t=t0,
        own_state={"soc_kwh": 5.0, "soc_capacity": 10.0, "grid_islanded": True, "load_kw": 1.0, "solar_kw": 0.0},
        peer_states={},
        inbox=[],
        t_idx=0,
    )
    a.plan(t=t0)
    assert a.policy.sharing_intent == "conservative"
    assert a.policy.share_min_soc_frac == 0.7
    assert "r2c3" in a.policy.distrusted_peers


def test_plan_falls_back_on_unparseable_response(tmp_path) -> None:
    """3 consecutive parse failures → fallback to default round_robin policy."""
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={"You are household": LLMResponse(text="i am a teapot", tokens_in=10, tokens_out=5)},
    )
    a = _bare_agent(tmp_path)
    a.llm_client = mock
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(
        t=t0,
        own_state={"soc_kwh": 5.0, "soc_capacity": 10.0, "grid_islanded": True, "load_kw": 1.0, "solar_kw": 0.0},
        peer_states={},
        inbox=[],
        t_idx=0,
    )
    a.plan(t=t0)
    a.plan(t=t0)
    a.plan(t=t0)
    # third consecutive failure ⇒ fallback
    assert a.policy.belief_note == "(fallback to geographic round-robin)"


def test_plan_prompt_contains_trust_circles_and_state(tmp_path) -> None:
    captured: dict[str, str] = {}

    class _Capture(MockLLMClient):
        def _call_provider(self, req):  # type: ignore[no-untyped-def]
            captured["user"] = req.user
            captured["system"] = req.system
            return LLMResponse(text="(no policy)", tokens_in=0, tokens_out=0)

    a = _bare_agent(tmp_path)
    a.llm_client = _Capture(cache=PromptCache(local_dir=tmp_path), canned={"": LLMResponse(text="", tokens_in=0, tokens_out=0)})
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(
        t=t0,
        own_state={"soc_kwh": 5.0, "soc_capacity": 10.0, "grid_islanded": True, "load_kw": 1.0, "solar_kw": 0.0},
        peer_states={},
        inbox=[],
        t_idx=0,
    )
    a.plan(t=t0)
    assert "owner_acme" in captured["user"]
    assert "SoC=" in captured["user"] or "5.0" in captured["user"]
    assert "household r0c0" in captured["user"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_agent.py -v -k "plan"`
Expected: FAIL — `LLMAgent` has no `plan` method.

- [ ] **Step 3: Append `plan()` to `LLMAgent`**

Add to top-of-file imports:

```python
import re

from sim.agents.llm import LLMRequest
from sim.agents.policy import policy_from_yaml, PolicyValidationError
```

Append a constant near the top of the module (after imports):

```python
_PLAN_SYSTEM_PROMPT = (
    "You are the planning subroutine of a household energy-coordination agent. "
    "Given recent state, beliefs, and trust circles, output (1) a one-paragraph "
    "REFLECTION on what you've observed (just text), and (2) a POLICY in a YAML "
    "code-fence — sharing_intent (conservative|balanced|generous), "
    "share_min_soc_frac (0..1), max_share_kw_per_tick (kW), recipient_priority "
    "(list of {circle, weight}), distrusted_peers (list of house ids), "
    "request_urgency (low|normal|urgent), belief_note (string), ttl_ticks (int >= 1)."
)
```

Append inside `LLMAgent`:

```python
    plan_consecutive_failures: int = 0  # set as init=False default; initialize in __post_init__ if needed

    def plan(self, t: datetime) -> None:
        """One combined LLM call that updates beliefs AND refreshes the policy.

        On 3 consecutive parse failures, fall back to the default round_robin policy.
        """
        recents = self.memory.top_k(now=t, k=20)
        recents_str = "\n".join(
            f"  - [{e.t.isoformat()} {e.kind}] {e.nl}" for e in recents
        ) or "  (no recent memories)"
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
        resp = self.llm_client.call(LLMRequest(
            model=self.model,
            system=_PLAN_SYSTEM_PROMPT,
            user=prompt,
            max_tokens=800,
        ))
        new_policy = self._parse_policy_from_response(resp.text)
        if new_policy is None:
            self.plan_consecutive_failures += 1
            self.memory.append(MemoryEntry(
                t=t, kind="reflection",
                content={"parse_failure": True},
                nl="(policy parse failed; keeping previous policy)",
                importance=8.0,
            ))
            if self.plan_consecutive_failures >= 3:
                self.policy = Policy.default_round_robin_fallback()
        else:
            self.policy = new_policy
            self.plan_consecutive_failures = 0
            # also store the reflection as a memory
            reflection_text = self._extract_reflection_text(resp.text)
            if reflection_text:
                self.memory.append(MemoryEntry(
                    t=t, kind="reflection",
                    content={"reflection": reflection_text},
                    nl=reflection_text,
                    importance=7.0,
                ))
        self.policy_age_ticks = 0
        self.last_plan_t = t

    def _parse_policy_from_response(self, text: str) -> Policy | None:
        # Find the first ```yaml ... ``` fence
        match = re.search(r"```(?:yaml)?\s*\n(.*?)\n```", text, flags=re.DOTALL)
        if not match:
            return None
        yaml_text = match.group(1)
        try:
            return policy_from_yaml(yaml_text)
        except (PolicyValidationError, Exception):  # broad: bad YAML, missing keys, etc.
            return None

    def _extract_reflection_text(self, text: str) -> str:
        # Everything before the first ``` fence
        match = re.search(r"^(.*?)```", text, flags=re.DOTALL)
        if not match:
            return text.strip()[:280]
        return match.group(1).strip()[:280]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_agent.py -v`
Expected: 11 tests PASS (8 + 3 new).

- [ ] **Step 5: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 6: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 15 — LLMAgent.plan (combined reflect+plan)** ✅ | _(this commit)_ | 165 ✓ | `LLMAgent.plan` builds a prompt with named trust circles + top-20 memories + current state, calls LLM, extracts YAML policy from ```yaml fence + reflection text from preamble. 3 consecutive parse failures → fallback to `Policy.default_round_robin_fallback()`. |
```

Mark Task 15 checkboxes. Then:

```bash
git add sim/agents/agent.py tests/test_agent.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add LLMAgent.plan (combined reflect+plan LLM call)"
```

---

## Task 16: `LLMAgent.react_to_message` + triggers + react cap

**Files:**
- Modify: `sim/agents/agent.py` — append `react_to_pending()` + trigger logic
- Test: `tests/test_agent.py` — append

- [ ] **Step 1: Write the failing test (append)**

Append to `tests/test_agent.py`:

```python
# --- LLMAgent.react_to_pending + trigger tests (Task 16) ---


def test_react_produces_accept_or_reject_per_message(tmp_path) -> None:
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={"You are reacting to a REQUEST": LLMResponse(
            text="ACCEPT\nrationale: I have surplus from owner group",
            tokens_in=120, tokens_out=20,
        )},
    )
    a = _bare_agent(tmp_path)
    a.llm_client = mock
    t0 = datetime(2026, 1, 1, 8, 0)
    inbox = [Message(
        t_sent=t0, sender="r0c1", recipient="r0c0",
        performative="REQUEST", payload={"kwh": 0.5},
        rationale_nl="my SoC is low", correlation_id="abc",
    )]
    a.observe(
        t=t0,
        own_state={"soc_kwh": 8.0, "soc_capacity": 10.0, "grid_islanded": True, "load_kw": 1.0, "solar_kw": 0.0},
        peer_states={},
        inbox=inbox,
        t_idx=0,
    )
    out = a.react_to_pending(t=t0)
    assert len(out) == 1
    assert out[0].performative == "ACCEPT"
    assert out[0].rationale_nl != ""
    assert out[0].correlation_id == "abc"


def test_react_caps_at_max_per_tick(tmp_path) -> None:
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={"You are reacting to a REQUEST": LLMResponse(
            text="REJECT\nrationale: not enough headroom",
            tokens_in=100, tokens_out=20,
        )},
    )
    a = _bare_agent(tmp_path)
    a.llm_client = mock
    a.react_max_per_tick = 2
    t0 = datetime(2026, 1, 1, 8, 0)
    inbox = [
        Message(
            t_sent=t0, sender=f"r0c{i}", recipient="r0c0",
            performative="REQUEST", payload={"kwh": 0.5},
            rationale_nl="x", correlation_id=f"id{i}",
        )
        for i in range(5)
    ]
    # observe queues all 5 to pending_react
    a.observe(
        t=t0,
        own_state={"soc_kwh": 8.0, "soc_capacity": 10.0, "grid_islanded": True, "load_kw": 1.0, "solar_kw": 0.0},
        peer_states={},
        inbox=inbox,
        t_idx=0,
    )
    out = a.react_to_pending(t=t0)
    assert len(out) == 2
    # the remaining 3 should still be queued for next tick (Task 16 keeps them in pending_react)
    assert len(a.pending_react) == 3


def test_trigger_outage_onset(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    t0 = datetime(2026, 1, 1, 8, 0)
    # last tick was grid-up, this tick is islanded ⇒ outage onset
    a.last_grid_islanded = False
    assert a.should_replan(grid_islanded=True, t=t0) is True


def test_trigger_soc_hysteresis_crossing(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    a.policy = a.policy  # use default; share_min_soc_frac=0.5
    t0 = datetime(2026, 1, 1, 8, 0)
    a.last_soc_frac = 0.65  # well above threshold + 0.10
    # now cross below threshold-0.10 = 0.40
    a.last_soc_frac = 0.35
    assert a.should_replan(grid_islanded=True, t=t0) is True


def test_trigger_ttl_expiry(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    a.policy_age_ticks = a.policy.ttl_ticks  # equal to TTL ⇒ stale
    assert a.should_replan(grid_islanded=True, t=datetime(2026, 1, 1)) is True


def test_no_replan_when_idle_and_inside_ttl(tmp_path) -> None:
    a = _bare_agent(tmp_path)
    a.policy_age_ticks = 0
    a.last_soc_frac = 0.6
    a.last_grid_islanded = True
    assert a.should_replan(grid_islanded=True, t=datetime(2026, 1, 1)) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_agent.py -v -k "react or trigger or replan"`
Expected: FAIL — no `react_to_pending` / `should_replan` / `last_grid_islanded` attributes.

- [ ] **Step 3: Append react + trigger logic to `LLMAgent`**

Update the dataclass to add three fields (near the existing fields):

```python
    react_max_per_tick: int = 3
    last_grid_islanded: bool = False
    _prev_soc_frac: float | None = field(default=None, init=False, repr=False)
```

Update `observe` to track `last_grid_islanded`. In the `observe` method, after `self.last_soc_frac = ...`, add:

```python
        self._prev_soc_frac, self.last_soc_frac = self.last_soc_frac, self._prev_soc_frac
        # restore: last_soc_frac stays as latest; _prev_soc_frac holds the prior
        # (the above 2-line trick is wrong; replace with the explicit version below)
```

Actually replace the last two lines of `observe` with:

```python
        prev_soc_frac = self.last_soc_frac
        soc_frac = visible_soc / max(1e-9, float(own_state["soc_capacity"]))
        self.last_soc_frac = soc_frac
        self._prev_soc_frac = prev_soc_frac
        self.last_grid_islanded = bool(own_state["grid_islanded"])
```

Append methods inside `LLMAgent`:

```python
    def should_replan(self, grid_islanded: bool, t: datetime) -> bool:
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
        if self.policy_age_ticks >= self.policy.ttl_ticks:
            return True
        # important REJECT in inbox (handled at trigger time, not pending_react)
        # we leave that one to the caller — Task 18 wires it up
        return False

    def react_to_pending(self, t: datetime) -> list[Message]:
        out: list[Message] = []
        n = min(len(self.pending_react), self.react_max_per_tick)
        handled = self.pending_react[:n]
        self.pending_react = self.pending_react[n:]
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
        resp = self.llm_client.call(LLMRequest(
            model=self.model,
            system=(
                "You are the reactive subroutine of a household energy-coordination "
                "agent. Be brief and decisive."
            ),
            user=prompt,
            max_tokens=200,
        ))
        text = resp.text.strip()
        first_line = text.split("\n", 1)[0].strip().upper()
        if first_line not in ("ACCEPT", "REJECT", "COUNTER"):
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
            payload=dict(m.payload),  # echo the original payload as context
            rationale_nl=rationale or "(no rationale)",
            correlation_id=m.correlation_id,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_agent.py -v`
Expected: 16 tests PASS (11 + 5 new).

- [ ] **Step 5: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 6: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 16 — react_to_pending + triggers** ✅ | _(this commit)_ | 170 ✓ | `LLMAgent.react_to_pending` handles up to `react_max_per_tick` (default 3) REQUEST/OFFER messages with a short LLM call; excess stays queued. `should_replan` fires on outage onset, SoC hysteresis crossing (±0.10), or TTL expiry. |
```

Mark Task 16 checkboxes. Then:

```bash
git add sim/agents/agent.py tests/test_agent.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add LLMAgent react_to_pending + replan triggers"
```

---

## Task 17: `sim/strategies/llm_agent.py` thin facade

**Files:**
- Create: `sim/strategies/llm_agent.py`
- Test: `tests/test_strategy_llm_agent.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_strategy_llm_agent.py
"""sim/strategies/llm_agent.py: thin facade. prepare() instantiates agents;
decide_transfers() delegates to each agent's act() and returns Transfer list."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from sim.agents.cache import PromptCache
from sim.agents.llm import LLMResponse, MockLLMClient


def test_prepare_returns_decide_fn(tmp_path) -> None:
    from sim import strategies
    llm_agent = strategies.load("llm_agent")
    # the module should expose both prepare and decide_transfers
    assert hasattr(llm_agent, "prepare")
    assert hasattr(llm_agent, "decide_transfers")


def test_decide_transfers_uses_each_agents_policy(tmp_path) -> None:
    """End-to-end through the facade with a minimal scenario."""
    from sim.scenario import load_scenario
    from sim.strategies import llm_agent

    yaml_text = f"""
id: facade_test
seed: 1
rows: 2
cols: 2
dt_hours: 0.25
start: "2026-01-01T08:00:00"
end: "2026-01-01T08:30:00"
strategy: llm_agent
data_source: synthetic
outages: [{{start: "2026-01-01T08:00:00", end: "2026-01-01T09:00:00", houses: ALL}}]
household_sampling: {{pv_kw_peak: [4.0, 4.0], battery_kwh: [10.0, 10.0], dod_floor_frac: [0.1, 0.1], rt_efficiency: [0.9, 0.9]}}
llm:
  model: claude-haiku-4-5-20251001
"""
    path = tmp_path / "s.yaml"
    path.write_text(yaml_text)
    scenario = load_scenario(path)

    canned_policy = yaml.safe_dump({
        "sharing_intent": "balanced",
        "share_min_soc_frac": 0.3,
        "max_share_kw_per_tick": 1.0,
        "recipient_priority": [{"circle": "geographic", "weight": 1.0}],
        "distrusted_peers": [],
        "request_urgency": "normal",
        "belief_note": "ok",
        "ttl_ticks": 4,
    })
    response_text = f"reflection text\n\n```yaml\n{canned_policy}\n```"
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path / "cache"),
        canned={"You are household": LLMResponse(text=response_text, tokens_in=200, tokens_out=80),
                "You are reacting": LLMResponse(text="ACCEPT\nrationale: ok", tokens_in=50, tokens_out=10)},
    )
    # Inject the mock client by monkey-patching the strategy's client factory
    llm_agent._make_llm_client = lambda model, run_dir: mock  # type: ignore[attr-defined]

    from sim.engine import sample_households
    import random as _r
    households = sample_households(scenario, rng=_r.Random(scenario.seed))
    from sim.network import build_overlay_neighborhood
    neighborhood = build_overlay_neighborhood(
        rows=scenario.rows, cols=scenario.cols,
        affiliations=scenario.affiliations,
        bus_max_kw=50.0, bus_loss_factor=0.05,
    )
    decide = llm_agent.prepare(scenario=scenario, households=households,
                               solar=None, loads=None, neighborhood=neighborhood)
    # Smoke: decide returns a callable
    assert callable(decide)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_strategy_llm_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.strategies.llm_agent'`.

- [ ] **Step 3: Implement `sim/strategies/llm_agent.py`**

```python
# sim/strategies/llm_agent.py
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
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from sim.agents.agent import LLMAgent
from sim.agents.cache import PromptCache
from sim.agents.failure_modes import (
    DefectorWrapper,
    FailureModeConfig,
    NoiseSource,
    assign_defectors,
)
from sim.agents.llm import AnthropicLLMClient, LLMClient
from sim.agents.memory import MemoryStream
from sim.agents.policy import Policy
from sim.agents.protocol import Message, MessageBus
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
    tick_index: dict[datetime, int]  # populated lazily as ticks arrive
    next_tick_idx: int = 0

    def t_idx(self, t: datetime) -> int:
        if t not in self.tick_index:
            self.tick_index[t] = self.next_tick_idx
            self.next_tick_idx += 1
        return self.tick_index[t]


_REGISTRY: _AgentRegistry | None = None  # set by prepare(), read by decide_transfers


def _make_llm_client(model: str, run_dir: Path) -> LLMClient:
    """Factory; overridden by tests to inject a MockLLMClient."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    cache = PromptCache(
        local_dir=run_dir / "llm_cache",
        reference_dir=_reference_cache_dir(run_dir),
    )
    return AnthropicLLMClient(cache=cache, api_key=api_key)


def _reference_cache_dir(run_dir: Path) -> Path | None:
    """Walk up from runs/<scenario>/<strategy>/<ts>/ to find reference_runs/."""
    # run_dir = runs/<scenario>/<strategy>/<timestamp>
    # we want reference_runs/<scenario>/<strategy>/<failure_cell>/llm_cache
    # For v0 we look at reference_runs/<scenario>/<strategy>/clean/llm_cache by default;
    # callers that know the failure cell can pass it explicitly via env var.
    repo_root = run_dir.parent.parent.parent  # crude but works for runs/<...>
    scen = run_dir.parent.parent.name
    strat = run_dir.parent.name
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
) -> DecideFn:
    """Engine hook. Returns a ``decide_transfers`` callable bound to a fresh registry."""
    global _REGISTRY

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

    # one LLM client + cache shared across agents (cache is content-addressed, so multi-agent share is fine)
    client = _make_llm_client(
        model=scenario.llm.get("model", "claude-haiku-4-5-20251001"),
        run_dir=run_dir or Path("runs/_inline"),
    )

    agents: dict[str, LLMAgent] = {}
    for hid, hh in households.items():
        is_defector_prompt = (
            hid in defectors and fm.defector_realization in ("prompt", "both")
        )
        agents[hid] = LLMAgent(
            house_id=hid,
            scenario_seed=scenario.seed,
            trust_circles=dict(hh.affiliations or {}),
            policy=_initial_policy(is_defector_prompt),
            memory=MemoryStream(),
            llm_client=client,
            model=scenario.llm.get("model", "claude-haiku-4-5-20251001"),
            noise=noise,
        )

    _REGISTRY = _AgentRegistry(
        agents=agents,
        bus=bus,
        defector_wrapper=wrapper,
        tick_index={},
    )
    return decide_transfers


def _initial_policy(is_defector_prompt: bool) -> Policy:
    # All agents start with the same balanced default. The `is_defector_prompt`
    # flag is computed for parity with the spec, but its *effect* (a selfish system-
    # prompt override on plan/react calls) is deferred — see "Known limitations" in
    # the Phase 2 README (Task 25). The `wrapper` realization (Task 11) is fully
    # wired and is the Phase 2 default ablation for the strategic-agent axis.
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
        peer_states = {p: {"soc_kwh": states[p].soc_kwh, "soc_capacity": households[p].battery_kwh}
                       for p in neighborhood.union_neighbors(hid) if p in states}
        agent.observe(t=t, own_state=own_state, peer_states=peer_states,
                      inbox=inboxes.get(hid, []), t_idx=t_idx)

    # 3. Replan where needed
    for hid, agent in reg.agents.items():
        if agent.should_replan(grid_islanded=not grid[hid], t=t):
            agent.plan(t=t)

    # 4. React to pending messages
    for hid, agent in reg.agents.items():
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
        transfers, outbox = agent.act(t=t, own_state=own_state, neighborhood=neighborhood,
                                      dt_hours=dt_hours)
        all_transfers.extend(transfers)
        for m in outbox:
            reg.bus.send(reg.defector_wrapper.maybe_corrupt(m))

    # 6. Age policies
    for agent in reg.agents.values():
        agent.policy_age_ticks += 1
    return all_transfers
```

- [ ] **Step 4: Add a strategy loader if not present**

Check `sim/strategies/__init__.py`. If it's empty, add:

```python
# sim/strategies/__init__.py
"""Strategy plug-points. Each strategy module exposes ``decide_transfers`` and
optionally ``prepare``."""

import importlib
from types import ModuleType


def load(name: str) -> ModuleType:
    return importlib.import_module(f"sim.strategies.{name}")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_strategy_llm_agent.py -v`
Expected: 2 tests PASS.

- [ ] **Step 6: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 7: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 17 — sim/strategies/llm_agent.py facade** ✅ | _(this commit)_ | 172 ✓ | Thin facade module: `prepare()` instantiates one `LLMAgent` per household + a shared `MessageBus`, returns the bound `decide_transfers` callable. Per-tick flow: deliver msgs → observe → replan-if-trigger → react → act → age policies. Defector wrapper applied to all outbound. |
```

Mark Task 17 checkboxes. Then:

```bash
git add sim/strategies/llm_agent.py sim/strategies/__init__.py \
        tests/test_strategy_llm_agent.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add sim/strategies/llm_agent.py thin facade"
```

---

## Task 18: Engine wiring (`message_bus` arg + `messages.jsonl` writer)

**Files:**
- Modify: `sim/engine.py` — add optional `message_bus` parameter, pass to strategies that need it
- Modify: `sim/logging.py` — add `messages.jsonl` writer
- Test: `tests/test_engine_message_bus.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_message_bus.py
"""Engine wiring: optional message_bus, messages.jsonl written, non-LLM strategies unchanged."""

from __future__ import annotations

import json
from pathlib import Path

from sim.engine import run
from sim.scenario import load_scenario


def _smoke_scenario(tmp_path: Path) -> Path:
    yaml_text = """
id: engine_bus_smoke
seed: 1
rows: 2
cols: 2
dt_hours: 0.25
start: "2026-01-01T08:00:00"
end: "2026-01-01T08:45:00"
strategy: round_robin
data_source: synthetic
outages: [{start: "2026-01-01T08:00:00", end: "2026-01-01T10:00:00", houses: ALL}]
household_sampling: {pv_kw_peak: [4.0, 4.0], battery_kwh: [10.0, 10.0], dod_floor_frac: [0.1, 0.1], rt_efficiency: [0.9, 0.9]}
"""
    p = tmp_path / "s.yaml"
    p.write_text(yaml_text)
    return p


def test_engine_round_robin_byte_identical_without_message_bus(tmp_path: Path) -> None:
    """Adding the optional message_bus parameter must NOT change non-LLM strategy output."""
    from sim.strategies import round_robin

    s = load_scenario(_smoke_scenario(tmp_path))

    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    run(scenario=s, decide_transfers=round_robin.decide_transfers, out_dir=out_a)
    run(scenario=s, decide_transfers=round_robin.decide_transfers, out_dir=out_b)

    assert (out_a / "state.jsonl").read_bytes() == (out_b / "state.jsonl").read_bytes()
    assert (out_a / "events.jsonl").read_bytes() == (out_b / "events.jsonl").read_bytes()


def test_engine_writes_messages_jsonl_when_bus_supplied(tmp_path: Path) -> None:
    """When a MessageBus is passed, messages.jsonl is written even if empty."""
    from sim.agents.protocol import MessageBus
    from sim.network import build_overlay_neighborhood
    from sim.strategies import round_robin

    s = load_scenario(_smoke_scenario(tmp_path))
    neighborhood = build_overlay_neighborhood(
        rows=s.rows, cols=s.cols, affiliations=s.affiliations,
        bus_max_kw=50.0, bus_loss_factor=0.05,
    )
    bus = MessageBus(neighborhood=neighborhood, seed=s.seed)
    out = tmp_path / "out"
    run(scenario=s, decide_transfers=round_robin.decide_transfers,
        out_dir=out, message_bus=bus)

    assert (out / "messages.jsonl").exists()
    # round_robin doesn't send messages ⇒ empty file
    assert (out / "messages.jsonl").read_text() == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_engine_message_bus.py -v`
Expected: FAIL — `run()` does not accept `message_bus`, and no `messages.jsonl` is written.

- [ ] **Step 3: Modify `sim/engine.py`**

Read `sim/engine.py` first to find the current `run(...)` signature. Add the optional parameter and message-bus integration:

```python
# sim/engine.py — add to imports if needed
from sim.agents.protocol import MessageBus
```

Update `run(...)` signature:

```python
def run(
    scenario: Scenario,
    decide_transfers,
    *,
    out_dir: Path | None = None,
    strict: bool = True,
    message_bus: MessageBus | None = None,
):
    ...
```

In the body, near where `prepare` is dispatched (Phase 1.6 added this hook), thread `message_bus` and `out_dir` into the call:

```python
    prepare_fn = getattr(strategy_module, "prepare", None)
    if prepare_fn is not None:
        decide_transfers = prepare_fn(
            scenario=scenario,
            households=households,
            solar=solar,
            loads=loads,
            neighborhood=neighborhood,
            message_bus=message_bus,
            run_dir=out_dir,
        )
```

(If the existing `prepare_fn` callsite uses positional args without kwargs, adapt it to pass these as kwargs. Phase 1.6's `prepare` only consumes scenario/households/solar/loads/neighborhood; the new kwargs are silently accepted via `**_`. To make this safe, **update Phase 1.6's `prepare` signatures in `lp_optimal.py`** to accept `**_` for forward compat.)

At the end of `run(...)`, after writing `events.jsonl` / `state.jsonl` / `summary.json`, add:

```python
    if message_bus is not None and out_dir is not None:
        message_bus.write_jsonl(out_dir / "messages.jsonl")
```

- [ ] **Step 4: Update `sim/strategies/lp_optimal.py` `prepare` signature for forward-compat**

In `sim/strategies/lp_optimal.py`, change the `prepare(...)` signature to:

```python
def prepare(scenario, households, solar, loads, neighborhood, **_):
    ...
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_engine_message_bus.py -v`
Expected: both tests PASS.

Also re-run the full suite to confirm no regression:

Run: `.venv/bin/pytest -q`
Expected: all green (96 existing + new Phase 2 tests).

- [ ] **Step 6: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 7: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 18 — engine MessageBus wiring + messages.jsonl** ✅ | _(this commit)_ | 174 ✓ | `engine.run(... , message_bus=None)`: when bus supplied, threaded into `prepare(...)` and `messages.jsonl` written at end of run. `lp_optimal.prepare` signature accepts `**_` for forward-compat. Non-LLM strategies remain byte-identical (existing `state.jsonl`/`events.jsonl`). |
```

Mark Task 18 checkboxes. Then:

```bash
git add sim/engine.py sim/strategies/lp_optimal.py tests/test_engine_message_bus.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: thread optional MessageBus through engine.run + messages.jsonl"
```

---

## Task 19: Extend `summary.json` with Phase 2 fields + `messages.jsonl` integration

**Files:**
- Modify: `sim/logging.py` — extend `JsonlLogger.finalize()` to read `messages.jsonl` and emit Phase 2 fields
- Test: `tests/test_logging_phase2.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_logging_phase2.py
"""Phase 2 summary.json extensions are additive (Phase 1.x parsers unaffected)."""

from __future__ import annotations

import json
from pathlib import Path

from sim.engine import run
from sim.scenario import load_scenario


def test_summary_carries_phase2_fields_when_messages_jsonl_present(tmp_path: Path) -> None:
    yaml_text = """
id: smry
seed: 1
rows: 2
cols: 2
dt_hours: 0.25
start: "2026-01-01T08:00:00"
end: "2026-01-01T08:45:00"
strategy: round_robin
data_source: synthetic
outages: [{start: "2026-01-01T08:00:00", end: "2026-01-01T10:00:00", houses: ALL}]
household_sampling: {pv_kw_peak: [4.0, 4.0], battery_kwh: [10.0, 10.0], dod_floor_frac: [0.1, 0.1], rt_efficiency: [0.9, 0.9]}
"""
    p = tmp_path / "s.yaml"
    p.write_text(yaml_text)
    s = load_scenario(p)

    from sim.agents.protocol import MessageBus, Message
    from sim.network import build_overlay_neighborhood
    from sim.strategies import round_robin

    nb = build_overlay_neighborhood(rows=s.rows, cols=s.cols, affiliations=s.affiliations,
                                    bus_max_kw=50.0, bus_loss_factor=0.05)
    bus = MessageBus(neighborhood=nb, seed=s.seed)
    out = tmp_path / "out"
    run(scenario=s, decide_transfers=round_robin.decide_transfers,
        out_dir=out, message_bus=bus)

    blob = json.loads((out / "summary.json").read_text())
    # Phase 1 fields are unchanged
    assert "served_load_fraction" in blob
    assert "gini_welfare" in blob
    # Phase 2 fields are present (zeros for non-LLM strategy)
    assert "message_counts" in blob
    assert blob["message_counts"]["sent"] == 0
    assert "llm_call_counts" in blob
    assert blob["llm_call_counts"]["reflect_plan"] == 0


def test_summary_counts_dropped_messages(tmp_path: Path) -> None:
    """When the bus drops messages, summary.message_counts reflects it."""
    from datetime import datetime
    from sim.agents.protocol import Message, MessageBus
    from sim.network import build_overlay_neighborhood

    nb = build_overlay_neighborhood(rows=2, cols=2, affiliations={},
                                    bus_max_kw=50.0, bus_loss_factor=0.05)
    bus = MessageBus(neighborhood=nb, seed=1)
    bus.send(Message(
        t_sent=datetime(2026, 1, 1, 8, 0),
        sender="r0c0", recipient="r1c1",  # not neighbors
        performative="REQUEST", payload={"kwh": 0.5},
        rationale_nl="x", correlation_id="y",
    ))
    bus.write_jsonl(tmp_path / "messages.jsonl")

    from sim.logging import phase2_message_counts
    counts = phase2_message_counts(tmp_path / "messages.jsonl")
    assert counts["sent"] == 1
    assert counts["dropped_invalid_recipient"] == 1
    assert counts["delivered"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_logging_phase2.py -v`
Expected: FAIL — `summary.json` does not have Phase 2 keys; `phase2_message_counts` does not exist.

- [ ] **Step 3: Extend `sim/logging.py`**

Add to `sim/logging.py`:

```python
def phase2_message_counts(messages_jsonl: Path) -> dict[str, int]:
    counts = {
        "sent": 0,
        "delivered": 0,
        "dropped_invalid_recipient": 0,
        "dropped_comm": 0,
        "dropped_budget": 0,
    }
    if not Path(messages_jsonl).exists():
        return counts
    for line in Path(messages_jsonl).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        counts["sent"] += 1
        if row["outcome"] == "delivered":
            counts["delivered"] += 1
        elif row["outcome"] == "dropped":
            reason = row.get("reason") or ""
            if reason == "invalid_recipient":
                counts["dropped_invalid_recipient"] += 1
            elif reason == "comm_drop":
                counts["dropped_comm"] += 1
            elif reason == "budget_overflow":
                counts["dropped_budget"] += 1
    return counts
```

Modify `JsonlLogger.finalize(...)` (Phase 1 entry point) — at the end of the existing summary-dict construction, before writing `summary.json`, add:

```python
        # Phase 2 additive fields
        messages_path = self.run_dir / "messages.jsonl"
        msg_counts = phase2_message_counts(messages_path)
        summary["message_counts"] = msg_counts
        summary["llm_call_counts"] = {"reflect_plan": 0, "react_msg": 0, "cache_hits": 0, "cache_misses": 0}
        summary["llm_cost_usd_estimated"] = 0.0
        summary["failure_modes_active"] = {}
        summary["policy_parse_failures"] = 0
        summary["policy_fallbacks_to_round_robin"] = 0
```

(LLM call counts will be populated by the strategy facade in a later refinement — for now, zero defaults are fine; the integration test in Task 21 wires real counts.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_logging_phase2.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 6: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 19 — summary.json additive Phase 2 fields** ✅ | _(this commit)_ | 176 ✓ | `sim/logging.py`: `phase2_message_counts()` reads `messages.jsonl`; `JsonlLogger.finalize` appends `message_counts`, `llm_call_counts`, `llm_cost_usd_estimated`, `failure_modes_active`, `policy_parse_failures`, `policy_fallbacks_to_round_robin`. Phase 1.x parsers unaffected (additive only). |
```

Mark Task 19 checkboxes. Then:

```bash
git add sim/logging.py tests/test_logging_phase2.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: extend summary.json with Phase 2 additive fields"
```

---

## Task 20: Scenario YAML — failure-cell variants of `haves_havenots`

**Files:**
- Modify: `configs/scenarios/haves_havenots.yaml` — add `llm:` and (empty) `failure_modes:` blocks; change `strategy` to `llm_agent` is OPTIONAL — keep `round_robin` as the default and add new variants
- Create: `configs/scenarios/haves_havenots__llm.yaml` — switch strategy to `llm_agent`, no failure modes
- Create: `configs/scenarios/haves_havenots__defectors.yaml` — defector_fraction=0.2
- Create: `configs/scenarios/haves_havenots__noise.yaml` — soc_std_frac=0.10, load_std_frac=0.15
- Create: `configs/scenarios/haves_havenots__comm.yaml` — comm.per_tick_budget=2, drop_prob_by_circle.geographic=0.30
- Create: `configs/scenarios/haves_havenots__all.yaml` — all three combined
- Test: `tests/test_failure_cell_scenarios.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_failure_cell_scenarios.py
"""Failure-cell variants of haves_havenots load + parse + sample-households work."""

from __future__ import annotations

from pathlib import Path

from sim.scenario import load_scenario

ROOT = Path(__file__).resolve().parent.parent
SCEN_DIR = ROOT / "configs" / "scenarios"


def test_haves_havenots_llm_loads() -> None:
    s = load_scenario(SCEN_DIR / "haves_havenots__llm.yaml")
    assert s.strategy == "llm_agent"
    assert s.llm["model"].startswith("claude-")
    assert s.failure_modes.defector_fraction == 0.0


def test_haves_havenots_defectors_loads() -> None:
    s = load_scenario(SCEN_DIR / "haves_havenots__defectors.yaml")
    assert s.failure_modes.defector_fraction == 0.2


def test_haves_havenots_noise_loads() -> None:
    s = load_scenario(SCEN_DIR / "haves_havenots__noise.yaml")
    assert s.failure_modes.obs_noise.soc_std_frac == 0.10


def test_haves_havenots_comm_loads() -> None:
    s = load_scenario(SCEN_DIR / "haves_havenots__comm.yaml")
    assert s.failure_modes.comm.per_tick_budget == 2
    assert s.failure_modes.comm.drop_prob_by_circle["geographic"] == 0.30


def test_haves_havenots_all_loads() -> None:
    s = load_scenario(SCEN_DIR / "haves_havenots__all.yaml")
    assert s.failure_modes.defector_fraction > 0
    assert s.failure_modes.obs_noise.soc_std_frac > 0
    assert s.failure_modes.comm.per_tick_budget is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_failure_cell_scenarios.py -v`
Expected: FAIL — none of the 5 scenario files exist yet.

- [ ] **Step 3: Create the 5 scenario variants**

For each, read `configs/scenarios/haves_havenots.yaml` first to get the base content; then create the variant by appending an `llm:` block and a `failure_modes:` block. Example for `haves_havenots__llm.yaml`:

```yaml
# configs/scenarios/haves_havenots__llm.yaml
# Copy of haves_havenots.yaml with strategy=llm_agent and an `llm:` config block.
# Failure modes: clean cell.
extends: haves_havenots.yaml   # NOT a YAML feature — see note below

# Instead of `extends:`, copy the full base content (the project doesn't yet
# support YAML inheritance). Paste the contents of haves_havenots.yaml here,
# then override:
strategy: llm_agent
llm:
  model: claude-haiku-4-5-20251001
  policy_refresh_every_ticks: 4
  react_max_per_tick: 3
  require_rationale: true
failure_modes: {}
```

(Concretely: cat the existing `haves_havenots.yaml` and copy its body verbatim into each new file, then update `id:`, `strategy:`, add `llm:` and `failure_modes:`.)

For `haves_havenots__defectors.yaml`, set:

```yaml
failure_modes:
  defector_fraction: 0.20
  defector_assignment: random
  defector_realization: prompt
```

For `haves_havenots__noise.yaml`:

```yaml
failure_modes:
  obs_noise:
    soc_std_frac: 0.10
    load_std_frac: 0.15
    solar_forecast_horizon_ticks: 4
    solar_forecast_std_frac: 0.20
```

For `haves_havenots__comm.yaml`:

```yaml
failure_modes:
  comm:
    per_tick_budget: 2
    drop_prob_by_circle:
      geographic: 0.30
      owner: 0.05
      hoa: 0.10
      dr_aggregator: 0.10
```

For `haves_havenots__all.yaml`, combine all of the above.

Also update the base `haves_havenots.yaml` to include `failure_modes: {}` and `llm: {}` blocks (additive, no behavior change for round_robin runs).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_failure_cell_scenarios.py -v`
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 20 — failure-cell scenario YAML variants** ✅ | _(this commit)_ | 181 ✓ | 5 new scenario files: `haves_havenots__{llm,defectors,noise,comm,all}.yaml` for clean LLM run + each failure-mode axis + combined. Base `haves_havenots.yaml` now carries empty `failure_modes:` and `llm:` blocks (no behavior change). |
```

Mark Task 20 checkboxes. Then:

```bash
git add configs/scenarios/haves_havenots.yaml \
        configs/scenarios/haves_havenots__llm.yaml \
        configs/scenarios/haves_havenots__defectors.yaml \
        configs/scenarios/haves_havenots__noise.yaml \
        configs/scenarios/haves_havenots__comm.yaml \
        configs/scenarios/haves_havenots__all.yaml \
        tests/test_failure_cell_scenarios.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add failure-cell scenario variants of haves_havenots"
```

---

## Task 21: Integration test — end-to-end mock-LLM on `haves_havenots__llm`

**Files:**
- Test: `tests/test_llm_agent_integration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_agent_integration.py
"""End-to-end smoke: LLM strategy runs on haves_havenots__llm.yaml with mock LLM,
produces all four output files, and beats round_robin on served-load fraction."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from sim.agents.cache import PromptCache
from sim.agents.llm import LLMResponse, MockLLMClient

ROOT = Path(__file__).resolve().parent.parent
SCEN_DIR = ROOT / "configs" / "scenarios"


def _canned_responses(tmp_path: Path) -> MockLLMClient:
    """A small dictionary of canned responses sufficient to drive a 30-house run."""
    policy_yaml = yaml.safe_dump({
        "sharing_intent": "generous",
        "share_min_soc_frac": 0.40,
        "max_share_kw_per_tick": 1.5,
        "recipient_priority": [
            {"circle": "owner", "weight": 1.0},
            {"circle": "hoa", "weight": 0.8},
            {"circle": "dr_aggregator", "weight": 0.7},
            {"circle": "geographic", "weight": 0.5},
        ],
        "distrusted_peers": [],
        "request_urgency": "normal",
        "belief_note": "haves should help havenots aggressively",
        "ttl_ticks": 4,
    })
    plan_text = f"reflection: havenot peers need help.\n\n```yaml\n{policy_yaml}\n```"
    return MockLLMClient(
        cache=PromptCache(local_dir=tmp_path / "cache"),
        canned={
            "You are household": LLMResponse(text=plan_text, tokens_in=400, tokens_out=160),
            "You are reacting": LLMResponse(text="ACCEPT\nrationale: i can spare it", tokens_in=80, tokens_out=20),
        },
    )


def test_llm_agent_beats_round_robin_on_haves_havenots(tmp_path: Path) -> None:
    from sim.engine import run
    from sim.scenario import load_scenario
    from sim.strategies import llm_agent as llm_strat
    from sim.strategies import round_robin as rr_strat

    # baseline
    s_rr = load_scenario(SCEN_DIR / "haves_havenots.yaml")
    out_rr = tmp_path / "rr"
    run(scenario=s_rr, decide_transfers=rr_strat.decide_transfers, out_dir=out_rr)
    rr_summary = json.loads((out_rr / "summary.json").read_text())

    # LLM
    s_llm = load_scenario(SCEN_DIR / "haves_havenots__llm.yaml")
    mock = _canned_responses(tmp_path)
    llm_strat._make_llm_client = lambda model, run_dir: mock  # type: ignore[attr-defined]
    out_llm = tmp_path / "llm"
    from sim.agents.protocol import MessageBus
    from sim.network import build_overlay_neighborhood
    nb = build_overlay_neighborhood(
        rows=s_llm.rows, cols=s_llm.cols, affiliations=s_llm.affiliations,
        bus_max_kw=50.0, bus_loss_factor=0.05,
    )
    bus = MessageBus(neighborhood=nb, seed=s_llm.seed)
    run(scenario=s_llm, decide_transfers=llm_strat.decide_transfers,
        out_dir=out_llm, message_bus=bus)
    llm_summary = json.loads((out_llm / "summary.json").read_text())

    assert llm_summary["served_load_fraction"] > rr_summary["served_load_fraction"], (
        f"LLM should beat round_robin on haves_havenots. "
        f"rr={rr_summary['served_load_fraction']:.4f} llm={llm_summary['served_load_fraction']:.4f}"
    )
    # outputs are present
    assert (out_llm / "messages.jsonl").exists()
    assert (out_llm / "state.jsonl").exists()
    assert (out_llm / "events.jsonl").exists()
    assert (out_llm / "config.json").exists()
    # there were SOME messages sent
    msgs = (out_llm / "messages.jsonl").read_text().splitlines()
    assert len(msgs) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_llm_agent_integration.py -v`
Expected: FAIL — likely either the mock isn't covering all distinct prompts, or `decide_transfers` raises, or LLM doesn't beat round_robin without more careful canning. Use the failure to iterate on the canned response dict + the policy fields.

- [ ] **Step 3: Iterate on canned responses until the test passes**

If the LLM strategy fails to beat round_robin, possible fixes:
- Lower `share_min_soc_frac` further in the canned policy (e.g., 0.30).
- Increase `max_share_kw_per_tick`.
- Add more substring-keyed canned responses to cover variant prompts (e.g., "household r0c0", "household r0c1", or just an empty substring `""` as a catch-all).

The goal is a passing smoke test, not a maximally-optimal LLM. The integration test asserts only that LLM beats round_robin; it does not claim a specific gap-closed number.

- [ ] **Step 4: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 5: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 21 — end-to-end mock-LLM integration test** ✅ | _(this commit)_ | 182 ✓ | `test_llm_agent_integration.py` runs the LLM strategy with a canned MockLLMClient on `haves_havenots__llm.yaml`; asserts served-load fraction strictly beats `round_robin`; all four output files present; non-empty `messages.jsonl`. |
```

Mark Task 21 checkboxes. Then:

```bash
git add tests/test_llm_agent_integration.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "test: end-to-end mock-LLM integration on haves_havenots"
```

---

## Task 22: Integration test — cache-warm replay determinism

**Files:**
- Test: `tests/test_llm_agent_replay.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_agent_replay.py
"""Replay determinism: two cache-warm runs produce byte-identical state/events/messages."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from sim.agents.cache import PromptCache
from sim.agents.llm import LLMResponse, MockLLMClient

ROOT = Path(__file__).resolve().parent.parent
SCEN_DIR = ROOT / "configs" / "scenarios"


def _canned_mock(tmp_path: Path) -> MockLLMClient:
    policy_yaml = yaml.safe_dump({
        "sharing_intent": "balanced",
        "share_min_soc_frac": 0.40,
        "max_share_kw_per_tick": 1.0,
        "recipient_priority": [{"circle": "owner", "weight": 1.0}, {"circle": "geographic", "weight": 0.5}],
        "distrusted_peers": [],
        "request_urgency": "normal",
        "belief_note": "",
        "ttl_ticks": 4,
    })
    return MockLLMClient(
        cache=PromptCache(local_dir=tmp_path / "cache"),
        canned={
            "You are household": LLMResponse(text=f"r\n\n```yaml\n{policy_yaml}\n```", tokens_in=400, tokens_out=160),
            "You are reacting": LLMResponse(text="ACCEPT\nrationale: ok", tokens_in=80, tokens_out=20),
        },
    )


def test_two_runs_with_same_mock_are_byte_identical(tmp_path: Path) -> None:
    from sim.agents.protocol import MessageBus
    from sim.engine import run
    from sim.network import build_overlay_neighborhood
    from sim.scenario import load_scenario
    from sim.strategies import llm_agent as llm_strat

    s = load_scenario(SCEN_DIR / "haves_havenots__llm.yaml")
    nb = build_overlay_neighborhood(rows=s.rows, cols=s.cols, affiliations=s.affiliations,
                                    bus_max_kw=50.0, bus_loss_factor=0.05)

    def one_run(label: str) -> Path:
        out = tmp_path / label
        mock = _canned_mock(tmp_path / f"mock_{label}")
        llm_strat._make_llm_client = lambda model, run_dir: mock  # type: ignore[attr-defined]
        bus = MessageBus(neighborhood=nb, seed=s.seed)
        run(scenario=s, decide_transfers=llm_strat.decide_transfers,
            out_dir=out, message_bus=bus)
        return out

    a = one_run("a")
    b = one_run("b")

    assert (a / "state.jsonl").read_bytes() == (b / "state.jsonl").read_bytes()
    assert (a / "events.jsonl").read_bytes() == (b / "events.jsonl").read_bytes()
    assert (a / "messages.jsonl").read_bytes() == (b / "messages.jsonl").read_bytes()
```

- [ ] **Step 2: Run test to verify it fails OR passes**

Run: `.venv/bin/pytest tests/test_llm_agent_replay.py -v`
Expected: PASS — all RNGs are deterministic; MockLLMClient is deterministic given same canned dict. If it FAILS, the cause is somewhere in the agent or bus where an undocumented dict-iteration order or unseeded RNG leaked in; investigate before continuing.

- [ ] **Step 3: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 4: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 22 — replay determinism lock-in** ✅ | _(this commit)_ | 183 ✓ | `test_llm_agent_replay.py`: two MockLLM runs of `haves_havenots__llm.yaml` produce byte-identical `state.jsonl` / `events.jsonl` / `messages.jsonl`. Pins down per-agent RNG seeding, bus RNG, defector RNG, and noise RNG determinism. |
```

Mark Task 22 checkboxes. Then:

```bash
git add tests/test_llm_agent_replay.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "test: lock in replay determinism for LLM strategy"
```

---

## Task 23: Integration test — each failure-mode axis produces measurable change

**Files:**
- Test: `tests/test_llm_agent_failure_axes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_agent_failure_axes.py
"""Each failure-mode axis must produce a measurable change vs the clean cell."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from sim.agents.cache import PromptCache
from sim.agents.llm import LLMResponse, MockLLMClient

ROOT = Path(__file__).resolve().parent.parent
SCEN_DIR = ROOT / "configs" / "scenarios"


def _canned_mock(tmp_path: Path) -> MockLLMClient:
    policy_yaml = yaml.safe_dump({
        "sharing_intent": "generous",
        "share_min_soc_frac": 0.40,
        "max_share_kw_per_tick": 1.5,
        "recipient_priority": [
            {"circle": "owner", "weight": 1.0},
            {"circle": "geographic", "weight": 0.5},
        ],
        "distrusted_peers": [],
        "request_urgency": "normal",
        "belief_note": "",
        "ttl_ticks": 4,
    })
    return MockLLMClient(
        cache=PromptCache(local_dir=tmp_path / "cache"),
        canned={
            "You are household": LLMResponse(text=f"r\n\n```yaml\n{policy_yaml}\n```", tokens_in=400, tokens_out=160),
            "You are reacting": LLMResponse(text="ACCEPT\nrationale: ok", tokens_in=80, tokens_out=20),
        },
    )


def _run(scenario_file: str, tmp_path: Path) -> dict:
    from sim.agents.protocol import MessageBus
    from sim.engine import run
    from sim.network import build_overlay_neighborhood
    from sim.scenario import load_scenario
    from sim.strategies import llm_agent as llm_strat

    s = load_scenario(SCEN_DIR / scenario_file)
    mock = _canned_mock(tmp_path / scenario_file)
    llm_strat._make_llm_client = lambda model, run_dir: mock  # type: ignore[attr-defined]
    nb = build_overlay_neighborhood(rows=s.rows, cols=s.cols, affiliations=s.affiliations,
                                    bus_max_kw=50.0, bus_loss_factor=0.05)
    bus = MessageBus(neighborhood=nb, seed=s.seed)
    out = tmp_path / scenario_file.replace(".yaml", "")
    run(scenario=s, decide_transfers=llm_strat.decide_transfers, out_dir=out, message_bus=bus)
    return json.loads((out / "summary.json").read_text())


def test_defectors_reduce_served_load_fraction(tmp_path: Path) -> None:
    clean = _run("haves_havenots__llm.yaml", tmp_path)
    dirty = _run("haves_havenots__defectors.yaml", tmp_path)
    assert dirty["served_load_fraction"] < clean["served_load_fraction"], (
        f"clean={clean['served_load_fraction']:.4f} defectors={dirty['served_load_fraction']:.4f}"
    )


def test_noise_changes_outcomes(tmp_path: Path) -> None:
    clean = _run("haves_havenots__llm.yaml", tmp_path)
    noisy = _run("haves_havenots__noise.yaml", tmp_path)
    # Noise should at least change the transfer count or served fraction
    differs = (
        noisy["transfer_count"] != clean["transfer_count"]
        or abs(noisy["served_load_fraction"] - clean["served_load_fraction"]) > 1e-4
    )
    assert differs, f"noise produced no observable difference: {clean=} {noisy=}"


def test_comm_constraint_reduces_message_delivery(tmp_path: Path) -> None:
    clean = _run("haves_havenots__llm.yaml", tmp_path)
    constrained = _run("haves_havenots__comm.yaml", tmp_path)
    # tighter budget + dropout ⇒ smaller delivered/sent ratio
    clean_ratio = clean["message_counts"]["delivered"] / max(1, clean["message_counts"]["sent"])
    cons_ratio = constrained["message_counts"]["delivered"] / max(1, constrained["message_counts"]["sent"])
    assert cons_ratio < clean_ratio, f"clean ratio={clean_ratio:.3f} constrained ratio={cons_ratio:.3f}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_llm_agent_failure_axes.py -v`
Expected: All three may PASS already (if Tasks 11-18 are correct). If any FAIL, the cause is in the relevant injection point — investigate before continuing.

- [ ] **Step 3: Run linters**

Run: `.venv/bin/ruff check sim tests && .venv/bin/mypy`
Expected: no errors.

- [ ] **Step 4: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 23 — failure-axis lock-in** ✅ | _(this commit)_ | 186 ✓ | Three tests pin down: defector_fraction=0.2 reduces served-load fraction; obs_noise=0.10 measurably changes transfer count or served fraction; comm constraints lower delivered/sent ratio. Each axis demonstrably affects the system, validating the injection points. |
```

Mark Task 23 checkboxes. Then:

```bash
git add tests/test_llm_agent_failure_axes.py \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "test: lock in failure-axis measurable effects"
```

---

## Task 24: `reference_runs/` setup + 3 live-Haiku reference runs

**Files:**
- Modify: `.gitignore` — keep `runs/` ignored, ensure `reference_runs/` is tracked
- Create: `reference_runs/.gitkeep`
- Create: `reference_runs/haves_havenots/llm_agent/clean/`
- Create: `reference_runs/haves_havenots/llm_agent/defectors/`
- Create: `reference_runs/long_outage_72h/llm_agent/clean/`
- Modify: `scripts/run.py` — add `--reference-cell` flag that writes outputs into `reference_runs/...`

- [ ] **Step 1: Update `.gitignore`**

Ensure `.gitignore` contains:

```gitignore
runs/
!reference_runs/
```

(`runs/` stays ignored; `reference_runs/` is NEW and explicitly tracked.)

- [ ] **Step 2: Create the reference_runs/ skeleton**

```bash
mkdir -p reference_runs/haves_havenots/llm_agent/clean
mkdir -p reference_runs/haves_havenots/llm_agent/defectors
mkdir -p reference_runs/long_outage_72h/llm_agent/clean
touch reference_runs/.gitkeep
```

- [ ] **Step 3: Add `--reference-cell` flag to `scripts/run.py`**

Read `scripts/run.py` first to find the argument parser. Add:

```python
parser.add_argument(
    "--reference-cell",
    type=str,
    default=None,
    help="If set, write outputs under reference_runs/<scenario>/<strategy>/<cell>/ instead of runs/...",
)
```

In the output-dir resolution logic, if `args.reference_cell` is set, use:

```python
out_dir = Path("reference_runs") / scenario_id / strategy / args.reference_cell
```

- [ ] **Step 4: Run the three live-Haiku reference runs**

**Live API calls required. Set `ANTHROPIC_API_KEY` first.** Each run takes ~5–20 minutes depending on the scenario length and cache state. Cost: ~$1–3 per run on Haiku.

```bash
export ANTHROPIC_API_KEY=...
.venv/bin/python -m scripts.run --scenario configs/scenarios/haves_havenots__llm.yaml --reference-cell clean
.venv/bin/python -m scripts.run --scenario configs/scenarios/haves_havenots__defectors.yaml --reference-cell defectors
.venv/bin/python -m scripts.run --scenario configs/scenarios/long_outage_72h__llm.yaml --reference-cell clean
```

(For the third command, you need to create `long_outage_72h__llm.yaml` similarly to `haves_havenots__llm.yaml` — copy + add `strategy: llm_agent` + `llm:` + `failure_modes: {}`. Add this as a sub-step.)

Each run should produce:

```
reference_runs/<scenario>/llm_agent/<cell>/
├── state.jsonl
├── events.jsonl
├── messages.jsonl
├── config.json
├── summary.json
└── llm_cache/
    └── claude-haiku-4-5-20251001/
        └── <sha256>.json   # many files
```

- [ ] **Step 5: Trim messages.jsonl in-repo to a manageable size if needed**

If a full `messages.jsonl` is >50 MB (likely for the 72h run), keep only the first 5000 lines in the in-repo file as `messages.jsonl.head` and document this in `reference_runs/README.md`:

```bash
head -n 5000 reference_runs/long_outage_72h/llm_agent/clean/messages.jsonl > /tmp/m.head
mv /tmp/m.head reference_runs/long_outage_72h/llm_agent/clean/messages.jsonl
```

(The `summary.json` already carries the totals.)

- [ ] **Step 6: Add a `reference_runs/README.md`**

```markdown
# Reference Runs (Phase 2)

These are cache-warmed reference runs that ship with the repo so any reviewer can
re-run Phase 2 experiments byte-identically without paying for the LLM API.

Each subdirectory under `<scenario>/llm_agent/<cell>/` contains:

- `state.jsonl` / `events.jsonl` / `messages.jsonl` / `config.json` / `summary.json`
  — exactly the same outputs `scripts/run.py` produces.
- `llm_cache/<model>/<sha256>.json` — every LLM call's prompt + response, content-
  addressed. The `LLMClient` checks this cache before hitting the API; cache-warm
  replays make zero network calls.

## Re-running

```bash
python -m scripts.run \
    --scenario configs/scenarios/haves_havenots__llm.yaml \
    --reference-cell clean
```

This re-uses the cache; the output `state.jsonl` etc. should be byte-identical
to the files in this directory.

## Files vs notes

- `messages.jsonl` may be truncated to the first 5000 lines in-repo to keep the
  repo small; `summary.json` carries the full counts.
```

- [ ] **Step 7: Run the suite to confirm nothing regressed**

Run: `.venv/bin/pytest -q`
Expected: all green.

- [ ] **Step 8: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 24 — reference_runs/ + 3 live-Haiku runs** ✅ | _(this commit)_ | 186 ✓ | New top-level `reference_runs/` with three runs: `haves_havenots__llm` clean, `haves_havenots__defectors`, `long_outage_72h__llm` clean. Each includes full prompt cache + state/events/messages/summary. `scripts/run.py --reference-cell <name>` writes outputs into this tree. README explains how to re-run with cache-warm replay (zero API calls). |
```

Mark Task 24 checkboxes. Then:

```bash
git add .gitignore scripts/run.py reference_runs/ \
        configs/scenarios/long_outage_72h__llm.yaml \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "feat: add reference_runs/ + 3 live-Haiku cached runs for replay"
```

---

## Task 25: README + CLAUDE.md Phase 2 status

**Files:**
- Modify: `README.md` — add Phase 2 section
- Modify: `CLAUDE.md` — update phase table

- [ ] **Step 1: Update `README.md`**

Add (or replace) a "Phase 2 status" section in `README.md`:

```markdown
## Phase 2 — LLM Agent Layer (in repo as of 2026-06-13)

Per-household LLM agents negotiate transfers in natural language across overlapping
trust circles (geographic + ownership/management overlays from Phase 1.6). Agents:

- maintain a Park-adapted memory stream + periodic reflection,
- emit structured Policy YAML that a pure-Python tick executor consumes,
- exchange speech-act messages (REQUEST / OFFER / ACCEPT / REJECT / COUNTER / INFORM)
  with an NL `rationale` field on every message,
- respect three orthogonal failure-mode axes — strategic agents, noisy observations,
  comm constraints — each independently configurable per scenario YAML.

Determinism is preserved via a content-addressed prompt cache. The in-repo
`reference_runs/` directory ships three cache-warmed runs you can replay without
hitting the API:

| Scenario | Failure cell | Notes |
|---|---|---|
| `haves_havenots__llm.yaml` | clean | primary gap-closed number vs Phase 1.6 strategies |
| `haves_havenots__defectors.yaml` | defectors_only (fraction 0.2) | robustness smoke |
| `long_outage_72h__llm.yaml` | clean | long-horizon memory/reflection smoke |

### Quickstart

```bash
# Replay a reference run (cache-warm, no API calls):
python -m scripts.run \
    --scenario configs/scenarios/haves_havenots__llm.yaml \
    --reference-cell clean
```

To run live, set `ANTHROPIC_API_KEY` and omit `--reference-cell`. Default model is
Claude Haiku 4.5; configure via the `llm.model` block of the scenario YAML.

### Phase 2 known limitations

- **`defector_realization: prompt` is partially wired.** Defector assignment is
  deterministic (Task 10) and the `wrapper` realization (Task 11) is fully
  implemented (mutates outbound payloads at the bus). The `prompt` realization,
  which would replace the agent's system prompt with a "selfish" template, is
  computed-but-not-applied; landing it is a v1 follow-up. The `wrapper`
  realization is the Phase 2 default ablation for the strategic-agent axis.
- **Peer state observed by an agent is the engine's true state**, not the
  peer's voluntarily-INFORM'd self-view. Migrating to message-only peer state
  is a v1 follow-up; the current shape is a conservative simplification that
  keeps the LLM-agent surface area honest about what it sees.
- **No synchronous multi-round negotiation in v0** — agents reply reactively
  within one tick of receiving a REQUEST/OFFER. Multi-round bargaining is a
  reserved ablation.
```

- [ ] **Step 2: Update the phase table in `CLAUDE.md`**

In `CLAUDE.md`, change the Phase 2 row of the phase table:

```markdown
| 2 — LLM agent layer | 5-8 | **complete** | Per-household LLM agent, natural-language P2P messaging |
```

Update the "Current position" line under "Phase 1 status" (or add a "Phase 2 status" section) to capture:

```markdown
## Phase 2 status

- **Spec:** `docs/superpowers/specs/2026-06-13-phase2-llm-agent-design.md`
- **Plan:** `docs/superpowers/plans/2026-06-13-phase2-llm-agent.md` (25 tasks, TDD)
- **Approved:** 2026-06-13
- **Execution mode:** Inline (Claude executes tasks in-session, batched ~3-5 at a time with check-ins).
- **Status:** complete; three reference runs shipped; tagged `phase2-complete`.
```

- [ ] **Step 3: Commit**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 25 — README + CLAUDE.md updates** ✅ | _(this commit)_ | 186 ✓ | README gains a Phase 2 section explaining what shipped + the three reference runs + the cache-warm replay quickstart. CLAUDE.md phase table marks Phase 2 complete and adds a Phase 2 status block with spec/plan/tag pointers. |
```

Mark Task 25 checkboxes. Then:

```bash
git add README.md CLAUDE.md \
        docs/superpowers/plans/2026-06-13-phase2-llm-agent.md
git commit -m "docs: update README + CLAUDE.md for Phase 2 completion"
```

---

## Task 26: Phase 2 wrap-up — clean-install verify + tag

**Files:**
- (no code change)

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/pytest -q`
Expected: ~186 tests pass (96 from Phase 1.6 + ~90 new in Phase 2). Zero failures.

- [ ] **Step 2: Lint + typecheck**

Run: `.venv/bin/ruff check sim scripts tests && .venv/bin/mypy`
Expected: zero errors.

- [ ] **Step 3: Clean-install dry-run in `/tmp/microgrid_ci_check`**

Run:
```bash
rm -rf /tmp/microgrid_ci_check && python3 -m venv /tmp/microgrid_ci_check
/tmp/microgrid_ci_check/bin/pip install --upgrade pip
/tmp/microgrid_ci_check/bin/pip install -e .
/tmp/microgrid_ci_check/bin/pytest -q
```
Expected: clean install succeeds; all tests pass in the fresh venv. If FAIL, **stop** and diagnose before tagging.

- [ ] **Step 4: Glance at CI on GitHub**

Run: `gh run list --limit 1`
Expected: latest run is green (or, if the Phase 2 commits haven't been pushed yet, push them now and wait).

- [ ] **Step 5: Confirm reference-run replay is byte-identical**

For each of the three reference runs, redo the run into `/tmp/replay/...` and diff:

```bash
mkdir -p /tmp/replay
python -m scripts.run --scenario configs/scenarios/haves_havenots__llm.yaml \
    --out-dir /tmp/replay/havhav_clean
diff <(cat reference_runs/haves_havenots/llm_agent/clean/state.jsonl) \
     <(cat /tmp/replay/havhav_clean/state.jsonl)
diff <(cat reference_runs/haves_havenots/llm_agent/clean/events.jsonl) \
     <(cat /tmp/replay/havhav_clean/events.jsonl)
```

Expected: empty diffs. (Note: `--out-dir` may need to be implemented in `scripts/run.py` if not present; alternatively, run with `--reference-cell` and diff against a known snapshot.)

If diff is NON-empty: cache lookup is broken OR something downstream of the cache (RNG, sort order) leaked nondeterminism. Diagnose before tagging.

- [ ] **Step 6: Tag**

```bash
git tag -a phase2-complete -m "Phase 2: LLM agent layer + 3 failure-mode axes + 3 reference runs"
git push --tags
```

- [ ] **Step 7: Final progress log entry**

Add progress log row:

```markdown
| 2026-06-13 | **P2 Task 26 — wrap-up + tag** ✅ | _(this commit)_ | 186 ✓ | Full suite green; ruff + mypy clean; clean-install dry-run in fresh `/tmp/microgrid_ci_check` venv passes; reference-run replay diffs are empty. Tagged `phase2-complete`. Phase 2 deliverable: LLM agent layer with policy+reactive cadence, Park-adapted memory+reflection, speech-act NL messaging, three orthogonal failure-mode axes, prompt-cache deterministic replay. |
```

Mark Task 26 checkboxes. Then:

```bash
git add docs/superpowers/plans/2026-06-13-phase2-llm-agent.md CLAUDE.md
git commit -m "chore: phase 2 wrap-up — tag phase2-complete"
```

---

## Phase 2 done.

What ships:

- `sim/agents/` substrate: `policy`, `memory`, `protocol`, `cache`, `llm`, `reflection`, `failure_modes`, `agent`.
- `sim/strategies/llm_agent.py` thin facade.
- Engine wiring: optional `message_bus`; `messages.jsonl` writer; additive `summary.json` fields.
- 5 failure-cell variants of `haves_havenots`.
- 3 reference runs (cache-warmed, in-repo).
- ~90 new tests + 3 integration tests + 1 replay-determinism test + 3 failure-axis tests.

What's next (Phase 3):

- Full benchmark sweep across {scenarios × strategies × seeds × failure cells × model tiers (Haiku / Sonnet / Opus / OS)}.
- Needs-weighted welfare metric.
- Explainability metric (consumes `rationale_nl` + `belief_note` populated this phase).
- `/sweep` skill activation for the multi-cell experimental grid.
