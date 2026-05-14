# Phase 1: Microgrid Simulator — Design

**Date:** 2026-05-14
**Status:** Approved, ready for implementation planning
**Owner:** Leo
**Project:** LLM agents for peer-to-peer energy coordination in residential microgrids

## Research context

This document specs **Phase 1** of a four-phase research project. The overall research question (from the advisor's framing): can a population of LLM agents, one per household, negotiate peer-to-peer to allocate scarce energy during a grid outage in a way that is fair across heterogeneous households, robust to incomplete or incorrect information, and explainable to residents?

Phase 1 builds the **physical substrate** the agents will live in: a deterministic, reproducible discrete-time simulator of a 30-household neighborhood with solar + battery + load + an outage-prone grid connection. It contains no agent intelligence. The simulator is the experimental apparatus; later phases plug coordination strategies (including LLM agents) into it.

The four phases (target: 6-8 months total):

1. **Phase 1 — Simulator.** Subject of this spec.
2. **Phase 2 — LLM agent layer.** Each household gets an LLM agent that perceives its own state, communicates with neighbors in natural language, and proposes transfers.
3. **Phase 3 — Benchmark & experiments.** Scenario suite, baselines (centralized-optimal, round-robin, no-coordination), metrics (served-critical-load, Gini fairness, energy wasted, explanation quality).
4. **Phase 4 — Web demo & paper.** Visualization + writeup for ICLR Climate Change workshop / NeurIPS Computational Sustainability / AAMAS applied.

## Phase 1 goals

The simulator must:

1. Produce **physically defensible** per-tick state evolution for 30 heterogeneous households, with battery dynamics, solar generation, residential load, and outage-prone grid connection.
2. Expose a **clean coordination plug-point** (`decide_transfers(state) -> List[Transfer]`) that Phase 2 can swap LLM agents into without modifying the simulator.
3. Emit a **state log + event log + summary** per run that Phase 3 evaluation and Phase 4 visualization both consume.
4. Be **deterministic under a seed** — two runs of the same scenario YAML produce byte-identical state logs.
5. Be **readable**: ~700-900 lines of Python in `sim/`, every line defensible to a reviewer.

Non-goals for Phase 1:
- No LLM agents (Phase 2).
- No baselines beyond "no coordination" and "round-robin" stubs (Phase 3 owns the full baseline suite incl. centralized optimal).
- No web visualization (Phase 4).
- No AC power flow, no voltage/frequency dynamics — energy accounting only.

## Locked design decisions

These were chosen during brainstorming on 2026-05-14. Each decision lists the chosen option and why it beats the alternatives.

### Physics fidelity
**Energy model + basic constraints.** Each household tracks `soc_kwh`, `solar_kw`, `load_kw`. Constraints applied each tick: battery charge/discharge rate limits (kW), round-trip efficiency (90%), DoD floor (10% of capacity, can't drain below), max transfer rate through the neighborhood bus.

Rejected: pure energy-only (too easy to attack as unrealistic); full AC power flow (competes on power-systems turf, the trap the advisor warned about).

### Temporal scale
**15-minute timestep for both physics and decisions in v1.** Scenarios run 24-72 hours. ~96-288 ticks per scenario. Architecture supports evolving to a hybrid (5-min physics, 15-min decisions) in Phase 2 if agent reaction time matters, but v1 keeps both at 15 min.

Rejected: 1-min (too expensive once LLM calls land in Phase 2); hourly (too coarse for realistic battery dynamics).

### Data sources
**Pecan Street primary (Austin TX), NREL ResStock as a robustness check, behind a common adapter.** Solar from NREL NSRDB irradiance, scaled per-household by PV kW peak with a 0.85 derate factor. Data is pre-cached locally; the simulator never hits the network at runtime.

Rejected: Pecan Street only (reviewer concern: "does this generalize?"); ResStock only (synthetic data weaker than measured).

### Neighborhood size and layout
**30 households on a 5×6 spatial grid**, sample size configurable for Phase 3 sweeps.

### Topology
**Spatial communication graph + shared physical bus.** Each agent's "comm neighborhood" is its 4 grid-adjacent houses (3 for edge, 2 for corner). Physical energy moves through a single shared neighborhood bus with a global rate limit (configurable; default ~50 kW) and a 5% transit loss.

Rejected: fully-connected (no structure for agents to negotiate around); spatial routing through intermediate houses (adds a routing solver, ~150 extra lines for no research payoff in Phase 1).

### Household heterogeneity
Each household samples:
- `pv_kw_peak` ∈ [4, 12] kW
- `battery_kwh` ∈ [10, 27] kWh
- `battery_max_rate_kw` ≈ battery_kwh / 5 (typical residential)
- A load profile assigned from the dataset (deterministic mapping by seed)
- A `profile: HouseholdProfile` field carrying a free-text description and structured tags (`has_medical`, `has_infant`, `essential_only`)

Phase 1 stores `profile` but **does not use it in physics**. Phase 2's LLM agents will consume it.

### Outage model
**Outage schedule as a list of `(start_time, end_time, affected_houses)` tuples** loaded from the scenario YAML. When the grid is up for a house, that house can import/export with the macro grid (subject to a connection rate limit). When down, the house is islanded.

Two assumptions baked in:
- When the entire neighborhood is islanded, the neighborhood bus remains operational. This is the whole research premise; flagged as a limitation in the paper.
- In partial-island scenarios (some houses grid-connected, others not), **no wheeling** — connected houses can use grid energy for themselves but cannot pass grid energy through the bus to islanded neighbors.

### Logging
Each run writes to `runs/<scenario_id>/<timestamp>/`:
- `config.json` — fully resolved scenario config (seed, household assignments, all parameters)
- `state.jsonl` — one record per (household, tick): `{house_id, t, soc_kwh, solar_kw, load_kw, grid_status, net_export_kw}`
- `events.jsonl` — discrete events: `outage_started`, `outage_ended`, `transfer_executed`, `bus_saturated`, `sender_dod_floor`, `receiver_full`, `receiver_rate_limited`, `unmet_load`
- `summary.json` — top-level metrics: served-critical-load fraction, Gini coefficient over household welfare, total energy wasted, total transfers, deficits
- `messages.jsonl` — reserved for Phase 2 (empty in Phase 1)

## Architecture

Five modules under `sim/`, with deliberate boundaries:

```
academic/microgrid/
├── sim/
│   ├── __init__.py
│   ├── data.py         # Data adapters — load profiles into a common format
│   ├── household.py    # Household dataclass + battery dynamics (pure)
│   ├── network.py      # Comm graph + shared bus + transfer settlement
│   ├── scenario.py     # Scenario config (YAML → dataclasses)
│   ├── engine.py       # The simulation loop. Owns time + RNG.
│   └── logging.py      # JSONL writers + summary computation
├── configs/scenarios/  # YAML scenario files
├── data/{pecan_street,nrel_solar}/  # Cached raw data (gitignored)
├── runs/               # Output (gitignored)
├── tests/
└── scripts/
    ├── fetch_data.py   # One-time download + cache of Pecan Street + NREL
    └── run.py          # CLI: `python -m scripts.run --scenario configs/scenarios/24h_uniform.yaml`
```

### Module boundaries

- **`data.py`** — pure data layer, knows nothing about simulation. `LoadProfile` and `SolarProfile` protocols expose `.get_kw(t)` and `.horizon()`. Two implementations: `PecanStreetAdapter`, `ResStockAdapter`.
- **`household.py`** — pure physics. `step(h, s, solar_kw, load_kw, desired_net_export_kw, grid_status, dt_hours) -> HouseholdState`. Knows nothing about neighbors. Returns the actually-achieved net export so the network module knows what really moved.
- **`network.py`** — the only module aware of multiple houses. `settle_transfers(requested, states, grid_status) -> SettlementResult` clips requested transfers to physical limits (bus capacity, sender DoD, receiver rate limit, partial-island no-wheeling rule), applies 5% transit loss, returns actual flows + structured rejection reasons for the event log.
- **`scenario.py`** — config dataclasses, no logic.
- **`engine.py`** — owns the clock and the RNG; calls into `network` and `household` each tick; routes events to the logger.

### Phase 2 integration point

`engine.run(scenario, decide_transfers, logger)` takes the coordination strategy as an injected callable:

```python
def decide_transfers(t: datetime, states: dict[str, HouseholdState],
                     solar: dict[str, float], load: dict[str, float],
                     grid: dict[str, bool]) -> list[Transfer]: ...
```

Phase 1 ships two implementations: `strategies.no_coordination` (everyone hoards) and `strategies.round_robin` (a naive fairness baseline). Phase 2 adds `strategies.llm_agents`. Phase 3 adds `strategies.centralized_optimal`. The engine never knows which is plugged in.

## Data flow (one run)

1. **Startup.** Load scenario YAML → `Scenario` dataclass. Seed RNG. Sample 30 households (PV/battery sizes). Lay them out 5×6, build 4-neighbor comm graph. Bind each to a load profile. Bind shared solar profile. Resolve coordination strategy. Open run directory, write `config.json`.
2. **Per tick (15 min, 96-288 total).**
   1. Look up solar(t), load(t) for each house from the data adapters.
   2. Look up grid status per house from the outage schedule.
   3. Call `decide_transfers(t, states, solar, load, grid)`.
   4. Call `network.settle_transfers(...)` → actual flows + clip events.
   5. Call `step_all_households(...)` → new states.
   6. Logger writes per-house state rows and any events.
3. **Finalize.** Logger reads back state log, computes summary metrics, writes `summary.json`. CLI prints one-line summary.

## Invariants

1. **Energy balance per tick per household.** All energy in (solar generated + grid import + received from peers) equals all energy out (load served + grid export + sent to peers + Δsoc_kwh + battery RT loss + transit loss attributed to sender + wasted-curtailment). The implementation-plan phase will pin down the exact accounting formula (in particular: where to charge the 5% transit loss — sender side, receiver side, or split — and where to charge battery RT efficiency). Asserted every tick when `--strict` is on (default for tests and "real" runs). Disabled by `--no-strict` for hacking.
2. **SoC bounds:** `dod_floor × capacity ≤ soc_kwh ≤ capacity`. Hard assertion.
3. **Determinism:** byte-identical state logs across two runs of the same scenario YAML.

## Error handling policy

- **Crash loud (programming errors):** energy-balance violation, SoC out of bounds, unknown household ID in a transfer, negative-or-zero transfer kW, self-transfer, scenario asks for data outside available horizon. All `AssertionError` with full context dump.
- **Log and continue (physical reality):** transfer clipped (bus_saturated, sender_dod_floor, receiver_full, receiver_rate_limited), grid status change (outage_started, outage_ended), load not met (unmet_load).
- **Pecan Street data gaps:** forward-fill up to 1 hour, crash on longer gaps (forces clean data, no silent fudging).
- **Solar interpolation:** NREL data is hourly, we run at 15 min — linear interpolation + small seeded noise term (reproducible).

## Testing strategy

Three layers:

**Unit tests** (`tests/test_household.py`, `test_network.py`, `test_data.py`, `test_scenario.py`): charge-to-full, discharge-to-DoD-floor, RT efficiency end-to-end (X kWh in → 0.9X kWh out), bus saturation with proportional clipping, sender DoD rejection produces correct event, partial-island no-wheeling, Pecan Street gap handling, solar interpolation reproducibility, YAML round-trip with bad outage schedule failing at load.

**Integration tests** (`tests/test_integration.py`):
- No coordination, no outage, sunny day → every house ends with `soc > start`.
- No coordination, 24h outage, uniform houses → some run out, totals match physical limits.
- Round-robin, same outage as above → strictly more even battery distribution than no-coordination on the same seed. (Sanity check that *coordination does anything*.)
- Determinism: two runs of the same YAML produce byte-identical `state.jsonl`.

**Physics smoke test** (runs in CI): 24h run with hand-computable synthetic data (constant solar, constant load, no outage), hand-computed expected end state, assert match within 0.01 kWh. Catches "I refactored the battery model and broke physics" bugs that otherwise are invisible.

**Tooling:** `pytest`, `ruff`, `mypy --strict` on `sim/`.

## References and prior work

- **Park et al., "Generative Agents: Interactive Simulacra of Human Behavior" (arXiv:2304.03442)** — recommended by the advisor as a starting point. Decision: do not fork the codebase; their world model is a 2D social town, fundamentally different from a physics-based microgrid. Treat as a **Phase 2 reference** for agent architecture patterns (memory stream, reflection loop, natural-language inter-agent communication) which we will reimplement adapted to the microgrid domain and cite prominently.

## Out of scope (deferred to later phases)

- LLM agents and natural-language messaging — Phase 2.
- Centralized-optimal baseline (LP solver) — Phase 3.
- Adversarial / lying agent scenarios — Phase 3.
- Heterogeneous-LLM scenarios — Phase 3.
- Welfare function over households (Gini computation uses a placeholder welfare = served-fraction-of-load for Phase 1; Phase 3 adds a needs-weighted welfare model informed by the energy-justice literature).
- Web visualization — Phase 4.

## Risks and open questions

1. **Pecan Street access lag.** Account approval can take days to weeks. **Mitigation:** apply on day 1; develop against synthetic data and ResStock until access lands.
2. **Welfare function timing.** Phase 1's placeholder welfare (served load fraction) is too simple for the final paper. Phase 3 will replace it; Phase 1 just must not lock in a specific welfare shape too early. **Mitigation:** keep welfare computation in `logging.py:finalize()`, not in the physics core.
3. **Bus rate limit value.** Default ~50 kW is a guess. **Mitigation:** Phase 3 sweeps this as a sensitivity parameter.
4. **Solar location.** Austin TX is the default (matches Pecan Street). If the wildfire/California framing is more compelling for the paper, the data layer supports a different NREL location with no code changes.

## Success criteria for Phase 1

Phase 1 is done when:

- `python -m scripts.run --scenario configs/scenarios/24h_uniform.yaml` runs end-to-end on real Pecan Street + NREL data and produces the four output files.
- All unit and integration tests pass.
- The physics smoke test passes.
- Two baselines (`no_coordination`, `round_robin`) plug into the engine and produce sensible, distinguishable results on the same scenario.
- A `README.md` documents data download, scenario YAML format, and how to run.
- The advisor has read `sim/household.py` and `sim/network.py` and agrees the physics is defensible.
