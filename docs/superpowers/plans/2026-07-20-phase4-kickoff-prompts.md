# Phase 4 kickoff prompts

One fresh Opus session per plan (after `/clear`), in order — Block 1 (paper) then Block 2 (demo). Block 2 is technically independent of Block 1 and may instead run in a parallel worktree session if Leo prefers. Each block is standalone: paste it verbatim, nothing to edit.

Standing next-step handoff: the executing session, as the LAST wrap step, prints the next pending block from this file verbatim inside a copyable code fence, prefaced "To continue, `/clear` and paste this into a fresh session:". "Next pending" = the first plan below whose tasks are not all checked off.

## Block 1 — Phase 4a: paper draft v1

```
/model opus-4.8
/readclaude
Execute docs/superpowers/plans/2026-07-20-phase4a-paper-draft.md task-by-task using superpowers:subagent-driven-development. Read the whole plan first, then the spec it names (docs/superpowers/specs/2026-07-20-phase4-paper-demo-design.md). All tasks are docs-only ($0, no API spend); Tasks 2-3 REQUIRE web search to verify every citation's arXiv ID/DOI/venue-year — no unverified citation enters the References. Gate per task: python -m scripts.figures --check green + ruff check sim tests scripts clean; full gate (+ mypy 37 files + pytest 407) at Tasks 0 and 11. Every number in the paper is COPIED from docs/phase3_results.md / docs/phase3_tables.md / committed summary.json — never computed fresh, never recalled. One commit per task with a CLAUDE.md progress-log row + plan checkbox flip in the same commit; Conventional Commits; no Claude attribution anywhere. Stop condition: all 12 tasks committed, security grep 0, pushed, gh run green, advisor/venue email printed in-session (NOT sent, NOT committed). Then print the Phase 4b kickoff block from docs/superpowers/plans/2026-07-20-phase4-kickoff-prompts.md verbatim in a code fence.
```

## Block 2 — Phase 4b: web demo

```
/model opus-4.8
/readclaude
Execute docs/superpowers/plans/2026-07-20-phase4b-web-demo.md task-by-task using superpowers:subagent-driven-development. Read the whole plan first, then the spec it names (docs/superpowers/specs/2026-07-20-phase4-paper-demo-design.md). Cost $0 (no API calls). Python tasks are strict TDD (red first); any pinned literal in a plan test that comes up red must be re-derived by measuring the committed artifact, never force-fitted (the plan's Pinned-literal rule). JS gate per task: npm run check (0 errors) + npm run build from web/. Python gate: fresh-3.12-venv ruff + mypy + pytest (407 baseline; +9 at Task 1, +5 at Task 3). NEVER copy llm_cache/ or judge_cache/ near web/; payload <= 20 MB total, every file <= 15 MB. Task 9 touches .github/workflows so the clean-install dry-run rule applies. Task 10's Vercel deploy is Leo-gated: STOP and hand off (Leo imports the repo in the Vercel dashboard, sets Root Directory = web, pastes the URL back); never touch the Vercel account or any token. One commit per task with a CLAUDE.md progress-log row + plan checkbox flip in the same commit; Conventional Commits; no Claude attribution anywhere. Stop condition: all 11 tasks committed, security grep 0, pushed, gh run green (both jobs), live URL verified and in README.
```
