# Maintenance plan batches

Executor-ready plans produced by `/planbatch` (distinct from the per-phase specs/plans under `docs/superpowers/`). One plan = one execution session; run in the listed order; check boxes / task logs live inside each plan.

## 2026-07-18 batch — audit + cleanup (brief: `docs/notes/2026-07-18-audit-cleanup-brief.md`)

| # | Plan | Covers | Status |
|---|------|--------|--------|
| 1 | [2026-07-18-phase3-accuracy-plan.md](2026-07-18-phase3-accuracy-plan.md) | Phase-3 accuracy completion: Sonnet-cell wiring, doc staleness, C1/C2 negotiation-bug fixes + authorized comm-cell re-run (~$4–7), defector provenance | pending |
| 2 | [2026-07-18-test-accuracy-hardening-plan.md](2026-07-18-test-accuracy-hardening-plan.md) | Test-suite accuracy: order-dependence, TZ leak, LLM-client error paths, reference-resume e2e, mypy → scripts/, exact e2e pins | pending |
| 3 | [2026-07-18-repo-cleanup-claudemd-plan.md](2026-07-18-repo-cleanup-claudemd-plan.md) | Archive completed-phase planning files, remove dead code, condense CLAUDE.md (~101 KB → ~30 KB), README refresh | pending |
| 4 | [2026-07-18-full-repo-review-plan.md](2026-07-18-full-repo-review-plan.md) | Full fresh adversarial review of sim/ + scripts/ + tests/ + configs, verify → triage → TDD fixes → review record | pending |

Flip a row to **done** in the executing session's wrap task.
