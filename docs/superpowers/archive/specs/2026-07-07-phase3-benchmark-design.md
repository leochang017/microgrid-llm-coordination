# Phase 3 — Benchmark & Experiments (Design Spec)

**Date:** 2026-07-07
**Status:** Approved for infrastructure execution (user: "continue with phase 3").
Items marked **[ADVISOR]** are provisional defaults that should be confirmed in the next
advisor sync before the paper freezes on them; none block implementation.

## What Phase 3 must produce

The paper's evidence. Three pillars, each currently unsupported:

1. **(a) Fairness** — needs-aware metrics beyond Gini-over-served-fraction.
2. **(b) Robustness** — failure-mode cells (defectors / noise / comm) where outcomes
   *causally depend* on information quality. Today they do not: agents read engine
   ground truth, so every failure injection is decorative (verified in the 2026-07-06
   review; the repo's own tests admit it).
3. **(c) Explainability** — an instrument that scores explanations, over rationales
   that are actually LLM-authored.

Plus the experimental machinery: multi-seed sweeps, dose-response grids, and controls
(`llm_fallback` 0.518 is the number to beat; messaging-off isolates the NL channel).

> **[CORRECTED 2026-07-12]** The benchmark scenario became `haves_havenots_solar` (T10); the zero-LLM control there was 0.6910 pre-Phase-3.1 and is re-pinned in `tests/test_golden_numbers.py` after the Phase 3.1 behavior fixes — trust the pin, not this line. 0.518 was the old 12 h `haves_havenots__llm` control.

## Part A — Information-flow rework (validity prerequisite; blocks ALL live failure-cell runs)

### A1. Message-borne peer beliefs (INFORM-only)

- Every tick, each agent emits one INFORM per `union_neighbors` peer carrying its
  **noised self-view** (`soc_kwh_reported`, `soc_capacity`) — pure Python, no LLM call.
- `LLMAgent.peer_beliefs: dict[hid, PeerBelief(soc_kwh, soc_capacity, t_idx_reported)]`
  updated ONLY from received INFORMs. The facade **stops passing ground-truth
  `peer_states`** into `observe()`.
- Consequences (these are the point): observation noise now reaches peers; comm dropout
  and budget destroy knowledge; the DefectorWrapper's INFORM corruption finally lands on
  a consumer; beliefs go stale (one-tick bus latency minimum).
- Peers with no belief yet are **not eligible transfer recipients** (you can't target
  who you know nothing about). Everyone INFORMs from tick 0, so beliefs populate by
  tick 1 in clean cells.
- Bus send ordering per tick (matters under `per_tick_budget`): react replies →
  REQUESTs/OFFERs → INFORMs (freshest need signals win; INFORM loss degrades gracefully).
- Plan-prompt "peers" section renders beliefs with age (`reported N ticks ago`), never
  ground truth.

### A2. Agents act on their own noised view

`act()` consumes the visible (noised) own state captured in `observe()`, not the raw
engine state the facade passes today. Physics settlement still uses TRUE state — agents
*decide* under uncertainty, the engine *executes* reality. That asymmetry is the
robustness experiment.

### A3. Binding negotiation

- **REQUEST sized by real need:** `kwh = max(0, (load - solar) * dt - deliverable_from_battery)`
  from the noised view (replaces the hardcoded 0.5).
- **ACCEPT creates a commitment:** an ACCEPT (or COUNTER, which commits at the countered
  amount — v1 simplification, logged) from A to B's REQUEST enters A's
  `commitments: list[(recipient, kwh_remaining, expires_t_idx)]` (TTL: 3 serviceable act() windows — the creation tick + the following 2; wording corrected 2026-07-12, behavior unchanged).
- **`act()` serves commitments first** (bounded by policy caps and physics), then shares
  residual headroom via the existing policy-driven executor. The executor path is what
  `llm_fallback` still exercises — no LLM ⇒ no reacts ⇒ no commitments ⇒ pure executor,
  so the control stays meaningful.
- React replies must carry a parseable committed amount (`ACCEPT 0.4` / `COUNTER 0.2`);
  unparseable amount ⇒ treat as the requested amount (logged counter).
- **[ADVISOR — confirmed 2026-07-15:** prompt-driven selfishness is the right implementation
  of strategic agents; wrapper corruption correctly kept as a separate failure mode.**]**
  Defector realizations under the new flow: `wrapper` = channel corruption
  (control condition); `prompt` = LLM briefed selfish (hoarding + reject-happy). True
  LLM-authored *misreporting* (agent lies in its own INFORM) is a stretch goal — v1 ships
  a `misreport_soc_frac` policy field only if time permits.

### A4. Acceptance for Part A (mock-LLM, all free)

The spec §7 assertions the old architecture could not satisfy must now hold:
- noise cell ≠ clean cell on served/transfers (beliefs perturb routing);
- comm cell: lower delivered/sent AND outcome change vs clean;
- defector(prompt) cell: defector households hoard measurably vs clean.

## Part B — Fairness substrate

- `household_sampling.critical_load_frac: [lo, hi]` (default absent = 0 ⇒ old behavior).
  Accounting rule (documented, standard): unmet energy hits flexible load first;
  critical unmet = `max(0, unmet - flexible_load)` per house-tick.
- New summary metrics (additive): `served_critical_load_fraction`,
  `min_house_served_fraction` (Rawlsian floor), `jains_index`.
- **[ADVISOR — confirmed 2026-07-15:** metric selection approved; complementary metrics over
  Gini-alone endorsed; give the efficiency-vs-equity tradeoff its own figure + discussion.**]**
  Read Sovacool before writing the fairness section; Gini stays reported
  but never alone. LP gini quoted max 2 dp (degenerate optima).

## Part C — Explainability substrate

- Every OFFER/REQUEST rationale and policy `belief_note` must be traceable to LLM output
  in llm_agent runs (templated fallbacks only in llm_fallback, marked `"templated": true`
  in messages.jsonl).
- `scripts/eval_explanations.py`: samples N messages + policies from a run dir, scores
  each 1-5 on a 3-axis rubric (state-accuracy vs logged reality, actionability,
  consistency with the sender's actual behavior that tick) via an LLM judge with the
  standard PromptCache (mock-tested; live judging is budget-gated).
- **[ADVISOR — confirmed 2026-07-15:** LLM-judge approved as practical; rubric must be fully
  transparent and the protocol must report inter-prompt / repeated-evaluation consistency
  (playbook Stage 4 sub-step); explanation quality stays secondary to coordination performance.**]**
  Rubric + LLM-judge (vs human study, infeasible pre-college) needed
  sign-off before paper claims.

## Part D — Experiment machinery

- `run.py --set dotted.key=value` generic scenario override (e.g.
  `--set failure_modes.defector_fraction=0.4`) so dose-response grids don't need
  hand-written YAML per point.
- `scripts/sweep.py`: scenarios × strategies × seeds × overrides, **subprocess per cell**
  (llm_agent registry constraint), summary.json harvest, markdown matrix + per-axis
  dose-response tables. Grid definitions in `configs/sweeps/*.yaml`.
- Failure-mode dose-response defaults: defector_fraction {0, 0.1, 0.2, 0.4};
  noise soc_std_frac {0, 0.05, 0.1, 0.2}; comm per_tick_budget {∞, 4, 2, 1}.
- Seeds: {23, 1, 7, 42, 99} everywhere; paired per-seed comparisons.
- Showcase-tight scenario: scan `bus_max_kw` / bimodal params for a materially larger
  rr→LP gap; ship the best as `haves_havenots_tight.yaml` with goldens. _[Shipped as `haves_havenots_solar.yaml` — plan T10; annotated 2026-07-12.]_

## Part E — Budget-gated (NOT in this implementation pass; needs user's key + $)

| Item | Est. cost |
|---|---|
| Live clean-cell re-run under new physics+architecture (Haiku, batched) | ~$5-15 |
| Live failure cells × 3 seeds (after Part A) | ~$50-150 |
| Sonnet capability ablation, clean cell | ~$22 batched _[CORRECTED 2026-07-12: no Batch-API support exists in this codebase; realistic sync cost ~$27-35 — see the Phase 3.2 playbook]_ |
| Live explanation judging (~200 samples) | ~$2-5 |
| VT/AZ ResStock + NSRDB fetches (winter/heatwave scenarios) | free, needs NREL_API_KEY + network |

## Out of scope for Phase 3

Web demo (Phase 4), paper writing (Phase 4), repo visibility decision (user),
advisor update email (user go-ahead; `/advisormeeting` ready).
