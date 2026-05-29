# Microgrid LLM Coordination

A research project asking: can a population of LLM agents — one per household — negotiate peer-to-peer to allocate scarce energy during a grid outage in a way that is **fair across heterogeneous households**, **robust to incomplete or incorrect information**, and **explainable to residents**?

The contribution is on the CS/ML axis (natural-language coordination, robustness, explainability), not power systems. Classical optimization handles fairness under strong assumptions, struggles with robustness, and doesn't attempt explainability. That gap is what this project explores.

**Status:** Phase 1 simulator + Phase 1.6 hardening — ✅ **complete.** 96 tests pass. CLI works end-to-end.

📐 [Phase 1 spec](docs/superpowers/specs/2026-05-14-phase1-simulator-design.md) · [Phase 1.6 spec](docs/superpowers/specs/2026-05-29-phase1.6-hardening-design.md) · 📋 [Phase 1 plan](docs/superpowers/plans/2026-05-14-phase1-simulator.md) · [Phase 1.6 plan](docs/superpowers/plans/2026-05-29-phase1.6-hardening.md) · 🧠 [Project context (CLAUDE.md)](CLAUDE.md)

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

Output goes to `runs/<scenario_id>/<timestamp>/`:

| File           | Contents                                                    |
|----------------|-------------------------------------------------------------|
| `config.json`  | Resolved scenario config (seed, sampling, outages, …)       |
| `state.jsonl`  | One row per (house, tick): SoC, solar, load, grid status…   |
| `events.jsonl` | Discrete events: outage start/end, transfers, clip reasons  |
| `summary.json` | Top-level metrics: served fraction, Gini, wasted, unmet     |

Add `--no-strict` to disable the SoC-bound assertions while hacking on physics.

## Run the tests

```bash
pytest                  # 54 tests
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
data_source: synthetic          # 'synthetic' in Phase 1; real adapters land in Task 23
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
sim/
├── types.py         Transfer, HouseholdProfile, Event, SettlementResult
├── data.py          LoadProfile/SolarProfile protocols + synthetic adapter
├── household.py     Pure physics: step(h, s, solar, load, …) -> new state
├── network.py       Comm graph + settle_transfers (bus, no-wheeling, caps)
├── scenario.py      YAML config + Scenario / OutageWindow dataclasses
├── engine.py        Main simulation loop (run + sample_households)
├── logging.py       JSONL writers + summary metrics (Gini, served-fraction)
└── strategies/      Pluggable coordination strategies
    ├── no_coordination.py
    └── round_robin.py
```

The **coordination strategy is an injected callback** — `decide_transfers(t, states, households, solar, load, grid, neighborhood, dt) -> list[Transfer]`. Phase 2 will add `sim/strategies/llm_agents.py` without touching the engine.

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
  | no_coordination | 0.4560 | 195.8 | 0.4851 | 0.00% |
  | round_robin | 0.5250 | 171.0 | 0.2416 | 0.00% |
  | round_robin_overlay | 0.5249 | 171.0 | 0.2401 | 0.00% |
  | lp_optimal | 0.5294 | 169.4 | 0.3653 | 100.00% |

  Note the served-maximizing LP optimum is *less* equitable (gini 0.365) than round_robin
  (0.242) — the fairness tension Phase 3's needs-weighted welfare model will address.

> The LP ceiling is the LP **objective** (`lp_optimal.optimal_metrics`), not an
> engine-realized run: the engine's greedy per-tick dispatch wouldn't faithfully execute
> the LP's planned battery schedule, so a realized LP run can fall below round_robin.

**Next:** Phase 2 — LLM agent layer (separate spec + plan, separate brainstorm).

## License

MIT — see [LICENSE](LICENSE).
