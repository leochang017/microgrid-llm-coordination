# Maintenance plan batches

Executor-ready plans produced by `/planbatch` (distinct from the per-phase specs/plans under `docs/superpowers/`). One plan = one execution session; run in the listed order; check boxes / task logs live inside each plan.

## 2026-07-18 batch — audit + cleanup (brief: `docs/notes/2026-07-18-audit-cleanup-brief.md`)

| # | Plan | Covers | Status |
|---|------|--------|--------|
| 1 | [2026-07-18-phase3-accuracy-plan.md](2026-07-18-phase3-accuracy-plan.md) | Phase-3 accuracy completion: Sonnet-cell wiring, doc staleness, C1/C2 negotiation-bug fixes + authorized comm-cell re-run (~$4–7), defector provenance | **done** (2026-07-19, `5c576ba5`; comm 0.4565→0.4941, spend $3.96) |
| 2 | [2026-07-18-test-accuracy-hardening-plan.md](2026-07-18-test-accuracy-hardening-plan.md) | Test-suite accuracy: order-dependence, TZ leak, LLM-client error paths, reference-resume e2e, mypy → scripts/, exact e2e pins | **done** (2026-07-19; 8/8 tasks, 362→367 tests, mypy now covers sim/ + scripts/, zero sim/ runtime change) |
| 3 | [2026-07-18-repo-cleanup-claudemd-plan.md](2026-07-18-repo-cleanup-claudemd-plan.md) | Archive completed-phase planning files, remove dead code, condense CLAUDE.md (132 KB → 89 KB; ≤35 KB gate waived by Leo, recent detail kept), README refresh | **done** (2026-07-19; 6/6 tasks, 367→364 tests, 17 files archived, 4 dead funcs + plotter removed) |
| 4 | [2026-07-18-full-repo-review-plan.md](2026-07-18-full-repo-review-plan.md) | Full fresh adversarial review of sim/ + scripts/ + tests/ + configs, verify → triage → TDD fixes → review record | **done** (2026-07-19; 8 reviewers + 8 skeptics, 29 findings + ENV-1, 20 fixed across 5 batches, 364→407 tests; record: `docs/superpowers/archive/2026-07-18-full-repo-review.md`) |

## 2026-07-20 batch — OSS polish (post-review)

| # | Plan | Covers | Status |
|---|------|--------|--------|
| 1 | [2026-07-20-oss-polish-plan.md](2026-07-20-oss-polish-plan.md) | README staleness (test count 364→407, CI badge, scripts listing, reference_runs note), pyproject OSS metadata, docs-only honesty caveats (commitment emission-vs-settlement I-1, SENDER_DOD_FLOOR misnomer, adapter boundary note, LP-Gini vertex caveat). Docs + metadata only — zero logic/cache-key changes. Includes the 2026-07-20 3-reviewer review record (security: clean; accuracy: no published number wrong). | **done** (2026-07-20; 13/13 boxes, 407 tests unchanged, `docs/phase3_tables.md` the only generated diff) |

Flip a row to **done** in the executing session's wrap task.

**Kickoff prompts** for all four plans live in [2026-07-18-kickoff-prompts.md](2026-07-18-kickoff-prompts.md) — after `/clear`, tell Claude to read that file and run the next pending kickoff.
