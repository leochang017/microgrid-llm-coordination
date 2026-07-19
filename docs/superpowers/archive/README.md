# Archive — completed-phase specs, plans, and one-off docs

These are the spec + implementation-plan pairs (and two one-off documents) for
phases that finished before 2026-07-19's repo-cleanup pass. They are kept for
historical reference and traceability, not as active pointers — nothing here
should be edited going forward. The live spec/plan pointers (Phase 4 and the
roadmap) remain at `docs/superpowers/specs/` / `docs/superpowers/plans/`.

## Specs (`archive/specs/`)

- `2026-05-14-phase1-simulator-design.md` — Phase 1, deterministic microgrid simulator. Tag: `phase1-complete`.
- `2026-05-29-phase1.6-hardening-design.md` — Phase 1.6, pre-Phase-2 hardening (comm-graph overlays, stress scenarios, LP baseline). Tag: `phase1.6-complete`.
- `2026-06-13-phase2-llm-agent-design.md` — Phase 2, per-household LLM agent + natural-language P2P messaging. Tag: `phase2-complete`.
- `2026-07-06-phase2.9-correctness-hardening.md` — Phase 2.9, correctness hardening (energy conservation, solar timezone, LP slack/bounds, seed sweeps). Tag: `phase2.9-complete`.
- `2026-07-07-phase3-benchmark-design.md` — Phase 3, benchmark & experiments infrastructure design. Tag: `phase3-infra-complete`.
- `2026-07-12-phase3.1-prelive-hardening.md` — Phase 3.1, pre-live hardening (55-finding review fixes gating live spend). Tag: `phase3.1-complete`.
- `2026-07-16-phase3.3-analysis-design.md` — Phase 3.3, analysis & results (figures, tables, results outline). Tag: `phase3.3-complete`.

## Plans (`archive/plans/`)

- `2026-05-14-phase1-simulator.md` — Phase 1 implementation plan (26 tasks, TDD). Tag: `phase1-complete`.
- `2026-05-29-phase1.6-hardening.md` — Phase 1.6 implementation plan. Tag: `phase1.6-complete`.
- `2026-06-13-phase2-llm-agent.md` — Phase 2 implementation plan (26 tasks, TDD). Tag: `phase2-complete`.
- `2026-07-06-phase2.9-correctness-hardening.md` — Phase 2.9 implementation plan (18 tasks, TDD). Tag: `phase2.9-complete`.
- `2026-07-07-phase3-benchmark.md` — Phase 3 infrastructure implementation plan (11 tasks, TDD). Tag: `phase3-infra-complete`.
- `2026-07-12-phase3.1-prelive-hardening.md` — Phase 3.1 implementation plan (23 tasks, TDD). Tag: `phase3.1-complete`.
- `2026-07-12-phase3.2-live-runs.md` — Phase 3.2 live-run playbook (Stages 1-5, budget-gated). Tag: `phase3.2-live-complete`.
- `2026-07-16-phase3.3-analysis.md` — Phase 3.3 implementation plan (7 tasks, $0 analysis/figures). Tag: `phase3.3-complete`.

## One-offs (`archive/`)

- `2026-07-15-opus-phase3.2-execution-prompt.md` — a one-time execution prompt written to hand off Phase 3.2 live-run execution to a fresh Opus session. No completion tag (a working aid, not a phase deliverable); superseded once Phase 3.2 finished.
- `phase1_real_data_result.png` — the Phase 1 real-ResStock-data result figure, referenced only from the archived Phase 2.9 plan. No completion tag; superseded by the Phase 3.3 figures (`docs/figures/phase3_*.png`).

Everything here is a completed phase's record; the authoritative summary lives in CLAUDE.md's phase table and `docs/progress_log_archive.md`.
