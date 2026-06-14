# Microgrid Project — Authoritative Context

> **Resume protocol for new sessions:** read this file first. The spec is the authoritative design; the plan is the authoritative TDD task list.

## Research question

Can a population of LLM agents, one per household, negotiate peer-to-peer to allocate scarce energy during a grid outage in a way that is **(a)** fair across heterogeneous households, **(b)** robust to incomplete or incorrect information, and **(c)** explainable to residents?

The contribution is on the **CS/ML axis** (natural-language agent coordination, robustness, explainability), not the power-systems axis. Classical optimization handles (a) under strong assumptions, struggles with (b), and does not attempt (c). That gap is the paper.

## Timeline + venue

- Started: 2026-05-14. Runway: summer + potentially the following school year (no fixed deadline).
- Target venues (refined per advisor 2026-05-26): Climate Change AI workshop @ NeurIPS, multi-agent LLM workshops, AAMAS COIN-style venues, or AAAI Student Abstracts (good fit for career stage). **Not** main NeurIPS — contribution isn't ML-methodological in the way they care about.

## Four-phase plan

| Phase | Weeks | Status | What it builds |
|-------|-------|--------|----------------|
| 1 — Simulator | 1-4 | **complete** | Deterministic discrete-time microgrid sim, no agents |
| 1.6 — Pre-Phase-2 hardening | — | **complete** | Ownership/management comm-graph overlays, stress scenarios that break round-robin, centralized LP upper-bound baseline, gap-closed reporting (cold/hot ResStock regions pending data fetch) |
| 2 — LLM agent layer | 5-8 | not started | Per-household LLM agent, natural-language P2P messaging |
| 3 — Benchmark & experiments | 9-14 | not started | Scenario suite + baselines + metrics (Gini, served-critical-load, explanation quality) |
| 4 — Web demo & paper writeup | 15-20 | not started | SvelteKit/Next.js visualization on Vercel + paper |

> **Phase 1.6 is a hard gate on Phase 2**, inserted by advisor (Yongfeng) on 2026-05-26. Rationale: the current 12h-July-overnight scenario has a 98.5% no-coordination ceiling, leaving only ~0.5% headroom for the LLM layer — Phase 2 would be a null result by construction. Must establish a regime where round-robin visibly fails before building LLM agents.

Each phase has its own spec + implementation plan in `docs/superpowers/`.

## Phase 1 status

- **Spec:** `docs/superpowers/specs/2026-05-14-phase1-simulator-design.md`
- **Plan:** `docs/superpowers/plans/2026-05-14-phase1-simulator.md` (26 tasks, TDD)
- **Approved:** 2026-05-14
- **Execution mode:** Inline (Claude executes tasks in-session, batched ~5 at a time with check-ins). Not subagent-driven — per project conventions, every line must be understood by the student.
- **Started executing:** 2026-05-14
- **Current position:** ✅ **Phase 1 complete + Phase 1.5 NREL ResStock integration done.** 70 tests pass; mypy + ruff clean. Three data sources work: synthetic (toy), pecan_street (requires university affiliation — not used), resstock (public, no signup). On real Texas ResStock load + 12h overnight outage: no_coord serves 81.3% with 254 kWh unmet; round_robin serves 83.9% with 218 kWh unmet. Round-robin saves **35.7 kWh of real residential load** and reduces welfare Gini by 15%. The advisor email is drafted asking whether to use ResStock primary or have him sponsor Pecan Street access. Tagged `phase1-complete`. **Advisor approved Phase 1 on 2026-05-26 but gated Phase 2 behind a Phase 1.6** (ownership/management comm-graph overlays + round-robin-breaking stress scenarios + centralized LP upper-bound baseline + 1-2 more public datasets — see "Locked Phase 1.6 design decisions"). **Phase 1.6 shipped 2026-05-29** (96 tests, tagged `phase1.6-complete`); only the cold/hot-climate ResStock scenario YAMLs remain, pending data fetch. Next: Phase 2 brainstorming (LLM agent layer).

### Progress log

Update this after every committed task. Newest entries on top.

| Date | Task | Commit | Tests | Note |
|------|------|--------|-------|------|
| 2026-06-13 | **P2 Task 7 — AnthropicLLMClient + retries** ✅ | _(this commit)_ | 127 ✓ | `AnthropicLLMClient` calls `messages.create` with temperature=0; exponential backoff on RateLimit/APIConnection/InternalServerError. Cache hit bypasses the API entirely. HTTP-level tests use `unittest.mock`. |
| 2026-06-13 | **P2 Task 6 — LLMClient abstract + MockLLMClient** ✅ | _(this commit)_ | 124 ✓ | `sim/agents/llm.py`: `LLMRequest`/`LLMResponse` data shapes, `LLMClient` base class (handles cache get/put), `MockLLMClient` (substring-keyed canned responses for tests). Real `AnthropicLLMClient` lands in Task 7. |
| 2026-06-13 | **P2 Task 5 — PromptCache (two-tier sha256)** ✅ | _(this commit)_ | 120 ✓ | `sim/agents/cache.py`: content-addressed prompt cache (sha256 over canonical-json of model+system+user+temp+max_tokens+tools_schema). Two-tier lookup: local then reference_runs/ cache. Atomic writes via tmp+os.replace. |
| 2026-06-13 | **P2 Task 4 — Message speech-act schema** ✅ | _(this commit)_ | 114 ✓ | Frozen `Message` dataclass with REQUEST/OFFER/ACCEPT/REJECT/COUNTER/INFORM vocabulary in `sim/agents/protocol.py`. `new_correlation_id(rng)` is deterministic when seeded RNG passed in. MessageBus lands in Task 8. |
| 2026-06-13 | **P2 Task 3 — MemoryStream + top-K retrieval** ✅ | _(this commit)_ | 110 ✓ | Park-adapted append-only `MemoryStream` in `sim/agents/memory.py`. Retrieval is α·recency + β·importance + γ·similarity, γ defaulting to 1.0 (no embedder in v0; Phase 3 hook). JSONL round-trip for run-output persistence. Recency uses 4 h half-life. |
| 2026-06-13 | **P2 Task 2 — Policy dataclass + validator** ✅ | _(this commit)_ | 105 ✓ | `sim/agents/policy.py` defines `Policy` (frozen dataclass) with hand-rolled validator + YAML round-trip + a `default_round_robin_fallback()` static method used when LLM output is unparseable. No Pydantic dep. mypy --strict clean. |
| 2026-06-13 | **P2 Task 1 — anthropic dep + sim/agents/ scaffold** ✅ | _(this commit)_ | 98 ✓ | Added `anthropic>=0.40` to core deps (+ mypy override). New `sim/agents/__init__.py` documents the planned module list (policy/memory/protocol/cache/llm/reflection/failure_modes/agent). Clean-install dry-run in fresh `/tmp/microgrid_ci_check` venv passed (`pip install -e '.[dev]' && pytest`). No behavior change yet; substrate is in place for Tasks 2-26. |
| 2026-05-29 | **P1.6 Task 16 — wrap-up + tag** ✅ | _(this commit)_ | 96 ✓ | README gains a Phase 1.6 section (affiliations YAML, 4 strategies, stress scenarios, fetch commands, gap-closed table); CLAUDE.md phase table marks 1.6 complete; plan checkboxes ticked. Clean-install dry-run (fresh venv) + ruff + mypy all green. Tagged `phase1.6-complete`. **Pending follow-up:** fetch VT/AZ ResStock + winter/heatwave scenario YAMLs. Next: Phase 2 brainstorming (LLM agent layer). |
| 2026-05-29 | **P1.6 Task 15 — gap-closed comparison** ✅ | _(this commit)_ | 96 ✓ | `scripts/compare.py` + `sim/strategies/lp_optimal.optimal_metrics`: runs the 3 heuristics through the engine, takes the LP objective as the ceiling, prints a markdown table with `gap_closed = (served − rr)/(lp − rr)`. On haves_havenots: no_coord 0.456 / rr 0.525 / overlay 0.525 / **lp 0.529**, and the table exposes the fairness tension — served-max LP gini 0.365 is *worse* than round_robin's 0.242. |
| 2026-05-29 | **P1.6 Task 14 — stress scenarios + acceptance** ✅ | _(this commit)_ | 92 ✓ | `haves_havenots.yaml` (12 h outage, bimodal big-have/tiny-havenot) is the showcase + acceptance test: no_coord 0.456 (≪ old 0.985 ceiling), round_robin still leaves 171 kWh unmet, **LP ceiling 0.529 > rr 0.525** (room remains). `long_outage_72h.yaml` = extreme total-scarcity regime (LP≈no_coord; only rationing *fairness* matters). **LP ceiling now reported via `lp_optimal.optimal_served_fraction` (LP objective), NOT the engine realization** — decided 2026-05-29 because the engine's greedy per-tick step() can't faithfully execute the LP's planned dispatch, so realized-LP could fall below round_robin. Finding: served-maximizing LP is *less* equitable (higher gini) than round_robin — the core fairness tension. **Deferred:** `winter_morning_lowsolar` + `heatwave_ac` need the VT/AZ ResStock downloads (commands in plan Task 13) — pending data fetch. |
| 2026-05-29 | **P1.6 Task 13 — ResStock region fixture** ✅ | _(this commit)_ | 91 ✓ | Cold-region adapter coverage via `tests/fixtures/resstock_cold_sample.csv`. The existing `fetch_data resstock --state <ST>` already supports any state (no code change) — fetch commands for cold (VT) + hot (AZ) regions documented in the plan for the winter/heatwave stress scenarios. |
| 2026-05-29 | **P1.6 Task 12 — LP end-to-end + determinism** ✅ | _(this commit)_ | 90 ✓ | `configs/scenarios/synthetic_lp_smoke.yaml` (2×3, bimodal, 3 h islanded). Tests: LP dominates all heuristics (the only guaranteed invariant) + byte-identical determinism. **Finding:** `round_robin` is NOT a guaranteed floor — lossy/poorly-targeted sharing can fall *below* no_coordination; only LP is a guaranteed ceiling. So "gap closed" is measured relative to round_robin, and round_robin-helps is empirical (stress scenarios). Smoke numbers: no_coord 0.704 < rr 0.759 = overlay 0.759 < lp 0.764. |
| 2026-05-29 | **P1.6 Task 11 — lp_optimal LP oracle** ✅ | _(this commit)_ | 88 ✓ | `sim/strategies/lp_optimal.py`: full-horizon LP (scipy HiGHS) over all ticks×houses with perfect foresight + full-bus access (ignores comm graph) → served-load ceiling. Vars per tick×house: ch/dis/imp/exp/send/recv/served + soc. Constraints: power balance, √η SoC recurrence, SoC/rate/grid caps, per-grid-group bus balance + throughput (enforces no-wheeling). Solved once in `prepare`, sliced per tick; aggregate send/recv converted to pairwise Transfers. Hand-checked 2-house instance: transfers 2 kW from charged to deficit house. |
| 2026-05-29 | **P1.6 Task 10 — scipy dependency** ✅ | _(this commit)_ | 87 ✓ | Added `scipy>=1.13` to core deps (+ mypy override) for the LP baseline. Clean-install dry-run in a fresh `/tmp/microgrid_ci_check` venv passed (87 tests) — verified packaging before commit per the standing rule. |
| 2026-05-29 | **P1.6 Task 9 — prepare hook** ✅ | _(this commit)_ | 87 ✓ | `engine.run` gains an optional `prepare(scenario, households, solar, loads, neighborhood) -> DecideFn` hook called once before the tick loop — lets a foresighted strategy (the LP) precompute a schedule. `scripts/run.py` resolves both `decide_transfers` and `prepare`, adds a `--strategy` override, and writes to `runs/<scenario>/<strategy>/<ts>/`. Myopic strategies unaffected. |
| 2026-05-29 | **P1.6 Task 8 — bimodal sampling** ✅ | _(this commit)_ | 86 ✓ | `household_sampling.mode: "uniform"\|"bimodal"`. Bimodal draws each house from a seeded "have" (big PV+battery) or "havenot" (little) cluster by `have_fraction` — the have/have-not heterogeneity the advisor wants stress scenarios to exploit. Uniform draw order unchanged ⇒ existing scenarios byte-identical. |
| 2026-05-29 | **P1.6 Task 7 — round_robin_overlay** ✅ | _(this commit)_ | 84 ✓ | New strategy: same share-the-headroom logic as round_robin but targets `union_neighbors` (geographic ∪ owner ∪ manager ∪ …). Intermediate baseline showing trust-circle structure has value before the LLM layer. Geographic round_robin retained as the weak baseline. |
| 2026-05-29 | **P1.6 Task 6 — engine overlay wiring** ✅ | _(this commit)_ | 83 ✓ | `sample_households` assigns each house its per-type affiliation group (inverted from `scenario.affiliations`); `run()` now builds the neighborhood via `build_overlay_neighborhood`. Existing scenarios (empty affiliations) get geographic-only graphs — behavior unchanged. |
| 2026-05-29 | **P1.6 Task 5 — scenario affiliations** ✅ | _(this commit)_ | 82 ✓ | `load_scenario` parses the `affiliations:` YAML block into `Scenario.affiliations` (type→group→house tuples) and validates every referenced house id exists in the grid (raises on unknown). Default empty. |
| 2026-05-29 | **P1.6 Task 4 — default_affiliations** ✅ | _(this commit)_ | 79 ✓ | Seeded generator for a plausible default trust-circle structure (2 multi-property owners, 1 top-row HOA, 1 DR aggregator). Deterministic per seed. |
| 2026-05-29 | **P1.6 Task 3 — build_overlay_neighborhood** ✅ | _(this commit)_ | 77 ✓ | New builder layers affiliation cliques (type→group→members, each group a clique) atop the geographic graph. Empty affiliations ⇒ geographic-only. Foundation for ownership/management trust circles. |
| 2026-05-29 | **P1.6 Task 2 — edge layers + union_neighbors** ✅ | _(this commit)_ | 75 ✓ | `Neighborhood` gains `edges_by_type` (per-type adjacency incl. reserved `"geographic"`) + `union_neighbors(hid)` (sorted dedup union across layers, falls back to comm_graph). `build_grid_neighborhood` now populates the geographic layer. Back-compat: comm_graph unchanged. |
| 2026-05-29 | **P1.6 Task 1 — Household.affiliations** ✅ | _(this commit)_ | 72 ✓ | `Household` gains `affiliations: dict[str,str]` (affiliation-type → group-id) defaulting empty, the per-house substrate for comm-graph overlay edges. No physics change; existing scenarios unaffected. |
| 2026-05-14 | **Phase 1.5 — NREL ResStock real-data path** ✅ | _(this commit)_ | 70 ✓ | New `sim/adapters/resstock.py` reads ResStock 15-min Parquet/CSV files; `_build_data` dispatches on `data_source: resstock`; `scripts/fetch_data.py` gains a `resstock` subcommand that downloads N buildings from the OEDI Data Lake. Downloaded 30 real Texas buildings (~110 MB, full-year 2018). First real-data result: on a 12 h overnight outage, round_robin saves 35.7 kWh of real residential load vs no_coord (Gini 0.052 vs 0.060). Unblocks the project from Pecan Street's institutional-access requirement. |
| 2026-05-14 | **Post-review fixes** ✅ | `fb406d0` | 68 ✓ | Independent `superpowers:code-reviewer` agent flagged 4 critical + 8 important items. Fixed: C2 (NREL noise → hash of (seed,t)), C3 (real-data integration test against in-repo fixtures), C4 (Transfer rejects NaN/Inf), I2 (`overnight_outage_hard.yaml` scenario where round_robin saves 30 kWh of unmet load; strict integration test), I5 (TRANSFER_EXECUTED post-saturation kw), I6 (Scenario validates dt_hours/rows/cols/end-after-start in __post_init__), I8 (scripts/run.py try/finally). Skipped C1 (the "same-house send+receive RT loss" critique assumes all-through-battery; current code matches realistic DC-bypass inverter semantics — documented in spec limitations). Spec gains an explicit Known Limitations section. |
| 2026-05-14 | **Task 25 — Phase 1 wrap-up** ✅ | `fe09358` | 61 ✓ | Full suite green: 61 tests, mypy clean, ruff clean. CLI sanity-run on `24h_uniform.yaml` produced `served=1.000 gini=0.000 wasted_kwh=898.1 unmet_kwh=0.0 transfers=1260`. README status block updated. Tagged `phase1-complete`. |
| 2026-05-14 | Task 24 — `scripts/fetch_data.py` | `d2e0884` | 61 ✓ | One-shot NREL NSRDB downloader: `python -m scripts.fetch_data --lat … --lon … --year …` writes hourly GHI CSV. Requires `NREL_API_KEY` + `NREL_EMAIL` env vars (free signup at developer.nrel.gov). Prints instructions for the Pecan Street manual download (researcher account at pecanstreet.org/dataport). No test — would hit the live network. |
| 2026-05-14 | Task 23 — wire real adapters into engine | `7ec721e` | 61 ✓ | Adds `data_paths: dict[str,str]` and `house_dataids: tuple[int,...]` to `Scenario`. Refactors `sim/engine.py` data construction into `_build_data(scenario, households)` dispatching on `scenario.data_source` (`"synthetic"` | `"pecan_street"`). Adapter imports stay local to the `pecan_street` branch so the synthetic-only path doesn't pull pandas. Adds `configs/scenarios/24h_real.yaml` template. Smoke test now monkey-patches `_build_data`. |
| 2026-05-14 | Task 22 — NREL solar irradiance adapter | `85196f8` | 61 ✓ | `sim/adapters/nrel_solar.py` with `NRELSolar(csv_path, seed, derate=0.85, noise_std=0.02)`. Reads hourly GHI W/m² from an NSRDB CSV, linearly interpolates to any sub-hourly timestamp, applies a small seeded multiplicative noise. Same seed + same call sequence → byte-identical outputs (determinism test). Ships against `tests/fixtures/nrel_sample.csv`. |
| 2026-05-14 | Task 21 — Pecan Street adapter skeleton | `ffb0c45` | 57 ✓ | `sim/adapters/pecan_street.py` with `PecanStreetLoad(csv_path, dataid).get_kw(t)` against in-repo `tests/fixtures/pecan_sample.csv`. Forward-fills gaps ≤1 h; raises on longer (data must be clean, not silently fudged). pandas now in dep tree → added a `[[tool.mypy.overrides]]` for pandas to ignore missing stubs. Real-engine dispatch lands in Task 23. |
| 2026-05-14 | Task 20 — full README | `e288128` | 54 ✓ | `README.md` rewritten: install, run, scenario YAML reference, architecture diagram, phase-1 status checklist. Anyone cloning the public repo can now figure out how to run the simulator. |
| 2026-05-14 | Task 19 — CLI runner | `af1a0ff` | 54 ✓ | `scripts/run.py` ships `python -m scripts.run --scenario <yaml> [--out-dir runs] [--no-strict]`. Resolves the strategy by importing `sim.strategies.<scenario.strategy>` and calls its `decide_transfers`. Output to `runs/<scenario_id>/<timestamp>/`. Manually smoke-tested + clean-venv verified. Also adds `scripts` to CI's `ruff check`. |
| 2026-05-14 | Task 18 — physics smoke test | `1748e46` | 54 ✓ | `tests/test_physics_smoke.py` runs a 2×2 grid for 24 h with monkey-patched flat 2 kW solar + 1 kW constant load + η=1 + DoD=0 + oversized batteries. Hand-computed end SoC: 50 + 24 = exactly 74.0 kWh per house. If this test ever fails, do NOT adjust the expected — `sim/household.py:step()` has regressed. |
| 2026-05-14 | Task 17 — integration test (rr vs no-coord) | `63b8880` | 53 ✓ | `tests/test_integration.py` runs the 24h_uniform scenario end-to-end with both strategies and asserts `gini(round_robin) <= gini(no_coordination)`. Real numbers: no_coord = 99.9% served / 1.1 kWh unmet / 0 transfers; round_robin = 100% / 0 / 1,260 transfers. Synthetic data is too easy — Phase 3 with Pecan Street will produce more interesting differentiation. Determinism check (byte-identical state.jsonl) also lives here. |
| 2026-05-14 | Task 16 — engine main loop + invariants | `660fddd` | 51 ✓ | `run(scenario, decide_transfers, logger, strict=True)` drives the per-tick loop: lookup solar/load/grid, emit OUTAGE_* on transitions, decide transfers, build sender/receiver caps from current state (battery rate + DoD/headroom + √η), settle, step each house, assert SoC bounds + non-negative wasted/unmet in strict mode, log state+events, finalize. **Simulator runs end-to-end** on `synthetic_smoke.yaml` (2880 state rows / run) and same-seed runs are byte-identical (determinism test). Phase 1 currently only supports `data_source: synthetic`; Task 23 adds real-data dispatch. |
| 2026-05-14 | Task 15 — engine household sampling | `227812a` | 49 ✓ | `sim/engine.py` with `sample_households(scenario, rng)` — deterministically samples PV size, battery capacity, derived charge rate per house from `scenario.household_sampling` ranges. Same seed → byte-identical neighborhood. Verified in a fresh `/tmp/microgrid_ci_check` venv per the new "verify before commit" preference. **Test totals had been miscounted as 22/26/30/35/37/40/41 — actual count is 5+11+6+13+5+2+4=46 through Task 14, now 49 with Task 15.** |
| _CI fix_ | `pyproject.toml` setuptools.packages.find | `d23fc7f` | (n/a) | Adding `configs/` in Task 11 broke setuptools auto-discovery on clean installs (CI). Local venv had been editable-installed pre-configs/ so the issue was invisible locally. Tasks 11-14 shipped with red CI. Fix: explicit `include = ["sim*"]`. Lesson encoded in workflow preferences. |
| 2026-05-14 | Task 14 — summary metrics | `b7da9bf` | 46 ✓ | Adds `JsonlLogger.finalize(dt_hours)` that re-reads `state.jsonl` + `events.jsonl`, computes `served_load_fraction`, `gini_welfare` over per-house served-load fraction, `wasted_kwh_total`, `unmet_kwh_total`, `transfer_count`, writes `summary.json`. Phase 1 uses served-load fraction as the welfare proxy for Gini; Phase 3 will swap in a needs-weighted welfare model. |
| 2026-05-14 | Task 13 — JsonlLogger | `b38df99` | 40 ✓ | `sim/logging.py` with `JsonlLogger(run_dir, scenario_id)`: writes per-(house, tick) state rows to `state.jsonl`, discrete events to `events.jsonl`, resolved scenario to `config.json`. `summary.json` lands in Task 14. |
| 2026-05-14 | Task 12 — strategies (no_coordination + round_robin) | `b984e28` | 37 ✓ | `sim/strategies/no_coordination.py` returns `[]` (every house hoards). `sim/strategies/round_robin.py` shares 5% of each above-mean-SoC islanded house's above-floor headroom with its below-mean spatial neighbors. Both implement the `decide_transfers` signature the engine will plug into in Task 16. |
| 2026-05-14 | Task 11 — Scenario config | `c05ee3a` | 35 ✓ | `sim/scenario.py` with `OutageWindow` + `Scenario` dataclasses and `load_scenario(path)` YAML reader. `Scenario.timesteps()` iterates the simulation clock; `grid_status_at(t, house_id)` checks the outage schedule. Ships `configs/scenarios/synthetic_smoke.yaml` (24 h, no outage, no_coordination) and `configs/scenarios/24h_uniform.yaml` (24 h, full neighborhood outage from 08:00, round_robin). Also adds the "continuous execution" workflow preference. |
| 2026-05-14 | Task 10 — bus saturation + no-wheeling | `87891c2` | 30 ✓ | Adds no-wheeling filter (sender's grid status != receiver's grid status → reject + `NO_WHEELING_REJECTED` event) and bus-saturation scaling (total gross out > `bus_max_kw` → scale all flows proportionally + `BUS_SATURATED` event). Network module fully done for Phase 1. |
| 2026-05-14 | Task 9 — sender/receiver cap clipping | `a82dbd1` | 26 ✓ | Two-stage clipping in `settle_transfers`: senders that requested more than their cap have outgoing transfers scaled proportionally (`SENDER_DOD_FLOOR` event); receivers whose total inbound exceeds their cap force a back-scale on the sender side (`RECEIVER_FULL` event). Includes workflow-preferences and project-skills sections added to this CLAUDE.md per user request. |
| 2026-05-14 | Task 8 — settle_transfers happy path | `3508a1b` | 23 ✓ | Adds `EventKind` (StrEnum), `Event`, `SettlementResult` to `sim/types.py`. Minimal `settle_transfers`: receiver gets `kw × (1 - bus_loss_factor)`; emits `TRANSFER_EXECUTED` event. Sender/receiver caps accepted but ignored — Task 9 wires them in. Ruff caught a `class EventKind(str, Enum)` pattern; switched to `StrEnum` (Python 3.11+). |
| 2026-05-14 | Task 7 — Neighborhood + comm graph | `a5a0226` | 22 ✓ | `Neighborhood` dataclass + `build_grid_neighborhood(rows, cols)` — 5×6 grid, 4-neighbor comm graph (corners 2, edges 3, interior 4). Network structure only; settle_transfers lands in Tasks 8-10. |
| 2026-05-14 | Task 6 — data layer + SyntheticAdapter | `d9c489e` | 17 ✓ | `LoadProfile`/`SolarProfile` protocols + `SyntheticSolar` (half-sine 6 AM–6 PM) + `SyntheticLoad` (constant). Real Pecan Street + NREL adapters deferred to Tasks 21-22. |
| 2026-05-14 | Task 5 — net export + grid coupling | `9aea280` | 11 ✓ | Wires up `desired_net_export_kw` and `grid_status`. Adds `grid_import_kwh`, `grid_export_kwh`, `achieved_net_export_kw` fields. Household physics now complete for Phase 1. |
| 2026-05-14 | Infrastructure: CI + pre-commit + permissions + skills | `32757b0` | 8 ✓ | GitHub Actions CI workflow, ruff/mypy pre-commit hooks, `.claude/settings.json` allowlist, and four new skills: `/advisormeeting`, `/sweep`, `/explainphysics` (plus `/nextask` + `/simtest` from earlier today). |
| 2026-05-14 | Task 4 — RT efficiency | `b34c754` | 8 ✓ | sqrt(eta) on each leg; full cycle returns eta*input. Ruff RUF002 caught a Unicode `×` in a docstring; replaced with `*`. |
| 2026-05-14 | Task 3 — rate clamps + SoC bounds | `6b4ec72` | 6 ✓ | Added `wasted_kwh` / `unmet_kwh` accounting. |
| 2026-05-14 | Task 2 — household basics | `0d71941` | 2 ✓ | Minimal `step()` with no constraints. |
| 2026-05-14 | Task 1 — shared types | `261e830` | 5 ✓ | `Transfer` + `HouseholdProfile`. |
| 2026-05-14 | Task 0 — scaffold | `76b013d` | 0 ✓ | pyproject.toml + venv + pytest/ruff/mypy. Used built-in `python3 -m venv` (no `uv` installed). |
| 2026-05-14 | Initial commit | `f0169f4` | — | Spec + plan + CLAUDE.md + LICENSE. |

## Locked Phase 1 design decisions

These are decisions you should NOT re-litigate without explicit user re-approval:

- **Physics:** energy model + basic constraints (battery rate, RT efficiency 0.9, DoD floor 0.1, bus transit loss 0.05). No AC power flow.
- **Temporal:** 15-min ticks for both physics and decisions in v1. Architecture supports evolving to 5-min physics / 15-min decisions in Phase 2.
- **Neighborhood:** 30 households on a 5×6 grid. 4-neighbor communication graph + shared physical bus (50 kW default). Configurable.
- **Data:** NREL ResStock primary (advisor confirmed 2026-05-26 — public reproducibility is a paper strength; Pecan Street dropped, can't get HS-student affiliation) + NREL NSRDB for solar irradiance. Adapter pattern in `sim/adapters/`. **Phase 1.6 adds 1-2 more public datasets** for cross-dataset robustness (another ResStock state, NREL ComStock, or EULP).
- **Outage model:** schedule of `(start, end, affected_houses)` tuples. Partial-island supported but **no wheeling** (grid-connected houses can't pass grid energy through the bus to islanded neighbors).
- **Coordination plug-point:** `decide_transfers(t, states, households, solar, load, grid, neighborhood, dt_hours) -> list[Transfer]`. Phase 2 LLM agents plug in here without modifying the simulator core.
- **Output:** state.jsonl + events.jsonl + summary.json under `runs/<scenario_id>/<timestamp>/`. `messages.jsonl` reserved for Phase 2.

## Locked Phase 1.6 design decisions (advisor 2026-05-26)

These are advisor-mandated and gate Phase 2. Do NOT skip or re-scope without re-approval.

- **Communication graph — ownership/management overlays.** 4-neighbor geographic adjacency is insufficient on its own. Add cross-cutting edges that follow real coordination relationships: single owner of multiple properties, property-management companies, HOAs, demand-response aggregators. Agents end up in multiple *partially overlapping trust circles* (geographic neighbors, same owner, same manager). This is the structure where natural-language negotiation should outperform fixed protocols — it's the core research setting, not a nice-to-have.
- **Stress scenarios that break round-robin.** Current 12h-July-overnight (98.5% no-coord ceiling) is too forgiving. Build scenarios where round-robin leaves *substantial* unmet demand and unequal welfare. Directions: 24-72h or repeated outages with no recovery window, winter morning peak with low solar, heterogeneous "have" vs "have-not" battery/solar capacity, heatwave + AC load. Target a regime with meaningful unmet kWh and Gini well above zero after round-robin.
- **Centralized LP upper-bound baseline.** Add a centralized linear-program allocator with full information as a third strategy. It defines the achievable ceiling. Reframe all results as **"LLM coordination closes X% of the gap between round-robin and LP-optimal"** rather than "beats round-robin by Y%".
- **Welfare measure:** served-load fraction confirmed fine for Phase 1; needs-weighting (medical loads, thermal comfort thresholds) in Phase 3 confirmed as the right trajectory.

## Locked Phase 2 design decisions (advisor 2026-05-26)

- **Failure modes the LLM layer must be tested against** (advisor's top three):
  1. *Strategic / selfish agents* — some agents misreport state or refuse to share. Does language-based negotiation surface and route around defectors better than a fixed protocol?
  2. *Noisy / faulty observations* — imperfect knowledge of own SoC or load forecast. Memory + reflection should help in ways a rule-based protocol can't.
  3. *Communication constraints* — limited message budget, partial link failures. Agents must reason about which trust circle to route through (ties back to the ownership/management overlays).
- **Park et al., "Generative Agents" (arXiv:2304.03442):** advisor-recommended. Decision: do NOT fork the codebase (their world is a 2D social town, fundamentally different from a physics-based microgrid). Treat as a Phase 2 reference for agent architecture patterns (memory stream, reflection, natural-language messaging) which we reimplement adapted to microgrid coordination and cite prominently.

## User context

- High school student, comfortable with Python, new to power systems / energy / multi-agent systems.
- Working on this as a research project under mentor/advisor guidance. Advisor framing is in the kickoff message in session history. No fixed deadline — summer + potentially next school year.
- Capable and engaged — don't be condescending, but do explain power-systems terminology when it first comes up (DoD, RT efficiency, distribution bus, etc.). Don't black-box the work via subagents; the student is here to learn the material.

## Workflow preferences (durable)

These are the user's explicit preferences for how Claude should operate on this project. They override default Claude Code behavior where they conflict.

- **Inline execution, not subagent-driven.** Tasks are executed in the active session, batched ~3-5 at a time with check-ins between. The student wants to see the work happen and learn the material, not have it produced by a fresh agent each time.
- **No `Co-Authored-By: Claude` trailer in commits.** All commits attributed solely to the user.
- **Update `CLAUDE.md` progress log after every completed task**, in the *same* commit as the task's code changes — never a separate "docs" commit.
- **After completing each task, preview the next one** — end the response with a 1-2 sentence summary of what's coming next.
- **Continuous execution: do NOT pause between tasks to ask "want me to continue?"** — just keep going. Stop only on real blockers: ambiguous spec, failing test you can't fix, decision the user hasn't authorized, or anything affecting the public surface area of the repo. The user explicitly opted into "fire-and-forget" execution on 2026-05-14.
- **Verify CI-equivalently before committing.** Local `pytest` against the long-lived venv is necessary but not sufficient — the local venv masks packaging bugs that fail on `pip install -e .` from scratch. On 2026-05-14 four commits (Tasks 11-14) shipped with red CI because `configs/` broke setuptools auto-discovery and my local venv had been installed before `configs/` existed. **The rule:** for any change touching `pyproject.toml`, `.github/workflows/`, `.pre-commit-config.yaml`, or any new top-level directory / package root, run a clean-install dry-run in `/tmp/microgrid_ci_check` (recipe in `~/.claude/projects/.../memory/feedback_microgrid_verify_before_commit.md`). After every push, glance at `gh run list --limit 1`. Don't let a red streak develop — fix before shipping the next task.
- **Mark plan checkboxes as `- [x]` after each task**, in the same commit. The plan file is the source of truth for what's done; `/nextask` reads the first `- [ ]`.
- **Public GitHub repo from day 1.** Repo: github.com/leochang017/microgrid-llm-coordination. MIT licensed.
- **Pre-commit hooks gate every commit.** If a hook reformats files, re-stage and retry — never bypass with `--no-verify`.
- **Explain power-systems jargon when it first appears**, but don't be condescending — the student is capable, just new to the domain.

## Project skills (invoke with `/<name>`)

Project-specific Claude Code skills authored for this project, all at `~/.claude/skills/<name>/SKILL.md`. Available in every session:

- **`/readclaude`** — Load this CLAUDE.md into working context at the start of a session.
- **`/nextask`** — Find the next unchecked step in the plan and report what it will do. Waits for go-ahead.
- **`/simtest`** — Run `pytest + ruff + mypy` and report a one-line summary (or first failure).
- **`/explainphysics`** — Plain-language walkthrough of a `sim/` file with hand-traced numeric examples.
- **`/advisormeeting`** — Draft a 2-paragraph status update for an advisor meeting using the progress log + git history.
- **`/sweep`** — (Phase 3) Run scenarios × strategies × seeds and tabulate summary metrics.

## Conventions (Phase 1)

- Python 3.12, `uv` for env, `pytest`, `ruff`, `mypy --strict` on `sim/`.
- **TDD always.** Every task: write failing test → run it red → minimal impl → run green → commit. Do not skip the red step.
- **Conventional commits** (`feat:`, `test:`, `chore:`, `docs:`).
- **No global state** in `sim/`. Engine owns the RNG. Pass it explicitly.
- **Pure functions** in `household.py` and `network.py`. The engine is the only stateful glue.
- **Determinism is mandatory.** Two runs of the same scenario YAML must produce byte-identical state logs.
- **Strict-mode invariants** (SoC bounds, non-negative wasted/unmet) asserted every tick. Disabled only via `--no-strict` for hacking.

## Critical files

| Path | Purpose |
|------|---------|
| `docs/superpowers/specs/2026-05-14-phase1-simulator-design.md` | Phase 1 design spec (authoritative) |
| `docs/superpowers/plans/2026-05-14-phase1-simulator.md` | Phase 1 implementation plan (TDD task list) |
| `CLAUDE.md` | This file |
| `sim/` | Simulator package (Phase 1 build target) |
| `tests/` | Test suite |
| `configs/scenarios/` | Scenario YAML files |
| `runs/` | Output directory (gitignored) |
| `data/` | Cached raw data (gitignored, see Task 24) |

## Data access

- **NREL NSRDB:** free API key at https://developer.nrel.gov/signup/. Env vars: `NREL_API_KEY`, `NREL_EMAIL`.
- **Pecan Street Dataport:** requires researcher account at https://www.pecanstreet.org/dataport/. **Apply on day 1**; approval can take days to weeks. Until approved, develop against synthetic adapters + CSV fixtures (Task 21 ships those).

## Important warnings (from advisor)

- Do NOT claim the system is ready for real deployment. It isn't, nobody's is.
- Be careful with the equity framing. Read Sovacool's energy-justice work before writing the fairness section.
- The LLM-agents-lie failure mode is interesting; study it but do NOT oversell as an adversarial security contribution.
- Open-source release planned alongside the paper. GitHub repo is **private until paper draft is solid**.

## What to do at the start of a new session

1. Read this file (`/readclaude` does this for you).
2. Read the current phase's spec.
3. Read the current phase's plan.
4. `git status` + `git log -10` to see where execution left off.
5. Find the first unchecked `- [ ]` step in the plan and proceed.
