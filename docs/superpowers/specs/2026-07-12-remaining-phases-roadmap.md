# Remaining Phases Roadmap (Phase 3.1 → Paper)

**Date:** 2026-07-12 · **Owner:** Leo · **Standing rule:** each phase still gets its own spec + TDD plan in `docs/superpowers/` before execution (this roadmap is the strategy layer, not a task list). The advisor's locked decisions (CLAUDE.md: Phase 1/1.6/2 sections + Important warnings) remain binding throughout — nothing below re-litigates them.

## The through-line (unchanged from the advisor's framing)

Research question: fair / robust / explainable LLM-agent energy coordination. Contribution axis: CS/ML, not power systems. All results framed as **gap-closed between round_robin and the LP ceiling**, with the zero-LLM control (`llm_fallback`) as the mandatory bar — the Phase 2 lesson ("the tuned executor, not the LLM, carries clean-cell performance") is reported honestly as a finding, not buried. The LLM's case, if it exists, is made in the **failure cells** (defectors / noise / comm — the advisor's three axes) and on **explanation quality**, not on clean-cell throughput.

## Phase sequence

| Phase | Doc | Gate to enter | Output |
|---|---|---|---|
| 3.1 Pre-live hardening | plans/2026-07-12-phase3.1-prelive-hardening.md (23 tasks, ready) | none — start now | tag `phase3.1-complete`; every review finding fixed |
| 3.2 Live runs | plans/2026-07-12-phase3.2-live-runs.md (playbook, ready) | 3.1 tag + advisor email + budget gates | live cells in `reference_runs/`, costs logged, tag `phase3.2-live-complete` |
| 3.3 Analysis & results | spec+plan to write at 3.2 wrap | 3.2 tag | figures + results tables + the paper's empirical story |
| 4 Paper & demo | spec+plan to write after 3.3 | 3.3 done + venue decision | submitted workshop paper + public demo |

## Phase 3.3 — Analysis & results (spec to be written; scope locked here)

**In scope:**
- **Headline figure:** paired multi-seed bars per cell — no_coord / control / round_robin / live-Haiku / LP, with gap-closed annotations. Seeds {23, 1, 7}; spreads are the error bars (single-seed deltas of a point or two are noise — established 2026-07-07).
- **Failure-axis story:** live-vs-control delta per axis vs the mock floor (`docs/phase3_mock_sweep.md` regenerated in 3.1). The paper's central claim template: "under degraded information, LLM negotiation recovers X points of served load and Y points of fairness that fixed policies lose."
- **Fairness panel:** Gini (never alone — advisor), `min_house_served_fraction` (Rawlsian floor), Jain, `served_critical_load_fraction`. Read Sovacool BEFORE writing this section (advisor warning, standing).
- **Explanation quality table:** rubric means (state_accuracy / actionability / consistency) with the Sonnet judge, plus templated-vs-authored provenance counts, plus ~10 hand-audited examples in an appendix.
- **Negotiation instrumentation:** commitments made/expired, defaulted amounts, react-starvation counters — the "what actually happened in negotiation" table (now that 3.1 wires them into summary.json).
- **VT/AZ winter/heatwave scenarios** (free data; NREL_API_KEY): fetch, build `winter_morning_lowsolar.yaml` + `heatwave_ac.yaml` per the Phase 1.6 deferred commands, run the $0 strategies + LP; include live cells ONLY if budget remains and the advisor wants cross-climate robustness in v1.
- **Analysis tooling stays in-repo and deterministic:** extend `scripts/compare.py` / a new `scripts/figures.py` (matplotlib, seeded, no notebook state) so every figure regenerates from committed artifacts with one command.

**Out of scope:** new mechanisms, new metrics beyond the shipped set, prompt-engineering iterations (that's a decision for the advisor after seeing live cells — it reopens 3.2, not 3.3).

**Exit:** results section outline with real numbers in it; advisor walkthrough scheduled; decision recorded: which venue, which claims survive.

## Phase 4 — Paper & web demo (spec to be written; strategy locked here)

**Paper (leads, demo follows):**
- Venue per advisor 2026-05-26: Climate Change AI @ NeurIPS workshop, multi-agent LLM workshops, AAMAS COIN, or AAAI Student Abstracts. Decision at 3.3 exit with the advisor; deadlines drive the writing calendar.
- Structure follows the phases: problem + gap (fairness/robustness/explainability), simulator + LP ceiling method, information-flow architecture (INFORM-only beliefs, binding negotiation), results (3.3 figures), honest-negative clean-cell finding, failure-cell story, explanation evaluation, limitations (single dataset family unless VT/AZ landed; LLM-judge caveat; no real deployment claim — advisor warning stands verbatim).
- Cite Park et al. (arXiv:2304.03442) prominently for the memory/reflection lineage (locked 2026-05-26); cite Sovacool for energy justice framing; do NOT oversell the defector work as a security contribution (advisor warning).
- Reproducibility box: public repo (Leo's 2026-07-12 decision), tags per phase, `reference_runs/` caches make every live figure replayable at $0.

**Web demo (Phase 4's second half, after paper draft v1):**
- Recommended architecture (decide at spec time, brainstorm first per house rules): **SvelteKit static site on Vercel reading precomputed run JSON** from `reference_runs/` — no backend, no live LLM calls, no keys in the browser. Tick-scrubber over the neighborhood grid (SoC heatmap), message-flow overlay (who asked/promised/delivered), per-house "why" panel showing the actual logged rationales with their judge scores. Everything the demo shows must be a committed artifact — the demo is a viewer, not a simulator.
- Explicitly NOT: user-triggered live runs, editable scenarios, anything requiring the API key server-side. (Cost, safety, and the advisor's no-deployment-claims warning all point the same way.)

**Exit:** submitted paper; demo URL in the README; repo tagged `paper-v1`.

## Standing constraints carried forward (do not drop)

1. Simplicity above all; serial TDD; progress-log row per task, same commit; conventional commits; no Claude attribution.
2. Security checks: no secrets in the public repo, `/security-review` at each phase tag (added 2026-07-12).
3. Determinism everywhere: same seed = byte-identical; anything nondeterministic (LLM live calls) is cached and replayable.
4. Budget is Leo's: every live-spend stage is gated in the playbook; nothing autonomous spends money.
5. Advisor sign-off items tracked in the 3.2 playbook preflight — they gate failure cells and judging, not infrastructure work.
