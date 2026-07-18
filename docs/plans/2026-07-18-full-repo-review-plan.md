# Plan C — Full-repo adversarial review (2026-07-18)

> **Batch position: 4 of 4** — run LAST, after the Phase-3 accuracy plan (behavior fixes + comm re-run), the test-hardening plan, and the cleanup plan, so the review sees the final tree. One execution session.
> **Source brief:** `docs/notes/2026-07-18-audit-cleanup-brief.md`, item 1. Leo chose **full fresh re-review** of the entire source (not just the unreviewed diff), knowing the repo passed adversarial reviews at `phase2.9` (65 findings) and `phase3.1` (55 findings), all fixed.

## Goal

A fresh, adversarially-verified review of ALL of `sim/`, `scripts/`, `tests/`, `configs/`, plus docs-vs-code consistency — then fix every confirmed real defect via TDD, document the rest as known limitations, and escalate (never silently fix) anything whose fix would change published-run physics.

## Context

- Since the last full review (`phase3.1-complete`, 2026-07-12) the tree gained: Stage 1/2 live-run tooling fixes, `scripts/figures.py` (+tests), Stage-4 judge changes (`f9b46bc5` temperature gating, `55971ac8` judge token budget), the Sonnet-cell wiring, the C1/C2/C3 negotiation fixes + comm re-run (Plan B), test-accuracy hardening (Plan A), and the cleanup (Plan D). **None of that has had an adversarial pass.** The older code has had two; expect its yield to be lower but non-zero (both prior reviews found criticals in "reviewed" code).
- Verified healthy as of 3.1 (re-attack, but with priors): energy conservation, LP-ceiling validity, RNG determinism, zero-LLM-control isolation.
- Published-results constraint: committed live artifacts under `reference_runs/` and every number in `docs/phase3_results.md` / `docs/phase3_tables.md` are the paper's record. A finding whose fix would alter simulation physics or negotiation behavior **changes what the artifacts mean** — those get an ESCALATE verdict for Leo, with a cost estimate if a re-run would be needed (clean/defectors/noise cells are pre-C2-fix artifacts by explicit decision; that is documented, not a finding).

## Global constraints

- TDD for every fix; suite + ruff + mypy green at every commit; one conventional commit per fix-batch; progress row per task; no Claude attribution; hooks re-stage; security grep before push.
- Frozen unless a CONFIRMED critical says otherwise (and then only via ESCALATE): golden pins, committed-summary pins, determinism tests, `python -m scripts.figures --check`.
- Reviewer subagents are READ-ONLY. Fixes happen in the main session (or a fix subagent per batch), never inside a reviewer.
- Findings must name a concrete failure scenario (inputs → wrong output), not style preferences. The project's simplicity rule applies to fixes: smallest change that kills the bug.

## Traceability

| Brief item | Covered by |
|---|---|
| 1 — "review all the code" | Tasks 1-6 (whole plan) |

---

## Task 1 — Preflight

`git status` clean; full verify green (`ruff check sim tests scripts && mypy && pytest -q`); `python -m scripts.figures --check` green; record HEAD sha and test count in the task log. Snapshot the review scope: `git ls-files 'sim/**' 'scripts/**' 'tests/**' 'configs/**' | wc -l`.

## Task 2 — Reviewer fan-out (read-only subagents, 8 clusters)

Dispatch 8 parallel read-only reviewer subagents, one per cluster, each with: the cluster file list, the paper-critical invariants below, and the output contract `[{file:line, severity CRITICAL/HIGH/MED/LOW, claim, concrete failure scenario, suggested minimal fix}]`.

Clusters:
1. **Physics core** — `sim/engine.py`, `sim/household.py`, `sim/network.py`. Attack: energy conservation (per-tick send/recv/loss/waste bookkeeping), transfer caps (`_transfer_caps` load/solar/√η terms), partial-island, strict-mode invariants, `dt_hours` scaling.
2. **LP + metrics** — `sim/strategies/lp_optimal.py`, `sim/logging.py`. Attack: LP remains a valid ceiling (pure relaxations only), curtailment slack, self-pair renormalization, gini/Jain/min-served/served-critical formulas vs their docstrings, zero-load-house conventions engine-vs-LP.
3. **Agent internals** — `sim/agents/agent.py`, `sim/agents/policy.py`, `sim/agents/memory.py`. Attack: commitment ledger (registration, TTL/expiry, partial serve, the new C1/C2 semantics from Plan B), noised self-view usage in `act()`, REQUEST sizing/fan-out dedup, policy validation bounds.
4. **Messaging + failure modes** — `sim/protocol.py`, `sim/agents/failure_modes.py`, `sim/agents/seeding.py`. Attack: bus budget/drop/latency ordering, `flush_undelivered`, delivered-flag semantics (new in Plan B), defector gating by realization, noise clamp bias, stable_seed usage everywhere RNG is derived.
5. **LLM layer** — `sim/agents/llm.py`, `sim/strategies/llm_agent.py`, `sim/strategies/llm_fallback.py`. Attack: cache-key stability (any drift re-pays committed cells), retry/timeout, temperature gating, tool-use parse, react queue aging, counters aggregation, prepare()-closure registry isolation, reference-cache tier.
6. **Scripts** — `scripts/run.py`, `compare.py`, `sweep.py`, `figures.py`, `eval_explanations.py`, `dose_check.py`, `fetch_data.py`. Attack: figures data layer reads committed artifacts faithfully (no silent fallback to regenerated numbers), `--check` actually guards, override typo-hardness, judge decision-time state pairing, paid-artifact overwrite protection.
7. **Tests-as-code** — the whole `tests/` tree. Attack: tautologies, mock realism vs the SDK contract, fixture drift, anything Plan A's static audit missed dynamically (run targeted mutations where cheap: flip a sign in a formula, confirm a test fails, revert — pick 5 core formulas: conservation, gini, transfer cap, commitment partial-serve, gap_closed).
8. **Config + docs-vs-code** — `configs/scenarios/*.yaml`, `configs/sweeps/`, `pyproject.toml`, `.github/workflows/`, `.pre-commit-config.yaml`, README, `docs/phase3_results.md`/`phase3_tables.md` cross-checked against `reference_runs/` summaries and CLAUDE.md's numbers (the condensed post-Plan-D versions).

## Task 3 — Adversarial verification

Every CRITICAL/HIGH/MED finding goes to an independent skeptic subagent whose prompt is to REFUTE it against the actual code (quote the lines; trace the failure scenario end-to-end; verdict CONFIRMED or REFUTED with evidence). LOWs are triaged by the main session directly. Findings that survive → the fix list. This is the same two-pass discipline that produced the 65- and 55-finding reviews; do not skip it — both prior reviews refuted ~⅓ of raw findings.

## Task 4 — Triage

Sort confirmed findings: (a) **FIX NOW** — defects in current behavior fixable without changing published-run physics; (b) **KNOWN LIMITATION** — real but accepted (document, don't fix); (c) **ESCALATE** — fix would change what committed artifacts mean or needs money (present to Leo with cost estimate; do NOT fix). Write the triage table into the task log before touching code.

## Task 5 — Fix (a)-list via TDD, batched by module

Per fix: failing test → minimal fix → full verify → commit (`fix(review): <finding>` + progress row). Frozen-pin rule from Global constraints applies; if a fix moves ANY golden number, it was mis-triaged — move it to ESCALATE and revert.

## Task 6 — Wrap

1. Known-limitations from (b): append to the existing limitations section of `docs/phase3_results.md` (only items relevant to interpreting results) and/or the review record.
2. Write the review record: `docs/superpowers/archive/2026-07-18-full-repo-review.md` — scope sha, finding counts by severity/verdict, fix list with commits, limitation list, escalation list.
3. Full verify twice + `python -m scripts.figures --check` + clean-install dry-run if `pyproject.toml` was touched.
4. `/security-review` on the batch diff (per the pre-tag rule), security grep, push, `gh run list --limit 1`.
5. Final CLAUDE.md progress row summarizing the whole review (counts, headline fixes, escalations awaiting Leo).

**Stop condition:** everything pushed and green; escalation list (if any) presented to Leo as the session's closing message.
