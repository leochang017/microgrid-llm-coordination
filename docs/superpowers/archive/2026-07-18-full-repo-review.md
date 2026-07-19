# Full-repo adversarial review — 2026-07-18 batch (Plan C, #4 of 4)

**Scope SHA:** `d51b57fa` · **Baseline (Python 3.12):** 364 tests, ruff clean, mypy clean (37 files), `figures --check` PASS.
**Review method:** 8 read-only reviewer subagents (physics / LP+metrics / agent / messaging / LLM / scripts / tests / config+docs) → 8 independent skeptic verifiers (default-REFUTE) on every CRITICAL/HIGH/MED → controller triage → TDD fixes gated on 3.12 verify + frozen pins.
**Raw findings:** 3 CRITICAL, 7 HIGH, 12 MED, 7 LOW = 29, plus **ENV-1** (found during verification). Mutation check: all 5 core-formula tests (conservation/gini/transfer-cap/commitment-serve/gap_closed) bite.
**Skeptic outcome:** all 22 CRITICAL/HIGH/MED **CONFIRMED, 0 refuted** (unlike phase2.9/3.1 which refuted ~⅓ — these reviewers pre-flagged reachability, so raw yield held). Severity corrections: C4-1 HIGH→MED (proven physics-inert on committed comm@23), C6-5 magnitude (34%→80.4% collision, still latent), C3-3 mechanism (hard crash not silent corruption), C5-2 upgraded (418 real empty entries already in the committed Sonnet cache).

**No committed `reference_runs/` number is wrong.** Every published figure/table value re-derived exactly from committed artifacts. The one wrong *published claim* is a README aside (C8-1), docs-only.

---

## ENV-1 — local `.venv` is Python 3.14 and non-deterministically fails the conservation assert
- **severity** — MED (local-dev hazard; **no published impact**)
- The repo `.venv` is Python **3.14.4 / numpy 2.4.4 / scipy 1.17.1**. Under it `test_golden_numbers.py` trips `sim/engine.py:309` ("export shortfall … desired 0.219, achieved 0.0") **hash-seed-dependently** — the preflight full-suite run got a lucky seed (364 passed), later runs fail. Under a fresh **Python 3.12** venv (numpy 2.5.1 / scipy 1.18.0 — the pinned/CI version) the suite is green and the golden physics is deterministic (6/6 random seeds + HASHSEED=0 pass). All published results were generated under 3.12.
- **Triage: ESCALATE (decision for Leo) + KNOWN LIMITATION.** `pyproject` `requires-python = ">=3.12"` over-claims — the repo is only proven-good on 3.12/3.13. Options: constrain to `">=3.12,<3.14"`, or investigate the numpy-version float-ordering sensitivity in `settle_transfers`. Also: Leo should rebuild the local `.venv` on 3.12 (the current one gives false green/red). Not fixed here (a pyproject constraint is a public-surface + support-policy decision; the float-ordering root-cause is a deep investigation that risks moving golden numbers).

---

## Triage table

Legend: **FIX** = fixed this batch (no published-physics change, gated on 3.12 verify + frozen pins) · **KL** = known limitation (documented, not fixed) · **ESC** = escalate to Leo.

| id | sev | title | verdict | triage | gate |
|----|-----|-------|---------|--------|------|
| C6-1 | CRIT | `figures.py --check` only prints, never asserts → can't detect drift | CONFIRMED | **FIX** | pins added match current values |
| C6-2 | CRIT | `apply_overrides` typo in dict-leaf key silently no-ops (contradicts hard-error contract) | CONFIRMED | **FIX** | code-only |
| C8-1 | CRIT | README "34 pts headroom" subtracts across two household populations (base LP − __llm control) | CONFIRMED | **FIX** (docs) | docs-only; use published 14.2-pt framing |
| C5-1 | HIGH | `_estimate_cost_usd` returns $0.00 for fable/mythos models | CONFIRMED | **FIX** | no committed cost wrong |
| C5-2 | HIGH | `LLMClient.call()` caches empty `stop_reason=max_tokens` responses (418 already in Sonnet cache) | CONFIRMED | **FIX** | `get()` ungated → committed replay byte-identical |
| C6-3 | HIGH | `figures.regen_baselines` reads current YAML, never committed `config.json` → silent baseline drift | CONFIRMED | **FIX** | figures --all/--check byte-identical |
| C6-4 | HIGH | `run.py` names ref-cell dir from `args.seed` not `scenario.seed`; `--set seed=` collides + `"w"`-truncates | CONFIRMED | **FIX** | code-only |
| C2-1 | HIGH | LP `_schedule_from_solution` self-pair renorm over-schedules a sender past its LP `send` bound | CONFIRMED | **KL** | isolated from `optimal_metrics` (published ceiling safe); visualization-only, already disclaimed; touching the solver is risky |
| C3-1 | HIGH | discretionary OFFER dup-transfers a peer in 2+ overlapping circles (vs `_emit_requests` which dedups) | CONFIRMED | **FIX** | 0 overlapping pairs in committed cells → no-op; gate all pins byte-identical |
| C4-1 | MED | `retract_commitment` value-equality `list.remove` can drop the wrong commitment | CONFIRMED | **FIX** | proven inert on comm@23; gate comm@23 pin + replay byte-identical |
| C1-1 | MED | `critical_load_frac` no upper-bound (>1.0) validation → silent `served_critical` corruption | CONFIRMED | **FIX** | all shipped YAMLs [0.2,0.6] pass |
| C2-2 | MED | LP bus-throughput cap per grid-status group, not global → up to 2× bus cap in mixed-status tick | CONFIRMED | **KL** | dormant (all shipped full-island); on published-ceiling solver → don't touch |
| C2-3 | MED | `logging.py` `defector_house_ids` "present⇒realized" docstring false (asdict always emits key) | CONFIRMED | **FIX** (docs) | docstring only |
| C3-2 | MED | grid-connected agents orphan commitments (C2 sweep inside `act()` early-return) | CONFIRMED | **KL** | partial-island only (none shipped); touches commitment lifecycle on committed pre/post-outage ticks → risky |
| C3-3 | MED | `policy._validate` accepts NaN/Inf `recipient_priority.weight` → crash (fallback YAML path only) | CONFIRMED | **FIX** | forced-tool live path unreachable |
| C5-3 | MED | temperature-omission comment overclaims cache "validity" for non-Haiku models | CONFIRMED | **FIX** (comment) | comment only |
| C5-4 | MED | crash-resume only works for `--reference-cell`; docstring implies broader guarantee | CONFIRMED | **FIX** (docstring) | docstring only |
| C6-5 | MED | rubric-variant pairing key `(sender,t_sent)` collides (80.4%) → mis-pair if variants differ in drops | CONFIRMED | **FIX** | committed variants have 0 drops → table byte-identical |
| C6-6 | MED | `eval_explanations` no existence check → same-variant re-run overwrites a paid artifact | CONFIRMED | **FIX** | code-only |
| C7-1 | MED | `test_cache_key_deterministic` only varies `user`; model/system/temp/max_tokens/tools untested | CONFIRMED | **FIX** (test) | test-only |
| C8-2 | MED | pre-commit mypy hook inherits `--ignore-missing-imports` → local silences undeclared-import class | CONFIRMED | **KL/ESC** (config) | CI unaffected; see note |
| C8-3 | MED | committed `defectors@7` `defector_house_ids: []` (pre-C3) not caveated in results §6 | CONFIRMED | **FIX** (docs) | docs-only |
| C1-2 | LOW | hardcoded 50% initial SoC not validated vs `dod_floor_frac>0.5` → first-tick assert crash | — | **KL** | unreachable (all 0.1); documented |
| C2-4 | LOW | round_robin divides by `battery_kwh` with no zero-guard | — | **KL**/FIX | unreachable (all ≥1.0); trivial guard folded if safe |
| C4-2 | LOW | `defector_fraction` outside [0,1] → confusing stdlib error | — | **FIX** | folds into failure_modes validation |
| C4-3 | LOW | `manual` defector assignment no membership check → silent zero-defector run | — | **FIX** | folds into failure_modes validation |
| C5-5 | LOW | module-global `_REGISTRY` fallback (mitigated by subprocess-per-cell convention) | — | **KL** | already documented in code |
| C6-7 | LOW | judge model default same family as agents (advisor wants judge≠author) | — | **KL** | all committed runs passed `--model` explicitly |
| C6-8 | LOW | `render_tables` explanation glob decoupled from cell registry | — | **KL** | no stray artifacts today |

## Fix batches (Task 5)
- **A (scripts):** C6-1, C6-2, C6-3, C6-4, C6-5, C6-6, C8-2 — commit: _pending_
- **B (LLM):** C5-1, C5-2, C7-1 — commit: `880d9b01` (383→395, +12; replay byte-identical)
- **C (sim validation):** C1-1, C3-3, C4-2, C4-3, C2-4 — commit: `5522d0fa` (395→405, +10; pins unchanged)
- **D (agent, pin-gated):** C4-1, C3-1 — commit: `5fcc07da` (405→407, +2; comm@23 pin + replay byte-identical, independently verified)
- **E (docs):** C8-1, C8-3, C2-3, C5-3, C5-4, C2-1 — commit: `667f5102` (407 unchanged; README self-consistent __llm pop)

## Escalation list for Leo (presented at session close)
1. **ENV-1** — rebuild local `.venv` on Python 3.12; decide `requires-python` (`<3.14`?) or investigate numpy float-ordering. No published impact.
2. **C8-1 README** — a wrong headline aside ("34 points") was on the public front page; corrected to the already-published 14.2-pt control→LP framing. Confirm the framing choice.
3. **C8-2 pre-commit mypy** — apply the documented `args`+`additional_dependencies` change and validate with a real `pre-commit` install (needs numpy pinned to CI's version to avoid the stub false positive). Local-only gap; CI unaffected.
4. **KL latent bugs for Phase-4 partial-island / LP-visualization work:** C2-1, C2-2, C3-2, C3-1-semantic (dedup max-vs-sum choice — defaulted to max, matching `_emit_requests`).
