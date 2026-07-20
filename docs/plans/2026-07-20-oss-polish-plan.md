# 2026-07-20 — OSS polish batch (post-review, docs + metadata only)

**Source:** independent 3-reviewer OSS-readiness evaluation, 2026-07-20 session (architecture/accuracy, security, organization/conciseness reviewers; every finding below re-verified against the actual code/artifacts by the controlling session before landing here).

**Review verdict (record):**
- **Security — CLEAN, safe to be public as-is.** Zero key-shaped strings in tree AND full git history; committed `llm_cache`/`judge_cache` files verified to contain only `{model, system, user, temperature, max_tokens, tools_schema, t_iso, response}` — no auth material; all YAML via `safe_load`; no eval/exec/pickle/shell-injection; CI grants fork PRs nothing. Residual hardening polish only (Actions pinned to tags not SHAs; no lockfile; NREL key-in-query-param is NREL's own API design) — noted, NOT tasked.
- **Accuracy — no published number wrong.** Physics/LP/Gini/Jain/determinism all re-verified by hand-trace. One NEW instrumentation-semantics finding (I-1, Task 3 below): commitment fulfillment is bookkept at emission, not settlement.
- **Organization — professional and navigable.** Four shallow staleness items (Tasks 1–2).

**Scope discipline:** this batch is docs + packaging metadata + comment/docstring caveats ONLY. Zero logic changes, zero prompt-string/cache-key changes, zero event-kind renames (committed `events.jsonl` artifacts and replay pins depend on them). Precedent: fix batch E (`667f5102`) — no TDD red step required for prose-only edits; the full frozen-pin verify still gates the commit.

---

## Task 1 — README polish (4 confirmed staleness items)

- [x] **Line 7:** `(364 as of 2026-07-19)` → `(407 as of 2026-07-20)` (batch #4 added 43 tests after the count was pinned; 407 verified by suite run 2026-07-20).
- [x] **Line 42:** says `see CI badge/logs for the current count` but README has no CI badge. Fix by adding the badge (standard OSS signal) near the top of README:
  `[![CI](https://github.com/leochang017/microgrid-llm-coordination/actions/workflows/ci.yml/badge.svg)](https://github.com/leochang017/microgrid-llm-coordination/actions/workflows/ci.yml)`
  (workflow file verified: `.github/workflows/ci.yml`, name `CI`).
- [x] **Line 82 scripts listing:** add the two missing entries — `figures.py` should HEADLINE the list (it is the reproduce-every-figure/table entry point a paper reviewer needs first, and the status line already advertises it); also add `dose_check.py`. Result: `figures.py · run.py · compare.py · sweep.py · eval_explanations.py · dose_check.py · fetch_data.py`.
- [x] **One new sentence** (near the install/clone or reproduce section): explain the checkout size — `reference_runs/` ships the LLM prompt caches so every live result replays byte-identically with zero API calls; it is ~35k small JSON files / ~13 MB, and is the deliberate reproducibility mechanism, not clutter.

## Task 2 — pyproject.toml OSS metadata

- [x] Add to `[project]`: `license = {text = "MIT"}`, `authors = [{name = "Leo Chang"}]`, `readme = "README.md"`, and a `[project.urls]` block with `Repository = "https://github.com/leochang017/microgrid-llm-coordination"`. Optionally minimal `classifiers` (Programming Language :: Python :: 3.12, License :: OSI Approved :: MIT License, Intended Audience :: Science/Research).
- [x] **MANDATORY (standing rule):** any pyproject change → clean-install dry-run in a fresh venv (`/tmp/microgrid_ci_check` recipe) before commit; then `gh run list --limit 1` after push.

## Task 3 — docs-only honesty caveats (I-1 + three minor notes; comments/docstrings, no behavior)

- [x] **I-1 (the one new substantive finding):** commitment "fulfillment" is measured at emission, not settlement. `sim/agents/agent.py:828` decrements `c.kwh_remaining` by the REQUESTED `kw * dt_hours`; the engine's sender cap (`sim/network.py` stage-1 clipping) routinely scales the actual transfer down (906 sender-cap clip events vs 1,632 executed transfers in committed clean@23), and no settlement result feeds back to agents — `transfer_outcome` in `sim/agents/memory.py:17` is declared but never written. Published served/Gini/Jain are UNAFFECTED (settlement is authoritative). Actions:
  - Add a caveat sentence to the negotiation-table prose in `scripts/figures.py` (`render_tables`, the "Reading it:" string at ~line 765): commitments made/expired are **promise-side counters bookkept at emission; physical delivery is settled (and often scaled down) separately by the engine** — so "fulfilled" ≠ "delivered kWh". Then regenerate `docs/phase3_tables.md` via `python -m scripts.figures --tables` (the ONLY generated-file diff expected).
  - Add the matching caveat to `docs/phase3_results.md` §6 Limitations (one bullet, same content, note the noise-cell "committed less, fulfilled more reliably" aside rests on emission-side counters).
  - One-line comment on `memory.py:17`'s `transfer_outcome`: reserved for Phase-4 settlement feedback; never written today.
  - Closing the loop (feeding settlement back to agents) is a **Phase-4 candidate**, NOT this batch — it would change prompts/cache keys and re-pay committed cells.
- [x] **M-4:** `SENDER_DOD_FLOOR` docstring/comment note in `sim/network.py` (~line 104): the event fires on ANY sender-cap clip (own-load deficit, rate limit, or DoD floor) — the name is historical; do NOT rename (committed events.jsonl + pins).
- [x] **M-1:** `sim/adapters/nrel_solar.py` (~line 88) docstring note: returns 0.0 for `t` before the first sample (a scenario horizon starting before the CSV runs dark, silently) while `ResStockLoad.get_kw` raises — boundary behaviors intentionally differ; noted for scenario authors.
- [x] **M-3:** `scripts/figures.py` fairness-panel or table prose: the LP row's Gini is whichever alternate optimum the solver selects (objective is served-load only, no fairness tiebreak — already in `lp_optimal.py`'s docstring, surfaced here so figure readers see it).

## Task 4 — WRAP

- [x] Full verify twice: `ruff check sim tests scripts` clean; `mypy` clean (37 files); `pytest` 407 ✓ (Task 3 adds no tests — count unchanged); `python -m scripts.figures --check` green (every committed cell byte-identical to its golden pin); regenerated `docs/phase3_tables.md` is the only generated-artifact diff; `docs/figures/*.png` untouched.
- [x] Security grep over staged diff: `git diff --cached | grep -cE 'sk-ant-(api|oat)[0-9a-zA-Z_-]{15,}'` → 0.
- [x] CLAUDE.md progress-log row (same commit), flip this plan's row in `docs/plans/README.md` to **done**, push, one `gh run list --limit 1` peek.

**Execution record (2026-07-20):** all 13 boxes done in one commit. One correction to the
plan's own text: Task 1's `reference_runs/` sentence estimated "~35k files / ~13 MB" — the
measured tree is **35,522 tracked files / ~266 MB apparent** (~35.5k of those are the prompt
caches, ~102 MB; the balance is frozen run artifacts, mostly `messages.jsonl`). The README
sentence carries the measured numbers, not the estimate. Task 3's I-1 line reference also
shifted: the emission-side decrement is `sim/agents/agent.py:830` (`c.kwh_remaining -= kw *
dt_hours`), not `:828`; the 906-clip / 1,632-transfer figures were re-counted from
`reference_runs/haves_havenots_solar__llm/llm_agent/clean__seed23/events.jsonl` and confirmed
exact. M-4's claim was re-derived from `sim/engine.py::_transfer_caps` before writing:
`sender_cap = (solar − load) + rate-and-DoD-bounded battery + grid`, so `SENDER_DOD_FLOOR`
genuinely fires on any of the three binding — the name is a misnomer, as stated.
`docs/phase3_tables.md` (+2 lines) was the only generated-artifact diff; `docs/figures/`
untouched. Clean-install dry-run run on BOTH a fresh 3.14 venv (metadata pickup: Author/License
resolve) and a fresh **3.12** CI-parity venv (407 ✓ / ruff / mypy 37 files / `figures --check`
green).

**Explicitly NOT in scope (reviewed, deliberately untouched):** SHA-pinning Actions + lockfile (low value, official-org actions, no secrets in CI); `round_robin.py`/`round_robin_overlay.py` dedup (near-copies but pinned-baseline churn risk > benefit); `agent.act()` split (replay-gated hot path — Phase 4 if the demo needs it); message-budget-consumed-by-dropped-messages ordering (M-2, defensible as-is, only matters for the deferred confounded `all` cell); `DecideFn` alias strictness (M-5); closing the I-1 feedback loop (Phase 4, changes cache keys).
