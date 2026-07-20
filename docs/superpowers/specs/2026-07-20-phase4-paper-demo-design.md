# Phase 4 — Paper & web demo (design)

**Date:** 2026-07-20 · **Owner:** Leo · **Gate:** `phase3.3-complete` (met; all Phase 3.2 playbook stages done) · **Scope authority:** `docs/superpowers/specs/2026-07-12-remaining-phases-roadmap.md` §Phase 4 (strategy locked there; this spec turns it into an implementable design).

## Goal

Produce (a) **paper draft v1** — a venue-agnostic Markdown draft under `docs/paper/` telling the Phase 3 empirical story with every number traced to a committed artifact, ready for advisor review and the venue decision (CHI / ICLR / WWW, main-or-workshop); and (b) the **public web demo** — a SvelteKit static site on Vercel that replays the committed live cells (tick-scrubber SoC grid, message flow, per-house rationales with judge scores). Total cost: **$0 API spend** (the paper copies committed numbers; the demo is a viewer of committed artifacts — no live LLM calls, no keys, no backend).

## What we have (the ground truth this phase reads)

- `docs/phase3_results.md` (§1–§7) — the complete empirical story: clean headline +5.8 ± 1.0 pts vs the zero-LLM control over 3 seeds (29.0% ± 2.9 of the control→LP gap closed); failure axes (defectors +2.3 / 89.1% retained at 33.6% dose; noise +0.87; comm −0.86 post-bugfix); fairness non-tradeoff; negotiation instrumentation; explanation quality (Sonnet judge); Sonnet capability-ablation tie; 11-item limitations list.
- `docs/phase3_tables.md` (3 generated tables) + `docs/figures/` (4 PNGs), regenerated deterministically by `python -m scripts.figures --all`; `--check` asserts every committed cell equals its golden pin (`EXPECTED_LIVE`).
- Methods sources: archived specs `2026-05-14-phase1-simulator-design.md`, `2026-06-13-phase2-llm-agent-design.md`, `2026-07-07-phase3-benchmark-design.md`, `2026-07-16-phase3.3-analysis-design.md`; judge rubric in `scripts/eval_explanations.py`.
- Demo substrate: 8 committed live cells under `reference_runs/<scenario>/llm_agent/<cell>/` — per cell `state.jsonl` (~800 KB, 30 houses × 96 ticks), `events.jsonl` (~400 KB), `messages.jsonl` (6–9.5 MB, INFORM ≈ 50% of rows, `templated:false` rows carry genuine LLM rationales), `summary.json`, `config.json`, and (clean@23 + defectors@7 only) `explanations_eval*.json` with judge scores. `llm_cache`/`judge_cache` (~22 MB+/cell) never ship. House positions parse from `r{r}c{c}` ids; trust-circle membership lives only in the scenario YAML `affiliations:` block; have/havenot + pv/battery + realized defectors must be re-derived (`sim/engine.py::sample_households`, `sim/agents/failure_modes.py::assign_defectors`). Baselines are gitignored — regenerated + baked at export time via `scripts/figures.py` (`regen_baselines`, `collect_cell`, `cell_served_gap_closed`).
- No paper/LaTeX infrastructure and no JS tooling exist anywhere in the repo — both halves are greenfield.

## Deliverables

1. **`docs/paper/paper.md`** — draft v1 (~5,300 words ≈ 6 pages two-column equivalent): problem + gap, simulator + LP-ceiling method, agent architecture + information-flow rework, results (reusing the 4 committed figures as-is), honest-negative subsection, failure-cell story, explanation evaluation, limitations, references with `[AuthorYear]` keys. Plus **`docs/paper/claims_audit.md`** — claim→artifact traceability table.
2. **`scripts/export_demo_data.py`** (mypy-strict, TDD) — per-cell compact JSON export (`meta` / `ticks` / `messages` / `explanations`) into `web/static/data/`, committed (~12.3 MB total; Vercel never needs Python), with **`tests/test_demo_data_pins.py`** asserting exported live numbers equal `EXPECTED_LIVE` exactly — the demo can never drift from the paper.
3. **`web/`** — SvelteKit static app (adapter-static, TypeScript, plain CSS, no component libs): `/` overview with per-cell baseline comparison bars + fairness chips; `/run/[cell]` replay — SoC neighborhood grid (viridis), tick scrubber with day/night strip, transfer arrows, trust-circle overlay, message panel with drop reasons, per-house "why" panel with rationales + judge scores.
4. **CI `web` job** (npm ci + svelte-check + build) alongside the untouched Python job.
5. **Vercel deploy** — Git integration rooted at `web/`, Leo-gated (executor never touches the Vercel account or any token); demo URL lands in README.
6. **Advisor/venue email draft** (via `/advisormeeting`) — printed + scratchpad, never committed or sent.

Execution: two plans, one session each — `docs/superpowers/plans/2026-07-20-phase4a-paper-draft.md` (12 tasks) then `2026-07-20-phase4b-web-demo.md` (11 tasks); 4b is independent and may run in a parallel worktree session. Kickoff blocks: `docs/superpowers/plans/2026-07-20-phase4-kickoff-prompts.md`.

## Out of scope / blocked / deferred

- **LaTeX/venue conversion + submission mechanics + camera-ready** — blocked on the advisor's venue decision; the `paper-v1` tag lands at submission, not at draft v1.
- **VT/AZ cross-climate cells** — dropped from Phase 4 (Leo, 2026-07-20); the single-dataset-family caveat stays in Limitations.
- **Demo:** no live runs, no scenario editing, no API keys anywhere near the browser (roadmap-locked); Sonnet ablation cell page, rubric-variant judge tables, and per-message judge joins (needs a paid re-judge with per-message ids — Leo-gated) all deferred and tracked in Plan B.
- **New experiments, prompt iterations, settlement-feedback loop-closing** — all reopen earlier phases; not Phase 4.

## Design decisions

- **Markdown-first paper** (Leo, 2026-07-20): venue-agnostic, advisor-reviewable on GitHub, converts once the venue is chosen. Single `paper.md` (not per-section files) — one file for advisor top-to-bottom review and one-shot pandoc conversion; abstract/intro written last so the claims checklist is enforceable against finished text.
- **Number rule:** every number in the paper is COPIED from `phase3_results.md` / `phase3_tables.md` / committed `summary.json` — never computed fresh, never recalled. **Citation rule:** nothing enters References without arXiv ID/DOI/venue-year verified by web search in-session. No regex-pin test on prose (would cry wolf on rewording); a mechanical numeral-by-numeral audit task is the backstop.
- **Figures reused as-is** — fresh matplotlib re-renders are byte-different from the committed PNGs; re-rendering risks pin confusion for $0 gain. Vector re-renders are a venue-conversion problem.
- **Advisor constraints are task-level verify gates**, not prose guidance: Sovacool read before fairness prose (with tenet provenance correctly attributed); `grep -icE 'byzantine|adversar|attack|threat'` → 0; deployment disclaimer unhedged in Limitations; Gini never alone; Park et al. cited by name in §4.1's first sentence; headline claimed vs the CONTROL, never round_robin.
- **SvelteKit static** (Leo, 2026-07-20): four-cell story only (clean@23, defectors@7, noise@23, comm@23) — clean seeds 1/7 ship as a spread field, Sonnet cell excluded (capability data point, not a failure axis — same reasoning that keeps it out of `LIVE_CELLS`). Exported JSON committed and pin-tested. Message downsampling: keep a row iff `performative != "INFORM" or templated == false`; per-tick INFORM sent/delivered/dropped aggregates preserved (that aggregate IS the comm-cell story). Judge scores join at tick level with an honesty note (per-message pairing is ambiguous in the committed evals). JS TDD waived — the risky transform is TDD'd in Python; the Svelte layer gates on svelte-check + build.
- **Determinism/reproducibility carried into the demo:** the export runs `collect_cell` (which regenerates baselines under the C6-3 frozen-config drift guard) and asserts the state.jsonl-derived served fraction equals the committed summary before writing.

## Exit

- `docs/paper/paper.md` draft v1 committed, number-audited (claims_audit.md complete), advisor/venue email drafted.
- Demo live on Vercel, URL in README; exported data pin-tested green; both CI jobs green.
- CLAUDE.md/README status synced. **`paper-v1` tag explicitly deferred to submission** (with the advisor, post venue decision).
