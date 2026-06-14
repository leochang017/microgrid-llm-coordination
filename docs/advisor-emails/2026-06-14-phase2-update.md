# Phase 2 Status Update — LLM Agent Layer

**To:** Prof. Yongfeng Zhang
**From:** Leo Chang
**Date:** 2026-06-14
**Subject:** Phase 2 (LLM agent layer) complete — surprise finding + questions for Phase 3

---

Dear Professor Zhang,

I wanted to give you a full update on the Phase 2 work since our last meeting, share a surprise finding I'd like your read on, and lay out my thinking for Phase 3 so you can steer it before I go too deep.

## What shipped in Phase 2

The Phase 1.6 substrate (ownership/management overlay communication graph, the LP upper-bound baseline, the gap-closed reporting) is now driving a real LLM-agent strategy that plugs into the simulator's existing `prepare` / `decide_transfers` interface. The new `sim/agents/` package has eight focused modules:

- **`policy.py`** — a structured Policy YAML schema with a hand-rolled validator. Agents emit one of these; a pure-Python tick executor consumes it. No LLM at act-time.
- **`memory.py`** — Park-adapted append-only memory stream with top-K retrieval (α·recency + β·importance + γ·similarity).
- **`reflection.py`** — Park-adapted reflection LLM call that distills recent memories into 1–3 belief statements (e.g. "peer r2c3 has refused 4/4 of my requests").
- **`protocol.py`** — speech-act `Message` schema (REQUEST / OFFER / ACCEPT / REJECT / COUNTER / INFORM) with a 1–3 sentence NL `rationale` field on every message; `MessageBus` with one-tick latency, routing through `Neighborhood.union_neighbors` (the Phase 1.6 overlay graph), per-edge dropout, per-tick send budget.
- **`failure_modes.py`** — the three locked failure modes from our 2026-05-26 meeting: `defector_fraction` (strategic agents), `obs_noise` (Gaussian on SoC / load / solar forecast), `comm.{drop_prob_by_circle, per_tick_budget}` (comm constraints). All deterministic given `scenario.seed`.
- **`cache.py`** — content-addressed prompt cache (sha256 over canonical-json of model+system+user+temp). Two-tier lookup: run-local then `reference_runs/` (the in-repo reproducibility artifact). Replays are byte-identical and cost $0.
- **`llm.py`** — provider-neutral `LLMClient` abstract base + `MockLLMClient` (for tests) + `AnthropicLLMClient` (Claude API; supports both API-key and OAuth-token auth).
- **`agent.py`** — `LLMAgent` with the full lifecycle: observe → memory append → reflect+plan (one LLM call when `should_replan` fires) → react to inbound REQUEST/OFFER (LLM call per message, capped at 3/tick) → act (pure Python; turns the current Policy into Transfers + outbound messages).

A thin `sim/strategies/llm_agent.py` facade is the only place that imports both the agent layer and the engine plug-point. Non-LLM strategies (no_coord / round_robin / round_robin_overlay / lp_optimal) are byte-identically unchanged.

## Three orthogonal failure-mode injection axes (per your 2026-05-26 mandate)

Each is an independently configurable scenario knob; five "cells" are available: `clean`, `defectors_only`, `noise_only`, `comm_only`, `all_combined`.

- **Strategic/selfish agents** (`defector_fraction` + `defector_realization: prompt | wrapper | both`). After the Phase 2 first pass I had only the `wrapper` realization wired (mutates outbound message payloads at the bus). Last night I added the `prompt` realization too: defector agents now get a "you are selfish; cooperation optional; you may misreport state" system prompt for plan + react calls. I also track an `n_react_refusals` counter — how often the LLM refuses to follow the adversarial instruction. I think the refusal rate itself is paper-relevant.
- **Noisy/faulty observations** (`obs_noise.soc_std_frac` / `load_std_frac` / solar forecast). Gaussian, deterministic per `(seed, channel, house_id, tick)`. Applied to the agent's *view* of its own state — physics still uses the true state.
- **Communication constraints**. Per-circle dropout (so we can model "owner edges are reliable, geographic edges are flaky") and per-tick send budget. Reflection is supposed to learn the dropout pattern over time.

## Determinism, caching, reproducibility

Two cache-warm runs of the same scenario YAML produce byte-identical `state.jsonl` / `events.jsonl` / `messages.jsonl`. I have a test (`tests/test_llm_agent_replay.py`) that locks this down. The reproducibility artifact for the paper is the `reference_runs/` directory in the repo — every LLM call's prompt + response is cached there as `<sha256>.json`. A reviewer can clone the repo and re-run any reference scenario with zero API spend.

## The surprise finding

I ran one live Claude Haiku 4.5 reference run on the `haves_havenots__llm.yaml` showcase scenario (12-hour outage, 30 households, bimodal "haves" with 35–40 kWh batteries vs "have-nots" with 2–4 kWh, your Phase 1.6 stress regime).

**Result: served-load fraction 0.460.** Round-robin baseline: 0.525. LP ceiling: 0.529.

LLM coordination *underperformed* round-robin by 6.5 points. In the gap-closed framing you wanted (`(served − rr) / (lp − rr)`), that's a *negative* 1500%.

I think this is actually useful. After staring at it I have a few hypotheses about why:

1. **Generic prompts.** The plan prompt tells Haiku its trust circles and recent memories, but doesn't surface the physics: round-trip battery losses, the fact that have-nots can't absorb large transfers, the obvious have/have-not asymmetry. A scenario-aware prompt might close this.
2. **Haiku writes conservative policies.** Empirically it tends to set `share_min_soc_frac` high (≈ 0.7), opposite of what helps in a long outage. Round-robin shares aggressively at the moment you're above average.
3. **The agent's `act()` didn't filter by recipient need.** This was a real architectural bug. Round-robin's secret sauce: it sends only to peers with *below-mean SoC*. My v0 `act()` distributed energy to all `union_neighbors` weighted by trust-circle priority — so haves were sending energy to other haves through owner edges, where it was wasted in round-trip losses.

## Phase 2.5 — last-night cleanup pass

After noticing #3 I did a small cleanup pass and re-ran the live Haiku:

- **`act()` now filters recipients by below-mean SoC** of visible peers (round-robin's filter, applied to the trust-circle-aware candidate set). This is a one-axis architectural fix that doesn't require new experiments to justify.
- **`defector_realization: prompt` is now wired through** (it was deferred to a follow-up in the Phase 2 wrap-up). This addresses your locked failure-mode mandate properly — the strategic agent's *LLM* is now briefed to be selfish, not just its message channel.
- **Refactored `LLMAgent`** into a clean class (the v0 had module-level functions monkey-patched onto the class — embarrassing).
- **LLM call counters wired into `summary.json`** — `n_plan_calls`, `n_react_calls`, `n_react_skipped`, `n_plan_parse_failures`, `n_plan_fallbacks`, `n_react_refusals`, plus cache hit/miss counts. Important for Phase 3 cost accounting.
- **Cleaner test injection** via a `llm_client_factory` parameter on `prepare()` instead of monkey-patching the module.

**Updated number from the Phase 2.5 re-run:** served-load fraction **0.458** (essentially unchanged from 0.460). Transfer count dropped from 206 to 44 — the below-mean-SoC filter is correctly suppressing wasted haves-to-haves shares — but the served-load didn't move. Wasted_kwh dropped a tiny amount (9.0 → 8.9).

The Phase 2.5 LLM-call instrumentation surfaced what I think is the actually-interesting bottleneck: **Haiku's policy YAML output fails to parse 41% of the time** (101 parse failures out of 246 plan calls). When three parse failures fire in a row for one agent, my code falls back to a hard-coded round-robin-style policy and stops calling the LLM until the next trigger. So a lot of the run was effectively executing the fallback policy, not the LLM's actual reasoning. The fix is either a more lenient parser (risky — invalid policies could enter the loop) or a more structured output mechanism (tool-use with a JSON schema, instead of asking for a YAML code-fence). I'll investigate this in Phase 3 — Anthropic's tool-use mode should give us schema-validated structured output and bring the parse rate to ~100%. I think this single change might close most of the remaining gap to round-robin, before we even start talking about prompt engineering.

A second suspect: my LLM `act()` shares 20% of headroom per tick, vs round-robin's 5%. So when LLM IS sharing, it's sharing 4× as much, which over-fills small batteries and wastes energy on round-trip losses. Tuning that parameter to 0.05 is another candidate fix.

## Questions I'd like your read on

1. **The negative-gap result.** Is "live Haiku underperformed round-robin on the clean cell" a fine framing for the paper, with the failure-mode cells as the place we expect NL coordination to pull ahead — or should we tune the prompt + re-run before reporting any number? I lean toward the former (the finding is informative either way), but I want your view on what's honest.
2. **Prompt engineering scope.** How much prompt tuning is "fair" before we report? If I rewrite the plan prompt to surface physics (battery RT losses, peer-state asymmetry) and Haiku then matches round-robin, is that prompt-engineering-as-a-finding or am I p-hacking the architecture into looking better?
3. **The reflection step's actual value.** Park's reflection is supposed to enable "peer X has been refusing me; route around them" reasoning. In my clean-cell run, reflection fired (≈ 1×/hour/agent) but I don't have a measurement of how much it helped. Should Phase 3 include a no-reflection ablation as a first-class condition?
4. **Strategic agent prompt refusal.** When I tell Haiku "you may misreport state," some fraction of the time it likely refuses (saying something like "I cannot misrepresent information"). That refusal *itself* is a finding — the LLM has built-in honesty. Do you have a view on whether we report that as a robustness result ("LLM defectors are partially neutralized by their own training") or as a methodology limitation?
5. **Welfare metric.** You confirmed served-load fraction is fine for Phase 2 and needs-weighted welfare is Phase 3. Before I start that work, do you have a specific needs-weighting in mind (medical loads = ∞, AC = low; or something quantified differently)? I want to avoid having to redo the metric mid-Phase-3.

## Phase 3 plan I'd like to validate with you

Roughly six weeks of work as I'm thinking about it:

| Weeks | What | Why |
|---|---|---|
| 9 | **Bring the deferred failure-cell live runs alive** — `__defectors` / `__noise` / `__comm` / `__all`. One cell at a time; small, iterate prompts; freeze the prompt and run all seeds. | The clean cell is where rule-based protocols are at their best. The interesting question is whether LLM pulls ahead under adversity. |
| 10 | **Implement the deferred items**: peer-state-via-INFORM-only (currently the agent sees engine ground truth — partial-observability is more honest). Make the `defector_realization: prompt` measurement rigorous. | Compliance with your 2026-05-26 mandate; partial observability is the realistic threat model. |
| 11 | **Needs-weighted welfare + explainability rubric**. The rubric is probably an LLM-judge that scores each agent rationale on (a) coherence, (b) state-faithfulness, (c) lay-person interpretability. | The (c) axis of the research question proper. |
| 12 | **Full sweep**: scenarios × strategies × seeds × failure cells × model sizes (Haiku / Sonnet / Opus / maybe Llama 3.1 70B for an OS-model row). Run overnight; cache makes replays free. | The headline figure of the paper: gap-closed vs failure-mode intensity, one line per model size. |
| 13 | **Figures**. The main plot I want is gap-closed (y) vs each failure mode's intensity (x), with model size as the family of curves. If LLM pulls ahead at higher intensities, you get the "robustness is the LLM's superpower" story. | Workshop-paper bread and butter. |
| 14 | **Writeup**. Draft of the experiments section + tighten the framing per your 2026-05-26 cautions (don't oversell adversarial robustness as security; read Sovacool before the fairness section). | Submission prep. |

Cost back-of-envelope for the full sweep: roughly 6 cells × 4 strategies × 3 model sizes × 5 seeds × ~$15 each at Haiku-like rates = ~$5000 worst case. That's prohibitive. Realistically I'd shrink the seed count to 3 and use Haiku for the bulk + Sonnet for headline rows only, which brings it under $1500. I'd appreciate your view on whether the budget is realistic — and whether you have lab credits, or I should look at a research-credit program.

## What I'd like from you

- A reaction to the negative-gap finding (question 1) and the framing — that more than anything determines what the paper's main story is.
- Greenlight (or steer) the Phase 3 plan, especially the failure-cell-first ordering and the model-size-as-experimental-axis idea.
- Your read on questions 2–5.
- Any thoughts on venues. Phase 1.6 update mentioned Climate Change AI workshop @ NeurIPS, multi-agent LLM workshops, AAMAS COIN, AAAI Student Abstracts. I lean Climate Change AI given the (a) robustness, (c) explainability emphasis — but I'd rather pick the right one before writing.

The full repo is at https://github.com/leochang017/microgrid-llm-coordination — `phase2-complete` tag is the v0 architecture, `phase2.5-complete` (about to be tagged) is the cleanup pass with the live re-run.

Happy to walk through any of this in person. I have time later this week.

Thanks for the steering on Phase 1.6 — the LP ceiling and overlay graph are exactly what made Phase 2's results interpretable (otherwise we'd be staring at numbers without context).

Best,
Leo
