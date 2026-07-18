# Plan D — Repo cleanup + CLAUDE.md condensation (2026-07-18)

> **Batch position: 3 of 4** (after the Phase-3 accuracy plan and the test-hardening plan; before the full-repo review). One execution session.
> **Source brief:** `docs/notes/2026-07-18-audit-cleanup-brief.md`, items 3, 4, 5.

## Goal

Archive every completed-phase planning file (Leo's decision 2026-07-18: **archive, not delete**), remove the four verified-dead functions and the superseded Phase-1 plotter, and condense CLAUDE.md from ~101 KB to ~30 KB (standard condensation: archive progress rows through 2026-07-12, compress the five phase-status blocks, fix every stale pointer) — without moving a single published number.

## Context (verified 2026-07-18 by audit)

- All specs/plans for phases 1→3.3 are fully checked (`- [x]`) EXCEPT `plans/2026-07-12-phase3.2-live-runs.md`: 16 unchecked boxes for Stage 3/4 work that is actually **done** (Stage 4 judging 2026-07-17, Sonnet ablation 2026-07-18) — the record is stale, not the work.
- Stale pointers: `CLAUDE.md:270` labels the Phase 3.1 plan "ACTIVE plan — start here" (3.1 finished 2026-07-12); `README.md:273` still titles Phase 3 "in progress"; the Critical-files table omits the 3.3 spec/plan, `docs/phase3_results.md`, `docs/phase3_tables.md`.
- High-confidence dead code (zero non-test call sites): `sim/network.py:95 default_affiliations`, `sim/agents/policy.py:92 policy_to_yaml`, `sim/strategies/lp_optimal.py:300 optimal_served_fraction`, `sim/agents/memory.py:87 MemoryStream.from_jsonl`. Also `scripts/plot_phase1_results.py` (only reference: README's architecture listing) and its output `docs/figures/phase1_real_data_result.png` (only reference: the phase-2.9 plan being archived).
- Explicit KEEPS (do not remove): `sim/adapters/pecan_street.py` + `configs/scenarios/24h_real.yaml` + pecan fixtures (CLAUDE.md documents them "for reference only"); all other scenario YAMLs incl. docs-only `24h_resstock.yaml` / `long_outage_72h.yaml` (the 72h scenario backs a recorded deferred live run); `pyarrow` in `[data]` (no direct import but required as the `pd.read_parquet` engine in `sim/adapters/resstock.py:63`); `docs/phase3_mock_sweep.md` (data source for the failure-axis figure overlay, cited at `scripts/figures.py:344-348`); every strategy module (all reachable via the importlib dispatch in `scripts/run.py:29` / `scripts/compare.py:137`).
- No TODOs, no commented-out code blocks, no orphan fixtures anywhere — the sweep confirmed the tree is otherwise clean.

## Decisions

- Archive location: `docs/superpowers/archive/{specs,plans}/` via `git mv` (history preserved; public repo keeps its research trail one directory deeper). One-off docs join `docs/superpowers/archive/`.
- Stays active: `docs/superpowers/specs/2026-07-12-remaining-phases-roadmap.md` (the live pointer to Phase 4) and this batch's plans in `docs/plans/`.
- Dead functions are deleted, their test blocks migrated or deleted (details in Task 3) — git history is the archive for code. FLAGGED: `optimal_served_fraction`'s two test call sites are real LP-behavior tests; they migrate to `optimal_metrics(...)["served_load_fraction"]` rather than being deleted.
- Progress-log split point: rows dated **≥ 2026-07-15** stay in CLAUDE.md (the live-runs era, plus every row this batch adds); rows 2026-07-06 → 2026-07-12 move verbatim to `docs/progress_log_archive.md`.
- `scripts/plot_phase1_results.py` is deleted; `docs/figures/phase1_real_data_result.png` moves to the archive dir (it documents a corrected historical result quoted in the archived plans).

## Global constraints

- This plan changes **zero** runtime behavior: after every task, `ruff check sim tests scripts && mypy && pytest -q` green, and at wrap `python -m scripts.figures --check && python -m scripts.figures --all` must leave `git status` clean for `docs/figures/` (byte-identical regeneration proves nothing moved).
- Frozen: all golden pins, the committed-summary pin in `tests/test_figures.py`, every number in `docs/phase3_results.md`/`docs/phase3_tables.md`.
- `git mv` only for moves (never delete+add). One conventional commit per task, CLAUDE.md progress row in the same commit, no Claude attribution, hooks re-stage on reformat.
- Task 3 touches `pyproject.toml` (comment only) → clean-install dry-run before that commit anyway (the rule keys on the file, not the size of the edit).
- Every cross-reference to a moved file must be updated in the same commit as the move (`grep -rn "<filename>" --include="*.md" .` before and after; zero dangling references).

## Traceability

| Brief item | Covered by |
|---|---|
| 3 — clean up unused planning files | Tasks 1, 2 |
| 4 — reorganize + condense CLAUDE.md | Tasks 4, 5 |
| 5 — clean up unused code | Task 3 |

---

## Task 1 — True-up the Phase 3.2 plan's stale checkboxes

In `docs/superpowers/plans/2026-07-12-phase3.2-live-runs.md`: check all 16 stale boxes (`- [ ]` → `- [x]`) for Stage 3 (Sonnet ablation, done 2026-07-18), Stage 4 (explanation judging, done 2026-07-17) and the credential-gate preflight, and add one line under the plan title:

```markdown
> **Record trued-up 2026-07-18:** Stages 3 + 4 completed after the 3.2 wrap (see CLAUDE.md progress rows 2026-07-17 / 2026-07-18); the boxes below were checked retroactively to match reality before archiving.
```

Do NOT alter any other text. Verify: `grep -c "\- \[ \]" docs/superpowers/plans/2026-07-12-phase3.2-live-runs.md` → 0.

**Commit:** `docs(phase3.2): true up stale Stage 3/4 checkboxes before archiving`

## Task 2 — Archive completed-phase specs, plans, and one-off docs

1. `mkdir -p docs/superpowers/archive/specs docs/superpowers/archive/plans`
2. `git mv` into `archive/specs/`: `2026-05-14-phase1-simulator-design.md`, `2026-05-29-phase1.6-hardening-design.md`, `2026-06-13-phase2-llm-agent-design.md`, `2026-07-06-phase2.9-correctness-hardening.md`, `2026-07-07-phase3-benchmark-design.md`, `2026-07-12-phase3.1-prelive-hardening.md`, `2026-07-16-phase3.3-analysis-design.md` (7 files; `2026-07-12-remaining-phases-roadmap.md` STAYS).
3. `git mv` into `archive/plans/`: all 8 files currently in `docs/superpowers/plans/`.
4. `git mv docs/2026-07-15-opus-phase3.2-execution-prompt.md docs/superpowers/archive/`
5. `git mv docs/figures/phase1_real_data_result.png docs/superpowers/archive/` (paired with Task 3's plotter deletion; the archived phase-2.9 plan is its only referrer).
6. Write `docs/superpowers/archive/README.md`: a one-line-per-file index (phase, date span, completion tag) and the sentence "Everything here is a completed phase's record; the authoritative summary lives in CLAUDE.md's phase table and `docs/progress_log_archive.md`."
7. Update every reference to the moved paths: `README.md` (links to phase1/1.6/2/3/3.1 specs+plans), `docs/superpowers/specs/2026-07-12-remaining-phases-roadmap.md` (links to 3.1/3.2 files), and leave `CLAUDE.md` references for Task 4's rewrite (note them in the task log). Gate: `grep -rn "superpowers/specs/2026-0" --include="*.md" . | grep -v archive` shows no dangling old paths (same for `superpowers/plans/`).

**Commit:** `chore(docs): archive completed-phase specs/plans + one-off docs under docs/superpowers/archive/`

## Task 3 — Delete verified-dead code (TDD: deletion is red-proofed by the suite)

For each item: delete, run the full suite, resolve exactly the listed test fallout, re-run green.

1. `sim/network.py:95` `default_affiliations` — delete the function; delete its tests (`tests/test_network.py:210-225`; read the block first — delete only the tests whose sole subject is `default_affiliations`).
2. `sim/agents/policy.py:92` `policy_to_yaml` — delete; rework `tests/test_policy.py:27`'s round-trip into a parse-only test of `policy_from_yaml` (keep the parse assertions, drop the serialize leg) or delete it if the file already covers parsing elsewhere — read the file and keep exactly one parse test.
3. `sim/strategies/lp_optimal.py:300` `optimal_served_fraction` — delete; migrate the two call sites `tests/test_lp_optimal.py:183` and `tests/test_stress_scenarios.py:46` to `optimal_metrics(...)["served_load_fraction"]` (these are real LP tests — they stay, only the accessor changes; confirm the exact key name in `optimal_metrics`' return before editing).
4. `sim/agents/memory.py:87` `MemoryStream.from_jsonl` — delete; delete its test (`tests/test_memory.py:62` block).
5. `git rm scripts/plot_phase1_results.py`; remove its row from README's architecture listing (`README.md:82`).
6. `pyproject.toml:19`: annotate the survivor —
```toml
data = ["pandas>=2.2", "pyarrow>=16.0", "requests>=2.32"]  # pyarrow: pd.read_parquet engine (resstock adapter) — no direct import, do not "clean up"
```
7. Docstring sweep: `grep -rn "optimal_served_fraction\|policy_to_yaml\|default_affiliations\|from_jsonl" sim scripts tests` → only `MemoryStream.write_jsonl`-adjacent mentions may remain; fix any docstring naming the deleted symbols (the audit saw `optimal_served_fraction` mentioned in `sim/` docstrings).
8. Update the pinned scenario/test counts if Plan A's Task 7 landed (scenario count is untouched — 21 stays; only `def test_` totals shift; update the docs number at wrap, Task 6).
9. Clean-install dry-run (pyproject touched), full verify.

**Commit:** `refactor: remove dead code (default_affiliations, policy_to_yaml, optimal_served_fraction, MemoryStream.from_jsonl, phase-1 plotter)`

## Task 4 — Condense CLAUDE.md (standard condensation)

Rewrite CLAUDE.md preserving these sections VERBATIM (they are load-bearing rules, not history): Research question · Timeline+venue · Four-phase plan table (update statuses) · all three Locked-decisions sections · Advisor sign-off 2026-07-15 · User context · Workflow preferences · Project skills · Claude Code efficiency setup · Conventions · Data access · Important warnings · What to do at the start of a new session.

Changes:
1. **Phase-status blocks (currently 5 blocks, ~45 lines + huge Phase-3 bullets) → one `## Status` section**: the phase table (every row now *complete* through 3.3, with tags) + one paragraph of current state (headline numbers: clean 3-seed +5.8±1.0 vs control / 29.0%±2.9 gap-closed; defectors +2.3, noise +0.87, comm result per the post-rerun number from Plan B; Sonnet ablation tie 0.6685 vs 0.6726; Stage 4 judge scores; total live spend) + a "next: Phase 4 (spec/plan to write), venue decision with advisor" line + pointers: `docs/phase3_results.md` for the full story, `docs/superpowers/archive/` for phase records, `docs/progress_log_archive.md` for row-level history. Every number retired from CLAUDE.md must already live in `docs/phase3_results.md` or the archive — verify each before deleting, add it there if not.
2. **Progress log**: move rows dated 2026-07-06 → 2026-07-12 verbatim to `docs/progress_log_archive.md` (append below its header, newest-first order preserved; update that file's "rows ≤" note to "≤ 2026-07-12"). Keep rows ≥ 2026-07-15 + all rows added by this batch. The append-per-task rule statement stays.
3. **Critical files table**: rewrite — roadmap spec (start here for Phase 4), `docs/plans/` (active maintenance batch), `docs/phase3_results.md`, `docs/phase3_tables.md`, `docs/figures/`, archive dir, progress-log archive, `sim/`, `tests/`, `configs/scenarios/`.
4. **Session-start block**: step 2-3 now say "read `docs/superpowers/specs/2026-07-12-remaining-phases-roadmap.md`; if a `docs/plans/` batch is unfinished, resume its first unchecked task".
5. Delete: the per-phase "status" prose now duplicated by №1, the Phase-2 deferred-follow-ups list (fold any still-open item into the Status paragraph — as of this writing only "peer INFORM-only state" style items already absorbed by Phase 3; verify each bullet is either done, absorbed, or explicitly carried into Status), and the superseded-struck-through advisor warning line (keep the warning list itself).
6. Size gate: `wc -c CLAUDE.md` ≤ 35,000. Content gate: a fresh-session reader can answer — what is the research question, what phase are we in, what are the headline numbers, what is next, where is every detail — from CLAUDE.md alone.

**Commit:** `docs(claude): condense CLAUDE.md — single status section, progress rows ≤07-12 archived, pointers fixed`

## Task 5 — README refresh (structural)

1. Status line + `README.md:273` header: Phase 3 complete (benchmark + live runs + analysis + Stage 3/4), Phase 4 next. (Plan B already inserted the Stage-3/4 result sentences; this task only fixes structure/labels it didn't own.)
2. Point spec/plan links at `docs/superpowers/archive/…` paths (from Task 2's reference sweep).
3. Architecture listing reflects Task 3 (no plotter).

**Commit:** `docs(readme): phase 3 complete, archived doc paths, architecture listing current`

## Task 6 — Wrap

1. Full verify twice: `ruff check sim tests scripts && mypy && pytest -q`.
2. `python -m scripts.figures --check && python -m scripts.figures --all` → `git status` clean (byte-identical figures; nothing this plan touched moved a number).
3. Update the stated test count in README/CLAUDE.md to `pytest --collect-only -q | tail -1`'s number.
4. **Public-repo hygiene pass** (Leo 2026-07-18: the repo is open source and public — organize accordingly): (a) full-tree key scan `git grep -IlE 'sk-ant-(api|oat)[0-9a-zA-Z_-]{15,}'` → 0 matches (baseline verified 2026-07-18 across 34,158 tracked files); (b) confirm no `.env*` files tracked and `.gitignore` still covers `runs/`, `data/`, regenerable baselines; (c) README reads front-door-first for an outside visitor: what this is, headline result, install, reproduce-the-figures command, license, then history — reorder sections if needed; (d) confirm `LICENSE` (MIT) is intact and referenced from README.
5. Security grep (staged diff, key-shaped pattern) → 0; push; `gh run list --limit 1`.

**Commit:** `docs: cleanup batch wrap — counts synced, figures byte-verified`
