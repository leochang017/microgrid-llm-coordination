# Phase 3 Benchmark & Experiments — Implementation Plan

> **For agentic workers:** Execution mode is INLINE per CLAUDE.md conventions — TDD,
> one commit per task, progress-log row + checkbox tick in the same commit.
> Spec: `docs/superpowers/specs/2026-07-07-phase3-benchmark-design.md`.

**Goal:** Make the three paper pillars measurable: causally-coupled failure modes
(information-flow rework), needs-aware fairness metrics, an explainability instrument,
and the sweep machinery to run it all at multi-seed scale.

**Architecture:** All agent-layer changes live in `sim/agents/` + the
`sim/strategies/llm_agent.py` facade; engine and physics are untouched (Phase 2.9
finished those). New scripts: `sweep.py`, `eval_explanations.py`.

## Global constraints

- TDD; mypy --strict + ruff clean per commit; determinism mandatory (mock replay
  byte-identical on both parse paths).
- `llm_fallback` must remain meaningful after every task (no LLM ⇒ pure executor).
- Live API runs are budget-gated: NOTHING in this plan performs a live LLM call.
- Golden pins updated only when a task intentionally changes behavior, same commit.

---

### Task 1: Spec + plan committed
- [x] Commit spec + this plan with progress-log row.

### Task 2: PeerBelief store + INFORM emission
- [x] `sim/agents/agent.py`: `PeerBelief` dataclass (soc_kwh, soc_capacity, t_idx_reported); `LLMAgent.peer_beliefs: dict[str, PeerBelief]`.
- [x] `observe()` updates beliefs from INFORM messages in the inbox (latest t_idx wins).
- [x] `act()` emits one INFORM per union-neighbor per tick carrying the NOISED self-view (payload keys: `soc_kwh`, `soc_capacity`); pure Python, no LLM.
- [x] Facade bus-send ordering per tick: react replies → act() REQUEST/OFFER → INFORMs.
- [x] Tests: belief created/updated from INFORM; noised value (not truth) in payload; ordering observable via bus log.
- [x] Commit `feat: message-borne peer beliefs (INFORM emission + belief store) (P3 T2)`.

### Task 3: Cut the ground-truth feed
- [x] Facade `observe()` call no longer receives `peer_states` built from engine states; plan-prompt peers section renders `peer_beliefs` with age ("reported N ticks ago"); `act()` recipient filter consumes beliefs; unknown peers ineligible.
- [x] Update `test_llm_agent_failure_axes.py`: noise and comm cells must now produce measurable outcome deltas vs clean (the assertions the old architecture couldn't satisfy).
- [x] Replay determinism (both parse paths) still byte-identical; golden clean-cell mock numbers re-derived if moved (same commit).
- [x] Commit `feat!: agents decide on message-borne beliefs, never engine ground truth (P3 T3)`.

### Task 4: act() uses the noised own view
- [x] `observe()` stashes the visible own-state snapshot; `act()` reads it instead of the facade-passed raw state (facade keeps passing raw for capacity bookkeeping only).
- [x] Test: with soc noise configured, act()'s share decisions differ from the zero-noise run on the same seed.
- [x] Commit `feat: act() decides on the agent's noised self-view (P3 T4)`.

### Task 5: Binding negotiation (REQUEST sizing + commitments)
- [x] REQUEST kwh = estimated next-tick deficit from the noised view (replaces hardcoded 0.5); payload carries `kwh` + `deficit_estimate`.
- [x] React replies parse a committed amount (`ACCEPT 0.4` / `COUNTER 0.2`; bare ACCEPT ⇒ requested amount, counted in `n_react_amount_defaulted`).
- [x] `LLMAgent.commitments` ledger (recipient, kwh_remaining, expires 2 ticks); `act()` serves commitments first, then residual policy-driven sharing; commitments respect policy caps.
- [x] Tests: request sizing math; ACCEPT creates commitment; commitment produces a transfer next tick; TTL expiry counted; llm_fallback unchanged (no commitments path).
- [x] Commit `feat: binding negotiation — need-sized REQUESTs and ACCEPT-gated commitments (P3 T5)`.

### Task 6: Failure-axis acceptance tests
- [x] Mock-LLM end-to-end: defector(wrapper) corruption moves outcomes (prompt-realization hoarding needs a live selfish-prompt run — budget-gated); noise cell — served/transfer deltas vs clean; comm cell — delivered/sent drop AND outcome delta.
- [x] Document effect sizes in the progress log (these become the paper's mock sanity row).
- [x] Commit `test: failure axes now causally couple to outcomes (P3 T6)`.

### Task 7: Fairness substrate
- [ ] `household_sampling.critical_load_frac: [lo, hi]` sampling → `Household.profile` field; accounting rule: unmet hits flexible first.
- [ ] Summary additions: `served_critical_load_fraction`, `min_house_served_fraction`, `jains_index` (+ unit pins: hand-computed Jain cases).
- [ ] Commit `feat: needs-aware fairness metrics (critical load, Rawlsian floor, Jain) (P3 T7)`.

### Task 8: Explainability substrate
- [ ] messages.jsonl rationale entries flagged `templated: true/false`; llm_agent rationales trace to LLM output.
- [ ] `scripts/eval_explanations.py`: rubric LLM-judge over sampled messages/policies, PromptCache-backed, `--mock` mode for tests; 3-axis rubric per spec.
- [ ] Commit `feat: explanation provenance + rubric judge harness (P3 T8)`.

### Task 9: Override + sweep machinery
- [ ] `run.py --set dotted.key=value` (repeatable) with type coercion + unknown-key rejection.
- [ ] `scripts/sweep.py`: grid YAML → subprocess-per-cell runs → harvested matrix + dose-response markdown; `configs/sweeps/phase3_grid.yaml` with spec defaults.
- [ ] Commit `feat: scenario overrides + sweep driver for dose-response grids (P3 T9)`.

### Task 10: Showcase-tight scenario
- [ ] Scan bus_max_kw / bimodal params (free strategies only) for a materially larger rr→LP gap; ship best as `haves_havenots_tight.yaml` + goldens + compare table in docs.
- [ ] Commit `feat: showcase-tight scenario with material rr→LP headroom (P3 T10)`.

### Task 11: Mock benchmark pass + wrap
- [ ] Full mock-LLM sweep (all cells × strategies × 5 seeds) via sweep.py; tabulate; record in README Phase 3 section + CLAUDE.md.
- [ ] Deferred/live items table verbatim from spec Part E; tag `phase3-infra-complete`.
- [ ] Commit `docs: Phase 3 infrastructure complete — mock benchmark matrix (P3 T11)`.
