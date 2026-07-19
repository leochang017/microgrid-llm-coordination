# Phase 2 — LLM Agent Layer: Design Spec

> **Status:** approved design, pre-implementation.
> **Date:** 2026-06-13.
> **Author:** Leo Chang.
> **Gate:** Phase 1.6 (`phase1.6-complete`, 2026-05-29) — overlay comm graph, stress
> scenarios, LP ceiling, gap-closed reporting — is the substrate this phase builds on.

## Motivation

Phase 1 + 1.6 produced a deterministic discrete-time microgrid simulator with:

- 30 households on a 5×6 grid with per-tick (15 min) physics,
- realistic stress scenarios where geographic round-robin visibly fails (`haves_havenots.yaml`:
  no_coord 0.456 / round_robin 0.525 / LP ceiling 0.529 served-load fraction),
- a centralized LP upper-bound baseline + `gap_closed` framing
  (`scripts/compare.py` from Phase 1.6 Task 15),
- ownership/management **affiliation overlays** producing partially-overlapping trust
  circles (`Neighborhood.union_neighbors`), and
- a `prepare(...)` / `decide_transfers(...)` plug-point reserved for the LLM layer.

This phase builds the LLM agent layer that plugs into that surface. The research
question is whether a population of per-household LLM agents, negotiating in natural
language across overlapping trust circles, can:

- **(a)** allocate scarce energy fairly in stress regimes where rule-based protocols
  leave headroom (`round_robin → LP` gap on Phase 1.6 stress scenarios),
- **(b)** remain robust to three failure modes the advisor locked on 2026-05-26 —
  strategic/selfish agents, noisy observations, and communication constraints — and
- **(c)** explain their decisions in NL (the explainability metric proper is Phase 3,
  but the rationale field of every message is the substrate for it).

The contribution axis is **CS/ML** (multi-agent NL coordination, robustness,
explainability), not power-systems. Park et al., *Generative Agents* (arXiv:2304.03442),
is the architectural reference: memory stream + reflection + planning, reimplemented for
this domain rather than forked. Cited prominently in the spec preamble and the docstrings
of `sim/agents/memory.py` and `sim/agents/reflection.py`.

## Non-goals (YAGNI / deferred to later phases)

- No needs-weighted welfare (advisor-confirmed Phase 3).
- No full benchmark sweep (scenarios × strategies × seeds × failure cells × model tiers);
  Phase 3.
- No explainability metric / rubric / LLM-judge (Phase 3 — the (c) of the research
  question proper).
- No web demo (Phase 4).
- No production / deployment hooks. This is a research artifact.
- No explicit "detect-the-liar" mechanism inside the agent beyond what reflection over
  message history naturally surfaces; designing such a mechanism is itself a finding,
  not an assumption.
- No synchronous multi-round negotiation in v0 (reactive single-turn responses to
  REQUEST/OFFER only). A multi-round variant is reserved as an ablation if needed.
- No changes to existing Phase 1.x physics (`household.step`, `settle_transfers`) or to
  Phase 1.6's overlay graph + LP strategy.

## Phase 2 MVP scope (what ships, what defers)

**In scope (Phase 2 deliverable):**

- New `sim/agents/` substrate (one focused module per responsibility, see Components
  table) — agent core, memory, reflection, policy, message protocol, message bus, LLM
  adapter, prompt cache, failure-mode injection.
- New `sim/strategies/llm_agent.py` thin facade that plugs into the existing `prepare`
  / `decide_transfers` interface.
- Minimal additions to `sim/engine.py`, `sim/scenario.py`, `sim/logging.py` (instantiate
  MessageBus; parse failure_modes + llm YAML blocks; write `messages.jsonl`).
- All three locked failure-mode injection axes (strategic, noisy, comm), each as an
  orthogonal scenario knob.
- Mock-LLM integration tests demonstrating the end-to-end pipeline runs deterministically
  on Phase 1.6 stress scenarios and that each failure-mode axis produces measurable
  degradation versus the clean cell.
- 2–3 cache-warmed reference runs (Haiku, real LLM) on `haves_havenots.yaml` so the
  spec's claims are backed by numbers in `runs/` before Phase 3 begins the full sweep.
- Determinism preserved: cache-warm replays produce byte-identical
  `state.jsonl` / `events.jsonl` / `messages.jsonl`.

**Out of scope (deferred):**

- Full Phase 3 sweep across {scenarios × strategies × seeds × failure cells × model
  tiers}.
- Multi-tier model ablation table (Haiku / Sonnet / Opus / open-source) — Phase 3.
- Needs-weighted welfare — Phase 3 (advisor-confirmed).
- Explainability metric — Phase 3 (the rationale field of every message is the data
  substrate for it; the metric itself is Phase 3).
- Web demo — Phase 4.

---

## Section 1 — Architecture overview

A per-household `LLMAgent` lives in a new `sim/agents/` package. Agents communicate
through a `MessageBus` owned by the engine. A thin `sim/strategies/llm_agent.py` wires
this into the existing Phase 1.6 plug-point with no breaking changes to non-LLM
strategies.

### Component map

```
sim/
  engine.py                   # +1 optional arg: MessageBus; +1 log stream: messages.jsonl
  agents/                     # NEW package
    __init__.py
    agent.py                  # LLMAgent: observe → memory → reflect → plan → act
    memory.py                 # MemoryEntry, MemoryStream, top-K retrieval
    reflection.py             # Reflection LLM call (Park-adapted)
    policy.py                 # Policy dataclass + YAML round-trip + validator
    protocol.py               # Message (speech act) + MessageBus
    llm.py                    # LLMClient adapter (Anthropic + optional OpenRouter)
    cache.py                  # PromptCache (sha256-keyed, on-disk)
    failure_modes.py          # FailureModeConfig + injection helpers
  strategies/
    llm_agent.py              # NEW, thin: prepare() + decide_transfers()
```

Each `sim/agents/*` file is intended to stay under ~300 lines, single responsibility,
with unit tests that use a mock `LLMClient` so no module's tests touch the API.

### Per-tick flow (additions only — Phase 1.x physics flow is preserved)

1. **Setup** (once, in `prepare`): instantiate one `LLMAgent` per household, bind them
   to a shared `MessageBus`, install the configured `FailureModeConfig`. Strategies that
   don't define `prepare` are unaffected.
2. **Each tick** (additions only — physics is unchanged):
   - `MessageBus.deliver_pending(t)` drains messages sent at `t-1` into each agent's
     inbox, applying failure-mode dropout and budget enforcement.
   - Each `LLMAgent.observe(t, own_state_visible, peer_state_visible, inbox)` updates its
     memory. *Visible* state is the engine's true state run through the noise-injection
     layer when noise is enabled.
   - If the agent's policy is stale (TTL expired) or a trigger fired (outage onset, SoC
     threshold cross, important inbound message), the agent runs one combined `reflect +
     plan` LLM call (split is reserved as an ablation), updating both its `MemoryStream`
     beliefs and its current `Policy`.
   - Each inbound `REQUEST` / `OFFER` triggers a short `react_to_message` LLM call
     producing an `ACCEPT` / `REJECT` / `COUNTER` with NL rationale.
   - The strategy's `decide_transfers(t, ...)` asks each agent for its tick's
     transfer intents via `LLMAgent.act(state)` — *pure Python*, no LLM, executes
     the current policy against current state.
   - Existing settle/step pipeline runs unchanged.
   - Engine logs the full message history of the tick to `messages.jsonl` with
     per-message `delivered` / `dropped(reason)` annotation.

### Why this shape

- The engine remains the physics owner; the agent layer is pluggable behind the
  existing strategy interface. Non-LLM strategies (`no_coordination`, `round_robin`,
  `round_robin_overlay`, `lp_optimal`) are byte-identically unchanged.
- The thin strategy facade owns the agent registry and message bus *instance*, so
  there is no module-level singleton — `sim/`'s "no global state" convention holds.
- Each `sim/agents/*` module is small enough to test exhaustively with a mock LLM.
  Ablations (no-reflection, sliding-window memory, no-rationale) become config
  flags, not forks.
- `messages.jsonl` was reserved by the Phase 1 output spec; we use the slot as
  intended.

### Engine signature change

`engine.run(...)` gains an optional `message_bus: MessageBus | None = None` parameter.
If `None`, the engine constructs a no-op bus (no agents, no messages, no logging).
Existing callers (which don't pass one) are byte-identically unchanged.

---

## Section 2 — Agent internals

### Per-tick lifecycle inside one `LLMAgent`

```
observe(t, own_state, visible_peer_state, inbox)
  └─ append to MemoryStream (cheap, no LLM)

if policy_stale or trigger_fired:               # typical: every 4 ticks (1 h) OR event
  memories = retrieve(top-K by recency × importance × similarity)
  reflect + plan                                 # ONE collapsed LLM call by default
    └─ updates belief notes + emits new Policy + (optionally) outbound INFORM / REQUEST

for each REQUEST / OFFER in inbox (up to react_max_per_tick):
  react_to_message                               # short LLM call: ACCEPT / REJECT / COUNTER

act(state)                                       # PURE PYTHON: policy + state → list[Transfer] + outbox
```

Triggers (explicit list — anything else is a stale-TTL re-plan):

- **outage onset** (this tick is the first islanded tick of an `OutageWindow`),
- **SoC threshold cross** with hysteresis: SoC fraction crosses
  `policy.share_min_soc_frac ± 0.10` in either direction (so brief jitter doesn't
  trigger; sustained change does),
- **important inbound message**: any `INFORM` whose payload SoC differs from the
  last-known peer state by ≥ 0.15 fraction, OR any `REJECT` to one of our recent
  `REQUEST`s.

`react_max_per_tick` defaults to 3 (per-agent, per-tick). Excess `REQUEST`/`OFFER`
inbound is queued for next tick or dropped after a configurable `react_queue_ttl_ticks`
(default 4), logged `REACT_DEFERRED` / `REACT_DROPPED`. This caps reactive LLM cost
even under message-flood attack from defectors.

### Memory stream

`MemoryEntry`:

```python
@dataclass(frozen=True)
class MemoryEntry:
    t: datetime
    kind: Literal["obs", "msg_sent", "msg_recv", "transfer_outcome", "reflection"]
    content: dict          # structured (kwargs vary by kind)
    nl: str                # short NL description for LLM consumption
    importance: float      # 0..10
```

Importance is heuristic for `obs` / `msg_*` / `transfer_outcome` (e.g., big SoC change,
unexpected refusal, large transfer) and LLM-set for `reflection` entries.

Retrieval (`MemoryStream.top_k(query_nl, k=20)`) ranks by
`α·recency + β·importance + γ·similarity(query, nl)`, with `α=β=0.4, γ=0.2` as defaults.
Similarity is cosine over a lightweight embedding cached locally; if no embedder is
configured, similarity defaults to `1.0` (i.e., only recency × importance) to keep
unit tests free of model dependencies.

### Reflection

Reflection is a short LLM call (≤500 output tokens) that takes recent memories and
produces 1–3 belief statements:

> *"Peer r2c3 has refused 4/5 of my last requests."*
> *"My solar yield was 30% below forecast over the last 4 ticks."*
> *"Owner-group peers reciprocated 3/3 offers in the past hour."*

Each belief is stored as a high-importance `reflection` memory and included in
subsequent plan prompts. This is the Park-adapted abstraction step; it is what
enables strategic-agent and noisy-observation failure modes to be addressed by the
agent's own reasoning rather than by an externally-engineered detector.

### Policy schema (machine-executable, no LLM at act-time)

```yaml
sharing_intent: conservative | balanced | generous
share_min_soc_frac: 0.50           # only share if SoC ≥ this
max_share_kw_per_tick: 1.5
recipient_priority:                 # over union_neighbors, by trust-circle membership
  - {circle: owner,           weight: 1.0}
  - {circle: hoa,             weight: 0.7}
  - {circle: dr_aggregator,   weight: 0.6}
  - {circle: geographic,      weight: 0.4}
distrusted_peers: [r2c3, r4c1]      # populated by reflection
request_urgency: low | normal | urgent
belief_note: "owner-group peers reciprocated 3/3 in past hour; r2c3 refused 4/4"
ttl_ticks: 4
```

The policy is YAML-validated on load by a hand-rolled validator in `sim/agents/policy.py`
(no new dependency; the schema is small and stable). Malformed LLM output triggers a
fallback to the
previous policy and logs `POLICY_PARSE_FAILED`; persistent failure (3+ ticks) falls back
to the geographic `round_robin` policy and logs `POLICY_FALLBACK_TO_ROUND_ROBIN`.

### Plan + reflection prompt shape

> *"You are household {hid}. You are in trust circles: {owner=owner_acme,
> hoa=hoa_north, dr_aggregator=agg_gridflex, geographic=[r0c1, r1c0, ...]}. Your
> recent observations and exchanges: {top-K memories}. Your current beliefs:
> {previous reflections}. Current state: SoC={…}, grid_islanded={…}, last_tick_load=…,
> last_tick_solar=…. Output (1) a one-paragraph belief summary, (2) a Policy YAML, and
> (3) optionally one or two INFORM / REQUEST messages to send."*

Trust-circle memberships are surfaced **by name** so the LLM can reason about them
(the Phase 1.6 advisor mandate: trust-circle overlays are the substrate where NL
coordination should outperform fixed protocols). The policy's `recipient_priority`
weights are how that reasoning becomes machine-executable.

### Tick-executor (`act(state)`, pure Python)

- If islanded AND `state.soc_frac ≥ policy.share_min_soc_frac`:
  - compute `headroom_kwh = max(0, soc - dod_floor·capacity)`,
  - `candidates = union_neighbors(self) − policy.distrusted_peers`,
  - distribute `min(SHARE_FRACTION × headroom_kwh, max_share_kw_per_tick × dt)`
    over candidates proportional to `policy.recipient_priority[circle]`,
  - emit one `OFFER` message per recipient (structured kwh + 1–2 sentence NL
    rationale).
- If islanded AND SoC low (below `share_min_soc_frac` − 0.1): emit `REQUEST` messages
  to peers in priority order, urgency from `policy.request_urgency`.
- Else: no action.

### Per-agent RNG (determinism-critical)

Each agent owns a `random.Random` instance seeded as
`hash((scenario.seed, "agent", house_id))`. Used only for tie-breaking among
equal-priority recipients and any local ordering decisions. Engine-owned, passed in
at `__init__`. No `random.random()` calls without going through this RNG.

### Strict-mode invariants (asserted every tick when strict)

- Sum of agent's outbound `Transfer.kw` ≤ `headroom_kwh / dt`.
- No `Transfer` whose `to_id ∉ union_neighbors(self)`.
- `policy.ttl_ticks ≥ 1`.
- `MemoryStream` is append-only (no deletes/edits).
- Every outbound message has a non-empty `rationale_nl` (≥ 1 char) when the
  scenario's `llm.require_rationale: true` (default).

### Cost back-of-envelope (Haiku 4.5, per scenario-day, 30 houses)

| LLM call type | Count / day | Tokens (in / out) | Cost |
|---|---|---|---|
| reflect+plan (combined) | 24 × 30 = 720 | ~2500 / ~600 | ~$1.20 |
| react_to_message | ~500–1500 | ~1200 / ~200 | ~$0.60 |
| **Total** | **~1200–2200** | — | **~$1.50–2.00** |

Replays from cache cost $0. Seed variants without cache pay full.

---

## Section 3 — Message protocol + bus + comm constraints

### Message schema

```python
@dataclass(frozen=True)
class Message:
    t_sent: datetime
    sender: str
    recipient: str         # one peer per Message; broadcasts emit N
    performative: Literal["REQUEST","OFFER","ACCEPT","REJECT","COUNTER","INFORM"]
    payload: dict          # structured: {kwh: float, deadline_tick: int, ...}
    rationale_nl: str      # 1–3 sentences
    correlation_id: str    # threads a negotiation
```

Performatives follow speech-act / FIPA-ACL tradition; the vocabulary is small enough
to be model-agnostic and avoid LLM-judge evaluation. `correlation_id` lets us
reconstruct negotiations in `messages.jsonl` post-hoc.

### MessageBus

Responsibilities:

- **Queue:** messages sent at tick `t` are delivered at tick `t+1`. One-tick latency
  models communication round-trip and breaks within-tick chicken-and-egg ordering.
- **Routing:** validates `recipient ∈ union_neighbors(sender)`. Off-graph messages
  are dropped + log `INVALID_RECIPIENT` event.
- **Dropout:** consults `failure_modes.comm.drop_prob_by_circle` per edge per
  message; dropped messages are logged with `reason: comm_drop`.
- **Budget:** enforces `failure_modes.comm.per_tick_budget` on each sender;
  excess outbound is dropped (oldest-first or random per RNG) with
  `reason: budget_overflow`.
- **Logging:** every send and every delivery decision is written to `messages.jsonl`
  with the outcome.

Comm-failure determinism: the bus owns a deterministic RNG seeded from
`scenario.seed` (`hash((scenario.seed, "bus"))`). Dropout draws are seeded; replays
produce identical drop sequences.

---

## Section 4 — Failure-mode injection

All three locked failure modes are independent scenario knobs. Sweep cells:
`{clean, defectors_only, noise_only, comm_only, all_combined}`. Each can be applied
without modifying the others.

### Scenario YAML schema (added under top-level `failure_modes:` block)

```yaml
failure_modes:
  defector_fraction: 0.20            # 0..1; fraction of houses that are selfish
  defector_assignment: random        # | by_circle | manual
  defector_house_ids: []             # populated when assignment: manual
  defector_realization: prompt       # | wrapper | both
  obs_noise:
    soc_std_frac: 0.05               # σ as fraction of capacity (per tick, fresh draw)
    load_std_frac: 0.10              # σ as fraction of true load
    solar_forecast_horizon_ticks: 4
    solar_forecast_std_frac: 0.20
  comm:
    drop_prob_by_circle:
      geographic: 0.15
      owner: 0.02
      hoa: 0.05
      dr_aggregator: 0.05
    per_tick_budget: 5               # max msgs sent per agent per tick
```

Every dropped message (comm-drop or budget-overflow) is recorded in
`messages.jsonl` with its `reason` field. Agents never see drops directly — they
must infer from peer silence over multiple ticks (this is what reflection has to
chew on for the comm-constrained failure mode).

Defaults are all zero/off (`failure_modes: {}` == clean cell), preserving Phase 1.6
behaviour for any scenario that omits the block.

### Defector realization

- **`prompt`:** the agent's system prompt is replaced with a "selfish" template
  whose behaviour is documented and tracked. The selfish template instructs the
  agent to prioritize own household survival and permits (but does not require)
  misreporting SoC / needs to neighbors. The agent's LLM may refuse such
  instructions — that refusal is itself measured and reported.
- **`wrapper`:** cooperative system prompt, but a `DefectorWrapper` mutates
  outbound messages before `MessageBus.send` ingests them (e.g., scales claimed
  `kwh` by a per-agent random factor in `[0.5, 1.5]`). The agent does not know it
  is lying. This is the clean control for "channel corruption" separate from "LLM-
  driven defection".
- **`both`:** independent ablation cell — selfish prompt AND wrapper. Rarely the
  realistic story; useful as a worst-case bound.

Assignment determinism: `hash((scenario.seed, "defector_assignment"))` seeds the
selection of defector house IDs; replays select the same houses.

### Noise injection

Engine maintains a `NoiseSource` (its own deterministic RNG, seeded from
`scenario.seed`) that adds Gaussian noise to per-agent observations *before* the agent
sees them. Physics still uses true state — only the agent's *visible* state is
corrupted. This is the standard partially-observable-MDP shape and keeps the engine
honest while letting the agent reason under uncertainty.

**Scope of noise:** the noise applies to (a) the agent's view of *own* state (SoC,
last-tick load, last-tick solar) and (b) the agent's view of *peer* state when the
peer state arrives via INFORM messages. INFORM messages carry the peer's noisy
self-view, *not* the engine's true peer state — so noise stacks naturally with
strategic misreporting under the `defector_realization: wrapper` cell. The agent
does not have any out-of-band "ground truth" channel.

### Comm constraints

See §3 — implemented in `MessageBus`. Per-edge drop probability and per-tick send
budget. `drop_prob_by_circle` lets us model the advisor's intended scenario where
owner-group edges are reliable but geographic edges are flaky, so reflection should
learn to prefer the reliable routes.

---

## Section 5 — Prompt cache + determinism

### On-disk layout

```
runs/<scenario_id>/<strategy>/<timestamp>/
  state.jsonl
  events.jsonl
  messages.jsonl
  config.json
  summary.json
  llm_cache/
    <model_name>/
      <sha256-of-prompt>.json
```

Each cache file: `{prompt, response, model, temperature, max_tokens, t_iso}`.

Cache key:

```
sha256(json({model, system, user, temperature, max_tokens, tools_schema}, sort_keys=True))
```

Temperature is fixed at `0.0` everywhere (research-grade replayability >
output-diversity here).

### Replay semantics

- On `LLMClient.call(prompt)`:
  1. compute `key`,
  2. if `runs/<scenario>/<strategy>/<ts>/llm_cache/<model>/<key>.json` exists
     (run-local cache, populated by prior runs in this output dir) → return,
     log `cache_hit:local`,
  3. else if `reference_runs/<scenario>/<strategy>/<failure_cell>/llm_cache/<model>/<key>.json`
     exists (reference cache, in-repo for shipped reference runs) → return,
     log `cache_hit:reference`,
  4. else → API call, write cache file (atomic via temp + rename) into the
     run-local cache, return response, log `cache_miss`.
- The in-repo `reference_runs/` directory (see §6) is the reproducibility artifact
  shipped with the paper. On any machine: clone the repo, re-run the same scenario
  YAML, get byte-identical `state.jsonl` / `events.jsonl` / `messages.jsonl` because
  every LLM call hits the reference cache.

### Determinism invariant

For any scenario whose cache is fully populated, two runs of `python -m scripts.run
--scenario <yaml>` produce byte-identical `state.jsonl`, `events.jsonl`, and
`messages.jsonl`. This is asserted in the integration test
`test_llm_agent_replay_determinism`.

For new runs (cache miss), the run is *not* claimed deterministic — that's the cell
where the API is being hit and a new cache entry is being created.

### Concurrency note

The cache supports multiple readers; writes are atomic (temp file + rename).
Parallel runs of the same scenario share the cache directory safely. In v0, runs are
sequential, so this is more of a future-proofing detail.

---

## Section 6 — Scope, reporting, and integration with Phase 1.6 surfaces

### `summary.json` compatibility

The LLM strategy emits the same `summary.json` schema as Phase 1.x strategies
(`served_load_fraction`, `gini_welfare`, `wasted_kwh_total`, `unmet_kwh_total`,
`transfer_count`). This means it drops directly into `scripts/compare.py` from Phase
1.6 Task 15 with no changes — gap-closed reporting works out of the box.

Additional Phase 2-specific fields appended to `summary.json` (do not break Phase 1.x
parsers — extra keys ignored):

```json
{
  "llm_call_counts": {"reflect_plan": 720, "react_msg": 432, "cache_hits": 1130, "cache_misses": 22},
  "llm_cost_usd_estimated": 1.82,
  "message_counts": {"sent": 1840, "delivered": 1500, "dropped_comm": 271, "dropped_budget": 49, "dropped_invalid_recipient": 20},
  "failure_modes_active": {"defector_fraction": 0.2, "obs_noise_soc_std_frac": 0.05, "comm_per_tick_budget": 5},
  "policy_parse_failures": 3,
  "policy_fallbacks_to_round_robin": 0
}
```

### Reference runs shipped with this phase

`runs/` is gitignored (Phase 1 convention). Reference runs that ship in-repo so
reviewers and future-Leo can replay without paying live the new top-level directory
`reference_runs/` (added to git, NOT gitignored). Layout mirrors `runs/`:

```
reference_runs/<scenario>/<strategy>/<failure_cell>/
  state.jsonl
  events.jsonl
  messages.jsonl       (truncated excerpt; full version lives in runs/)
  config.json
  summary.json
  llm_cache/<model>/<sha256>.json
```

At minimum, three cache-warmed reference runs ship with Phase 2:

1. `haves_havenots.yaml`, llm_agent, clean — primary gap-closed number versus the
   four Phase 1.6 strategies.
2. `haves_havenots.yaml`, llm_agent, defectors_only (fraction 0.2) — robustness
   smoke.
3. `long_outage_72h.yaml`, llm_agent, clean — long-horizon memory/reflection smoke.

`LLMClient.call(prompt)` checks the run-local cache first
(`runs/<scenario>/.../llm_cache/`), then the reference cache
(`reference_runs/<scenario>/.../llm_cache/`), then hits the live API. Cache
lookup is content-addressed (sha256 of full prompt), so reference and live runs
share entries when prompts match.

---

## Section 7 — Testing strategy

TDD throughout, per project conventions (`red → minimal green → commit`). All tests
that exercise the LLM use a `MockLLMClient` that returns canned JSON responses; no
real API calls in CI.

### Unit tests

- **`MemoryStream`:** append-only invariant; retrieval rank order with hand-built
  entries; importance heuristics deterministic given seed; JSON round-trip.
- **`Reflection`:** with mock LLM returning a fixed JSON, reflection entries are
  appended to memory with correct importance and `kind`.
- **`Policy`:** YAML round-trip; validator accepts valid; rejects (a) negative
  weights, (b) `ttl_ticks < 1`, (c) malformed `recipient_priority`; fallback to
  previous policy on parse failure.
- **`MessageBus`:** delivery one tick later; routes only through `union_neighbors`;
  dropout determinism (same seed = same drop sequence); budget enforcement counts
  correctly; all log entries written to `messages.jsonl` with correct outcomes.
- **`PromptCache`:** hit/miss; atomic writes survive simulated kill mid-write;
  collision on same key returns same response; portable across machines (key is
  content-only).
- **`FailureModes`:** noise stream determinism; defector assignment determinism;
  comm dropout determinism.
- **`LLMAgent.act(state)`** (PURE PYTHON, no LLM): given a fixed Policy and state,
  emits the expected list of `Transfer`s and outbox messages. This is the workhorse
  test of the tick-executor.
- **`LLMClient`:** with HTTP-level mock, retries on 429 / 5xx with exponential
  backoff; respects `temperature=0`; cache integration works.

### Integration tests (mock LLM, mock = canned responses keyed by prompt shape)

- **End-to-end run on `haves_havenots.yaml`** with `llm_agent` strategy: produces
  the full output tree (state/events/messages/summary), and `summary.served_load_fraction`
  is strictly greater than `round_robin`'s.
- **Determinism (replay):** two cache-warm runs of the same scenario produce
  byte-identical `state.jsonl` / `events.jsonl` / `messages.jsonl`.
- **Failure-mode axes:**
  - `defector_fraction=0.2` produces `served_load_fraction` strictly less than the
    clean cell.
  - `obs_noise.soc_std_frac=0.10` measurably changes per-agent decisions vs clean.
  - `comm.per_tick_budget=2` produces fewer delivered messages and (usually) lower
    served-load fraction than the clean cell.
- **`prepare` hook:** confirmed to fire exactly once before tick loop; existing
  myopic strategies (`no_coordination`, `round_robin`, `round_robin_overlay`,
  `lp_optimal`) byte-identically unchanged.

### LLM live tests (gated by env var, excluded from CI)

`pytest -m llm_live`: one tiny scenario (5 ticks, 2 houses), one real Haiku call,
asserts the adapter shape works against the live API. Useful for catching SDK or
schema drift; never blocks development.

### CI invariants

- `pyproject.toml` change → mandatory clean-install dry-run in
  `/tmp/microgrid_ci_check` (per the 2026-05-14 burned-once lesson encoded in
  workflow preferences). Adding `anthropic` (and optionally `openai` if we add an
  OpenRouter/Groq adapter for the open-source tier) triggers this.
- `ruff` + `mypy --strict` extend over `sim/agents/` and `sim/strategies/llm_agent.py`.
- `llm_live` excluded from default `pytest` invocation.

---

## Section 8 — Components touched / added

| Path | Change |
|---|---|
| `sim/agents/__init__.py` | new |
| `sim/agents/agent.py` | new — `LLMAgent` (observe / remember / reflect+plan / react / act) |
| `sim/agents/memory.py` | new — `MemoryEntry`, `MemoryStream`, top-K retrieval |
| `sim/agents/reflection.py` | new — Park-adapted reflection LLM call wrapper |
| `sim/agents/policy.py` | new — `Policy` dataclass + YAML round-trip + validator + fallback |
| `sim/agents/protocol.py` | new — `Message`, `MessageBus` |
| `sim/agents/llm.py` | new — `LLMClient` (Anthropic; optional OpenRouter / Groq), retries, caching |
| `sim/agents/cache.py` | new — `PromptCache` (sha256-keyed, atomic on-disk) |
| `sim/agents/failure_modes.py` | new — `FailureModeConfig` + injection helpers (defector/noise/comm) |
| `sim/strategies/llm_agent.py` | new — thin facade: `prepare()` + `decide_transfers()` |
| `sim/engine.py` | minimal: instantiate `MessageBus`; pass to strategies; log `messages.jsonl` |
| `sim/scenario.py` | extend YAML schema: `failure_modes:` block, `llm:` config block (model, cadence, require_rationale) |
| `sim/logging.py` | add `messages.jsonl` writer; extend `summary.json` schema with Phase 2 fields (purely additive) |
| `configs/scenarios/*.yaml` | extend `haves_havenots.yaml` with `llm:` and (default-zero) `failure_modes:` blocks; add 4 failure-cell variants of the showcase scenario |
| `pyproject.toml` | add `anthropic>=0.40` (+ optional `openai` for OpenRouter/Groq adapter) |
| `.gitignore` | add `runs/` (already gitignored), keep `reference_runs/` tracked |
| `reference_runs/` | new top-level directory (git-tracked) for the three Phase 2 reference runs (state/events/messages/summary/llm_cache); see §6 |
| `tests/` | new tests per Section 7 |
| `docs/superpowers/specs/2026-06-13-phase2-llm-agent-design.md` | this spec |

---

## Section 9 — Known limitations / non-goals (paper-honesty register)

These are explicit limitations to surface in the paper's discussion section. Each
mirrors the framing posture the advisor flagged on 2026-05-26.

- **Not deployment-ready.** This is a research artifact. No security review, no
  operational hardening, no integration with real DERMS / utility infrastructure.
  The advisor specifically warned against any deployment-readiness claim.
- **Strategic-agent realization assumes the LLM follows the selfish prompt.** Some
  models refuse instructions to misreport; the refusal rate per model is itself a
  reportable result, not a design failure. We measure it.
- **Strategic / robustness framing is not adversarial security.** Per advisor
  guidance, we frame defector-detection as *robustness to misreporting peers*, not
  as defense against adversaries. No threat model, no Byzantine analysis.
- **Determinism is cache-conditional.** Cache-warm replays are byte-identical;
  fresh runs (cache miss) hit the API and inherit whatever residual nondeterminism
  the provider exhibits even at `temperature=0`. The paper's
  reproducibility artifact is the cache.
- **Comm dropout is per-edge probabilistic.** Bursty / correlated failures and
  partition events are not modeled in v0.
- **Noise model is Gaussian.** No systematic sensor drift, no calibration error.
- **No synchronous multi-round negotiation** in v0; messages are exchanged
  reactively across consecutive ticks. A multi-round variant is held in reserve as
  a possible ablation if the reactive baseline underperforms.
- **Welfare is served-load fraction** (advisor-confirmed Phase 2). Needs-weighted
  welfare is Phase 3.
- **Explainability metric is not implemented in Phase 2.** The `rationale_nl` field
  on every message and the `belief_note` field on every Policy are the data
  substrate that Phase 3's metric will consume.
- **Equity framing** uses Gini over served-load fraction (Phase 1.x baseline). A
  proper equity discussion (Sovacool's energy-justice work) is part of the paper
  writeup, not the simulator.

---

## Section 10 — Mapping to advisor feedback (2026-05-26)

| Advisor ask | Where addressed |
|---|---|
| Failure mode: strategic / selfish agents | §4 — `defector_fraction` + `defector_realization: prompt | wrapper | both` |
| Failure mode: noisy / faulty observations | §4 — `obs_noise` (SoC + load + solar forecast) |
| Failure mode: communication constraints | §3 + §4 — `comm.drop_prob_by_circle` + `per_tick_budget` |
| Park et al. as architecture reference, *not fork* | §2 — `MemoryStream` + `Reflection` reimplemented; cited in spec preamble + module docstrings |
| Trust-circle / overlay structure is *the* substrate | §1 — `MessageBus` routes through `union_neighbors`; §2 — policy schema names trust circles by name and weights recipients per circle |
| Centralized LP upper bound + "% of gap closed" framing | §6 — LLM strategy emits Phase 1.x-compatible `summary.json`; drops into `scripts/compare.py` from Phase 1.6 Task 15 unchanged |
| Served-load fraction OK for Phase 2 | §9 — retained; needs-weighting deferred to Phase 3 |
| Don't oversell strategic-agent failure as adversarial security | §9 — explicitly framed as robustness, not adversarial defense |
| Don't claim deployment-ready | §9 — explicit non-deployment statement |
| Equity framing care | §9 — limitations section flags Sovacool reading for paper writeup |
