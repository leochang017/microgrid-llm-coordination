# Kickoff prompts — 2026-07-18 audit + cleanup batch

How to use: after `/clear`, open a fresh session and paste ONE block below (in order — 1 → 2 → 3 → 4, next one only after the previous session's work is merged and pushed). Or just tell Claude: *"read docs/plans/2026-07-18-kickoff-prompts.md and run the next pending kickoff"* — it should check `docs/plans/README.md` for which plans are already marked done, then execute the first pending one exactly as its block says.

Progress tracking: the executing session flips the matching row in `docs/plans/README.md` from **pending** to **done** in its wrap task.

**Next-step handoff (standing instruction for every executing session):** as the very last thing in your wrap — after the row is flipped, the branch is pushed, and CI is green — end your closing summary by printing the **next pending** kickoff block from this file verbatim, inside a copyable ``` code fence, prefaced with "To continue, `/clear` and paste this into a fresh session:". Determine "next pending" by reading the status column in `docs/plans/README.md` (the first row still marked pending after yours). If yours was the last plan (#4) — or no pending rows remain — say instead that the 2026-07-18 batch is complete and there is nothing left to run.

---

## 1 — Phase-3 accuracy (bug fixes + comm re-run; money-gated, cap $8)

```
/model opus-4.8
/readclaude
Execute docs/plans/2026-07-18-phase3-accuracy-plan.md task-by-task using superpowers:subagent-driven-development. Read the whole plan first — its Decisions and "Edge flags" sections are locked; do not re-litigate or simplify the C1 register-then-retract design. Gate per task: pytest + ruff check sim tests scripts + mypy green, frozen tests untouched (any red in test_agent.py commitment tests or golden pins = implementation drift — stop and re-check, never update those pins). Task 8 spends real money: authorization is recorded in the plan header (comm@23 re-run only, hard cap $8); if interrupted, an identical-command relaunch replays cached calls at $0, but any NEW spend beyond the cap or a different cell requires asking Leo first. Stop condition: all 8 tasks committed with progress-log rows, security grep 0, pushed, gh run green — then end the session with a summary of the new comm number vs the pre-fix 0.4565 and the control 0.5027.
```

## 2 — Test-suite accuracy hardening

```
/model opus-4.8
/readclaude
Execute docs/plans/2026-07-18-test-accuracy-hardening-plan.md task-by-task using superpowers:subagent-driven-development. Read the whole plan first. This plan must change ZERO sim/ runtime behavior — Task 5's mypy fixes are annotation-only; if a fix would alter behavior, stop and report. Gate per task: pytest + ruff check sim tests scripts + mypy green; Task 5 touches pyproject.toml so run the clean-install dry-run (fresh venv, pip install -e ".[dev,data]", full suite) before that commit. Derive Task 6's exact pins from real runs (run twice to confirm stability), never invent them. Stop condition: all 8 tasks committed with progress-log rows, docs state the true test count and mypy scope, pushed, gh run green — then end the session with a summary.
```

## 3 — Repo cleanup + CLAUDE.md condensation

```
/model opus-4.8
/readclaude
Execute docs/plans/2026-07-18-repo-cleanup-claudemd-plan.md task-by-task using superpowers:subagent-driven-development. Read the whole plan first — the KEEP list (pecan adapter, docs-only YAMLs, pyarrow, mock-sweep doc) is explicit; touch nothing on it. Use git mv for every move; zero dangling references after each move (grep gate is in the plan). Gate per task: pytest + ruff check sim tests scripts + mypy green; at wrap, python -m scripts.figures --check and --all must leave git status clean (byte-identical figures prove no number moved). CLAUDE.md condensation: preserve the listed sections verbatim, archive progress rows ≤ 2026-07-12, size gate ≤ 35 KB. Stop condition: all 6 tasks committed with progress-log rows, public-repo hygiene pass done (full-tree key grep 0), pushed, gh run green — then end the session with a summary.
```

## 4 — Full-repo adversarial review (run LAST)

```
/model opus-4.8
/readclaude
Execute docs/plans/2026-07-18-full-repo-review-plan.md task-by-task using superpowers:subagent-driven-development. Read the whole plan first. Reviewer subagents are read-only; every CRITICAL/HIGH/MED finding goes through an independent skeptic verification pass before triage (both prior reviews refuted ~1/3 of raw findings — do not skip it). Triage rule: fix only what changes no published-run physics; anything that would alter what the committed reference_runs artifacts mean goes on the ESCALATE list for Leo with a cost estimate — never silently fixed. Gate per fix-batch: failing test first, then pytest + ruff check sim tests scripts + mypy green, golden pins and figures --check untouched. Stop condition: review record written to docs/superpowers/archive/2026-07-18-full-repo-review.md, all fixes committed with progress-log rows, /security-review run on the batch diff, pushed, gh run green — end the session by presenting the escalation list (if any) to Leo.
```
