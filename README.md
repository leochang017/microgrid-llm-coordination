# Microgrid LLM Coordination

A research project asking: can a population of LLM agents — one per household — negotiate peer-to-peer to allocate scarce energy during a grid outage in a way that is **fair across heterogeneous households**, **robust to incomplete or incorrect information**, and **explainable to residents**?

The contribution is on the CS/ML axis (natural-language coordination, robustness, explainability), not power systems. Classical optimization handles fairness under strong assumptions, struggles with robustness, and doesn't attempt explainability. That gap is what this project explores.

**Status:** Phases 1–2.9 complete; Phase 3 infrastructure + pre-live hardening complete; live runs complete; **Phase 3.3 analysis & results complete** (`phase3.3-complete`, 2026-07-16); **all Phase 3.2 playbook stages done, including the optional Stage 3 Sonnet capability ablation (2026-07-18) and Stage 4 live explanation judging (2026-07-17)**. Run `pytest` for the current test count (364 as of 2026-07-19); ruff + mypy --strict (sim/ + scripts/) clean. **Headline: live Haiku beats the zero-LLM control on 3/3 seeds (+5.8 ± 1.0 pts, closing 29% of the control→LP gap)** — the first replicated evidence the LLM layer adds coordination value; failure-cell probes then show it retains 89% of that value under 33.6% defection and tolerates observation noise, while a bandwidth-constrained comm cell is the one regime with a residual net loss vs the control (−0.86 pts after a 2026-07-19 re-run fixing two commitment-integrity bugs that had inflated the original −4.6). **Capability ablation: swapping Haiku for Sonnet on the clean cell ties (0.6685 vs 0.6726) — model capability does not move clean-cell coordination quality; the LLM advantage is about scenario difficulty, not raw reasoning power.** **Explanation judging (Sonnet judge, ≠ author family): rationales score 3.03/4.05/4.46 (state_accuracy/actionability/consistency) on the clean cell, 3.00/3.97/4.52 on defectors — actionable and consistent, self-reported state figures are the weakest axis.** The results story with real numbers is in [`docs/phase3_results.md`](docs/phase3_results.md); every figure + table regenerates from committed artifacts with `python -m scripts.figures --all` ($0, no API calls). Next: Phase 4 (paper + demo). Deferred, not scheduled: VT/AZ cross-climate cells.

📐 [Phase 1 spec](docs/superpowers/archive/specs/2026-05-14-phase1-simulator-design.md) · [Phase 1.6 spec](docs/superpowers/archive/specs/2026-05-29-phase1.6-hardening-design.md) · [Phase 2 spec](docs/superpowers/archive/specs/2026-06-13-phase2-llm-agent-design.md) · [Phase 3 spec](docs/superpowers/archive/specs/2026-07-07-phase3-benchmark-design.md) · [Phase 3.1 spec](docs/superpowers/archive/specs/2026-07-12-phase3.1-prelive-hardening.md) · 📋 [Phase 1 plan](docs/superpowers/archive/plans/2026-05-14-phase1-simulator.md) · [Phase 1.6 plan](docs/superpowers/archive/plans/2026-05-29-phase1.6-hardening.md) · [Phase 2 plan](docs/superpowers/archive/plans/2026-06-13-phase2-llm-agent.md) · 🧠 [Project context (CLAUDE.md)](CLAUDE.md)

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,data]"
```

Requires Python ≥ 3.12.

## Run a scenario

```bash
python -m scripts.run --scenario configs/scenarios/24h_uniform.yaml
```

Output goes to `runs/<scenario_id>/<strategy>/<timestamp>-<pid>/`:

| File           | Contents                                                    |
|----------------|-------------------------------------------------------------|
| `config.json`  | Resolved scenario config (seed, sampling, outages, …)       |
| `state.jsonl`  | One row per (house, tick): SoC, solar, load, grid status…   |
| `events.jsonl` | Discrete events: outage start/end, transfers, clip reasons  |
| `summary.json` | Top-level metrics: served fraction, Gini, wasted, unmet     |
| `messages.jsonl` | Every message decision (llm_agent / llm_fallback runs): delivered, dropped+reason, pending_at_end |

Add `--no-strict` to disable the SoC-bound assertions while hacking on physics.

## Run the tests

```bash
pytest                  # full suite; see CI badge/logs for the current count
ruff check sim tests scripts
mypy
```

CI on every push runs all three.

## Scenario YAML reference

```yaml
scenario_id: example
start: "2024-07-01T00:00:00"   # ISO datetime
end:   "2024-07-02T00:00:00"
dt_hours: 0.25                  # 15 min
seed: 42
rows: 5
cols: 6                         # 30 houses on a 5x6 grid
bus_max_kw: 50.0                # neighborhood transformer cap
bus_loss_factor: 0.05           # 5% transit loss
strategy: round_robin           # name of file under sim/strategies/
data_source: synthetic          # real-data adapters live in sim/adapters/ (NREL NSRDB solar, ResStock loads, Pecan Street)
household_sampling:
  pv_kw_peak: [4.0, 12.0]       # uniform sample range (kW)
  battery_kwh: [10.0, 27.0]     # uniform sample range (kWh)
  rt_efficiency: 0.9            # round-trip battery efficiency
  dod_floor_frac: 0.1           # don't drain below this fraction of capacity
  grid_max_kw: 10.0             # per-house grid connection cap
outages:
  - start: "2024-07-01T08:00:00"
    end:   "2024-07-02T00:00:00"
    affected_houses: ["r0c0", "r0c1", …]
```

## Architecture

```
sim/            engine.py · household.py · network.py · scenario.py · logging.py · overrides.py · data.py · types.py
sim/agents/     agent.py · policy.py · memory.py · protocol.py · cache.py · llm.py · failure_modes.py · seeding.py
sim/adapters/   nrel_solar.py · resstock.py · pecan_street.py
sim/strategies/ no_coordination.py · round_robin.py · round_robin_overlay.py · lp_optimal.py · llm_agent.py · llm_fallback.py
scripts/        run.py · compare.py · sweep.py · eval_explanations.py · fetch_data.py
```

The **coordination strategy is an injected callback** — `decide_transfers(t, states, households, solar, load, grid, neighborhood, dt) -> list[Transfer]`. Phase 2 added `sim/strategies/llm_agent.py` (the LLM strategy facade) and Phase 2.9 added `llm_fallback.py` (the zero-LLM control).

## Phase 1 status

- [x] Project scaffold, types, household physics (rate clamps, RT efficiency, DoD floor, grid coupling)
- [x] Data layer + synthetic adapters
- [x] Neighborhood + comm graph + settle_transfers (bus saturation, no-wheeling, sender/receiver clipping)
- [x] Scenario YAML + three example scenarios (`synthetic_smoke`, `24h_uniform`, `24h_real`)
- [x] Baseline strategies (no_coordination, round_robin)
- [x] Engine main loop + JSONL logger + Gini/served-fraction summary
- [x] CLI runner + `scripts/fetch_data.py` (NREL NSRDB downloader)
- [x] Integration test (round_robin beats no_coordination on Gini) + physics smoke test + determinism check
- [x] Real data adapters (Pecan Street + NREL NSRDB), engine dispatches on `data_source`

**Phase 1 complete.**

## Phase 1.6 — pre-Phase-2 hardening

Advisor-gated work establishing that the Phase 2 LLM layer has real room to add value:

- **Communication-graph overlays.** Beyond the geographic 4-neighbor graph, scenarios
  declare ownership/management *trust circles* (single-owner portfolios, HOAs,
  demand-response aggregators, …). Each affiliation group becomes a clique layer; a house
  can sit in several overlapping circles. Declared in the scenario YAML:

  ```yaml
  affiliations:
    owner:
      owner_a: [r0c0, r2c3, r4c5]   # one owner, three scattered properties
    hoa:
      hoa_top: [r0c0, r0c1, r0c2]
    dr_aggregator:
      agg_gridflex: [r0c0, r1c1, r2c2, r3c3, r4c4]
  ```

- **Four strategies.** `no_coordination` (hoard) · `round_robin` (share with geographic
  neighbors) · `round_robin_overlay` (share across the overlay union) · `lp_optimal`
  (centralized full-horizon LP, the served-load **ceiling**).

- **Stress scenarios** where simple sharing visibly breaks: `haves_havenots.yaml`
  (bimodal capacity, 12 h outage) and `long_outage_72h.yaml`. The `winter_morning_lowsolar`
  and `heatwave_ac` scenarios need real cold/hot-climate ResStock data — fetch with:

  ```bash
  python -m scripts.fetch_data resstock --state VT -n 30 --out-dir data/resstock_vt/
  python -m scripts.fetch_data nrel --lat 44.26 --lon -72.58 --year 2018 --out data/nrel_solar/vermont_2018.csv
  python -m scripts.fetch_data resstock --state AZ -n 30 --out-dir data/resstock_az/
  python -m scripts.fetch_data nrel --lat 33.45 --lon -112.07 --year 2018 --out data/nrel_solar/phoenix_2018.csv
  ```

- **Gap-closed comparison.** `python -m scripts.compare --scenario <yaml>` runs the
  heuristics through the engine, takes the LP objective as the ceiling, and tabulates
  `gap_closed = (served − round_robin) / (lp_optimal − round_robin)`. On `haves_havenots`:

  | strategy | served | unmet_kwh | gini | gap_closed |
  |---|---|---|---|---|
  | no_coordination | 0.4560 | 195.8 | 0.4851 | -639.62% |
  | round_robin | 0.5194 | 173.0 | 0.2244 | 0.00% |
  | round_robin_overlay | 0.5194 | 173.0 | 0.2217 | 0.00% |
  | lp_optimal | 0.5294 | 169.4 | 0.3617 | 100.00% |

  *gap_closed is unclamped (P2.9 T12): negative = below the round_robin baseline.*

  *(Numbers re-derived 2026-07-06 after the Phase 2.9 energy-conservation fix — the
  old round_robin figure of 0.5250 included ~0.56 points of phantom energy from a
  sender-cap bug. The honest round_robin→LP gap is now 1.0 point, not 0.44.)*

  Note the served-maximizing LP optimum is *less* equitable (gini ≈0.36; solver-version-dependent under degenerate optima) than round_robin
  (0.224) — the fairness tension Phase 3's needs-weighted welfare model will address.

> The LP ceiling is the LP **objective** (`lp_optimal.optimal_metrics`), not an
> engine-realized run: the engine's greedy per-tick dispatch wouldn't faithfully execute
> the LP's planned battery schedule, so a realized LP run can fall below round_robin.

## Phase 2 — LLM Agent Layer (2026-06-13)

Per-household LLM agents that negotiate transfers in natural language across
overlapping trust circles (geographic + ownership/management overlays from Phase 1.6).
Each agent maintains a Park-adapted memory stream + periodic reflection, emits a
structured `Policy` YAML that a pure-Python tick executor consumes, and exchanges
speech-act messages (`REQUEST` / `OFFER` / `ACCEPT` / `REJECT` / `COUNTER` / `INFORM`)
with an NL `rationale` field on every message.

Three orthogonal failure-mode injection axes are independently configurable per
scenario YAML: strategic agents (`defector_fraction`), noisy observations
(`obs_noise.{soc,load,solar}_std_frac`), and communication constraints
(`comm.{drop_prob_by_circle, per_tick_budget}`).

Determinism is preserved via a content-addressed prompt cache. The in-repo
`reference_runs/` directory ships one cache-warmed run you can replay without
hitting the API:

| Scenario | Failure cell | Notes |
|---|---|---|
| `haves_havenots__llm.yaml` | clean | live Haiku 4.5 run (Phase 2.8 architecture, **pre-conservation-fix physics**); served 0.513 vs round_robin-at-the-time 0.525. Post-fix round_robin is 0.5194; a live re-run under corrected physics is a Phase 3 deliverable. |

**Phase 2.8 (2026-06-17, tag `phase2.8-complete`):** added a peer-state summary to every
plan prompt and made the per-tick share fraction LLM-controlled. The live re-run left every
macro metric unchanged (served 0.513, gini 0.399, transfers 259) while message traffic rose
66% — the clean cell has hit this architecture's ceiling ~1.2 points behind round_robin.
The Phase 3 hypothesis is therefore that the LLM advantage, if any, lives in the
failure-mode cells (defectors / noise / comm), which so far have only mock-LLM coverage.

### Replaying the Phase 2.8 reference run (historical — pinned to its tag)

The shipped reference cache was recorded under Phase 2.8 prompts. At HEAD the
prompts differ, so this replay MISSES the cache and either crashes (no key) or
silently spends money — and it truncates the git-tracked reference artifacts
first. Replay only at the matching tag:

    git checkout phase2.9-complete
    python -m scripts.run --scenario configs/scenarios/haves_havenots__llm.yaml --reference-cell clean

Fresh Phase 3 reference cells ship with the live runs — see
`docs/superpowers/archive/plans/2026-07-12-phase3.2-live-runs.md`.

To run live, follow the Phase 3.2 playbook (`docs/superpowers/archive/plans/2026-07-12-phase3.2-live-runs.md`) — it covers credentials, crash-resume, per-cell commands, and budget.

### Phase 2 known limitations

- **Live Haiku reached 0.513 on `haves_havenots__llm`** (Phase 2.7/2.8
  architecture), 1.2 points behind the round_robin figure of the time (0.525).
  Phase 2v0 was 0.460 (6.5-pt gap); the Phase 2.7 fixes closed 80% of that
  deficit and Gini improved from 0.48 to 0.40. **Caveat (2026-07-06):** both
  numbers predate the Phase 2.9 energy-conservation fix; post-fix round_robin
  is 0.5194, and the LLM cell needs a live re-run under corrected physics
  before any comparison is quoted in the paper (Phase 3 deliverable).
- **`defector_realization: prompt`** is now wired in Phase 2.5 (selfish system
  prompt for plan + react calls when an agent is a defector). The `wrapper`
  realization (per-message payload mutation at the bus) remains the safer
  default for unbiased measurement.
- **Peer state observed by an agent is the engine's ground-truth state**, not
  the peer's voluntarily-INFORM'd self-view. Migrating to message-only peer
  state is a v1 follow-up.
- **No synchronous multi-round negotiation in v0** — agents reply reactively to
  REQUEST/OFFER across consecutive ticks.
- **Defectors and noise + comm failure-cell reference runs are deferred follow-ups.**
  Mock-LLM tests cover them in `tests/test_llm_agent_failure_axes.py`; live
  reference runs ship in a future phase.
- **Not deployment-ready.** Research artifact only.


## Phase 2.9 — Correctness hardening (2026-07-07)

A full-repo adversarial review (65 verified findings) triggered an 18-task hardening pass
before Phase 3. Everything below is TDD'd; the suite grew 188 → 243 tests.

**Physics fixes that changed shipped numbers:**

- **Energy conservation.** The engine's sender caps ignored the sender's own load, so
  settlement could credit receivers energy that was never sourced. Round-robin's entire
  "30 kWh saving" on `overnight_outage_hard` was phantom (post-fix: rr == no_coord
  exactly, while the LP ceiling shows 73.8 kWh of real headroom the 5%-share heuristic
  can't reach). Showcase round_robin: 0.5250 → **0.5194**; the honest rr→LP gap is
  **1.0 point**, not 0.44. Strict mode now asserts `achieved == desired` export per tick.
- **Receiver caps are load-aware** (DC bypass): a full-battery house with unmet load can
  now receive, matching `step()` physics.
- **Real-data solar was shifted ~+6 h** (NSRDB fetched in UTC, consumed as local time).
  Corrected `24h_resstock_outage` numbers: no_coord **0.8425** / round_robin **0.8582**
  (a real 21.4 kWh saving, previously overstated as 35.7) / LP ceiling **0.9111** —
  a genuine 5.3-point coordination gap on real data. `NRELSolar` now validates that
  solar noon lands at local noon and refuses UTC-shaped files; ResStock loads use the
  data's native 15-min interval and period-ending timestamps are realigned.
- **LP hardening:** curtailment slack (no more infeasibility crashes on solar-rich
  islanded ticks) + engine-feasibility send/recv bounds; showcase ceiling unchanged
  (0.529368, regression-pinned).

**The zero-LLM control (new `llm_fallback` strategy, $0 to run):** identical llm_agent
machinery with the LLM disabled scores **0.518** on the showcase clean cell — within
0.15 points of round_robin and above the Phase 2.8 live Haiku run (0.513, old physics).
The hand-tuned executor, not LLM reasoning, currently accounts for clean-cell
performance; every Phase 3 comparison must beat this control. A `llm: messaging: off`
ablation flag isolates whether NL messaging causally affects allocations.

**Tooling for Phase 3:** `run.py --seed`, `compare.py --seeds a,b,c` (per-seed tables +
paired aggregate; cross-seed spread on this scenario family is ~20 points, dwarfing
single-seed differences), unclamped gap_closed (negative = worse than round_robin;
n/a = no headroom), real `llm_cost_usd_estimated` from fresh-call tokens,
`failure_modes_active` recorded in every summary, react-queue aging (19.5% of
negotiation messages were being silently destroyed by a queue-clobber bug), and
golden-number regression pins for every showcase metric.

Deferred (tracked in the Phase 2.9 spec): INFORM-only peer state + binding negotiation
(prerequisite for valid failure-cell experiments), needs-weighted welfare, the
explainability instrument, live re-runs under corrected physics.



## Phase 3 — Benchmark & Experiments (complete)

Benchmark infrastructure, live LLM runs, and analysis are all complete (tags `phase3-infra-complete` → `phase3.3-complete`); the results story is in [`docs/phase3_results.md`](docs/phase3_results.md).

**Information-flow rework (the validity gate).** Agents no longer see engine ground
truth about peers. All peer knowledge is message-borne: every agent broadcasts its
*noised* self-view via INFORM each tick, and routing decisions run on the resulting
`peer_beliefs` (possibly stale, corrupted, or missing — unknown peers are ineligible
recipients). `act()` decides on the agent's own noised view too, while the engine
settles against physical truth. Consequences, all test-enforced:

- the three failure axes finally *cause* outcome changes (noise perturbs beliefs →
  routing; defector INFORM corruption lands on consumers; comm drops destroy the
  knowledge sharing depends on);
- `llm: messaging: off` now collapses transfers to zero — communication causally
  matters (pre-Phase-3 it changed nothing, proving messages were decorative);
- negotiation is **binding**: REQUESTs carry the genuine estimated shortfall, and an
  `ACCEPT <kwh>` / `COUNTER <kwh>` reply creates a commitment ledger entry that
  `act()` serves ahead of discretionary sharing (TTL 2 ticks).

**The solar showcase (`haves_havenots_solar.yaml`).** PV on the haves over a 24 h
outage makes energy abundant but *misplaced* — the coordination-bound regime:

| strategy | served | note |
|---|---|---|
| no_coordination | 0.4280 | hoarding collapses overnight |
| llm_fallback (zero-LLM control) | 0.6269 | tuned executor, no LLM — the bar any LLM run must beat (live `__llm` cell, seed 23) |
| round_robin | 0.7666 | myopic sharing strands midday solar |
| lp_optimal (ceiling) | 0.9711 | pre-positions solar into have-not batteries |

A 20.4-point rr→LP gap (20× the old showcase) and an unsaturated control with 34
points of headroom above it.

**Fairness + explainability substrate.** `critical_load_frac` sampling with
served-critical accounting (unmet hits flexible load first), Rawlsian floor
(`min_house_served_fraction`), Jain's index; message rationales carry
`templated: true/false` provenance and `scripts/eval_explanations.py` scores
LLM-authored explanations 1-5 on state-accuracy / actionability / consistency
against the sender's logged state (LLM-judge method advisor-approved
2026-07-15; live judging complete — see `docs/phase3_tables.md`).

**Machinery.** `run.py --set dotted.key=value` overrides (typos hard-fail),
`scripts/sweep.py` dose-response grids (subprocess-per-cell), and process-stable
RNG seeding (`sim/agents/seeding.py` — the old `hash()`-based seeds were silently
PYTHONHASHSEED-dependent across processes).

**Mock dose-response matrix** (fixed canned policies — the floor for live-LLM
comparisons; round_robin's flat rows demonstrate rule-based baselines are
structurally immune to information-quality failures): see
`docs/phase3_mock_sweep.md`.

**Budget-gated work (spec Part E) — done:** live clean-cell + failure-cell runs
under the new architecture, the Sonnet capability ablation (ties Haiku, see
status line above), and live explanation judging are all complete. Deferred,
not scheduled: VT/AZ data for winter/heatwave cross-climate scenarios.

## License

MIT — see [LICENSE](LICENSE).
