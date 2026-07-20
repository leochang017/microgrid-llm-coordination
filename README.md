# Microgrid LLM Coordination

[![CI](https://github.com/leochang017/microgrid-llm-coordination/actions/workflows/ci.yml/badge.svg)](https://github.com/leochang017/microgrid-llm-coordination/actions/workflows/ci.yml)

Can a population of LLM agents — one per household — negotiate peer-to-peer to allocate scarce energy during a grid outage in a way that is **fair across heterogeneous households**, **robust to incomplete or incorrect information**, and **explainable to residents**?

This repo contains a deterministic microgrid simulator, a natural-language negotiation layer (one Claude agent per household), a benchmark of baselines and failure modes, and a web demo that replays the live experiments in the browser. The contribution is on the CS/ML axis (natural-language coordination, robustness, explainability), not power systems: classical optimization handles fairness under strong assumptions, struggles with robustness, and doesn't attempt explainability. That gap is what this project explores.

**Live demo:** <https://microgrid-llm-coordination.vercel.app/> · **Full results:** [`docs/phase3_results.md`](docs/phase3_results.md)

## Key results

30 households (9 with rooftop solar + large batteries, 21 without) ride out a 24-hour grid outage on a shared neighborhood bus. Every LLM run is compared against a **zero-LLM control** — the identical agent machinery with the language model replaced by a fixed policy — and against a centralized linear-program (LP) ceiling with perfect information.

- **The LLM layer adds real coordination value.** Live Haiku agents beat the zero-LLM control on 3/3 seeds: **+5.8 ± 1.0 points of served load, closing 29% ± 3 of the control→LP gap.**
- **Fairness improves alongside efficiency, not against it.** Gini and Jain's index both improve together with served load on every seed — no efficiency–equity tradeoff appears in this regime.
- **Robust to selfish agents.** With 6 of 30 households prompted to hoard and decline requests (33.6% of generation withheld), coordination retains **89% of its clean-cell value** and still beats its same-seed control.
- **Tolerates noisy sensors.** Under dual-channel observation noise (SoC ±10%, load ±15%), the ordering holds; the margin over the control narrows from +4.6 to +0.9 points.
- **Honestly loses under message scarcity.** With per-sender message budgets and lossy links, the negotiation's own bandwidth cost exceeds its value: **−0.9 points vs the control.** Negotiation traffic displaces the state broadcasts sharing depends on.
- **Model capability is not the bottleneck.** Swapping Haiku for Sonnet on the clean cell is a statistical tie (0.6685 vs 0.6726) — the advantage comes from where coordination is hard, not raw reasoning power.
- **Explanations are judged, not asserted.** A Sonnet judge (different model family from the Haiku authors) scored 100 sampled agent rationales per cell on state-accuracy / actionability / consistency: 3.03 / 4.05 / 4.46 (clean), 3.00 / 3.97 / 4.52 (defectors). Rationales are actionable and consistent; self-reported state figures are the weakest axis.

Every number regenerates from committed artifacts with `python -m scripts.figures --all` — $0, no API calls — and is regression-pinned by the test suite.

## How it works

```
sim/            engine.py · household.py · network.py · scenario.py · logging.py · overrides.py · data.py · types.py
sim/agents/     agent.py · policy.py · memory.py · protocol.py · cache.py · llm.py · failure_modes.py · seeding.py
sim/adapters/   nrel_solar.py · resstock.py · pecan_street.py
sim/strategies/ no_coordination.py · round_robin.py · round_robin_overlay.py · lp_optimal.py · llm_agent.py · llm_fallback.py
scripts/        figures.py · run.py · compare.py · sweep.py · eval_explanations.py · dose_check.py · export_demo_data.py · fetch_data.py
web/            SvelteKit static demo (see "Web demo" below)
```

**Simulator.** A discrete-time (15-minute tick) energy model: per-house solar, load, and battery (rate limits, round-trip efficiency, depth-of-discharge floor), a shared neighborhood bus with a transfer cap and transit losses, and a configurable outage schedule. Two runs of the same scenario YAML are byte-identical; strict-mode invariants (SoC bounds, energy conservation) assert every tick. Real data comes from NREL ResStock (loads) and NSRDB (solar) via adapters.

**Agent layer.** Each household runs an LLM agent that periodically emits a structured sharing policy, broadcasts its (possibly noised) own state to peers via INFORM messages, and negotiates transfers with speech-act messages — REQUEST / OFFER / ACCEPT / COUNTER / REJECT — each carrying a natural-language rationale. All peer knowledge is message-borne: agents act on beliefs built from what peers told them, never on engine ground truth. Accepted requests become binding commitments served ahead of discretionary sharing. Agents sit in overlapping *trust circles* (geographic neighbors, shared owners, demand-response aggregators) that shape who can talk to whom.

**Coordination is an injected callback** — `decide_transfers(t, states, households, solar, load, grid, neighborhood, dt) -> list[Transfer]` — so strategies are swappable: `no_coordination` (hoard), `round_robin` (fixed-rule sharing), `lp_optimal` (centralized full-information LP, the ceiling), `llm_agent` (live LLM), and `llm_fallback` (the zero-LLM control: identical machinery, fixed policy instead of a model).

**Failure modes** are independently injectable per scenario: selfish agents (`defector_fraction`, realized as a selfish system prompt), noisy observations (`obs_noise`), and communication constraints (`comm`: per-circle drop probabilities, per-sender message budgets).

**Reproducibility.** Live LLM calls are stored in a content-addressed prompt cache committed under `reference_runs/`, so every published run replays byte-identically with zero API calls. `tests/test_demo_data_pins.py` and `scripts/figures.py --check` pin every published number against the committed artifacts.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,data]"
```

Requires Python ≥ 3.12.

**Why the checkout is large.** `reference_runs/` is ~35.5k tracked files / ~266 MB, and
that is the deliberate reproducibility mechanism, not clutter: ~35.5k of those files are
the content-addressed LLM prompt caches (~102 MB) that let every live result replay
byte-identically with **zero API calls**, and the rest are the frozen run artifacts
(`state.jsonl` / `events.jsonl` / `messages.jsonl` / `summary.json`) every published figure
and table is re-derived from. A `--depth 1` clone skips the history but not these files.

## Quickstart

Run a scenario:

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

Reproduce the published figures and tables from the committed artifacts ($0, no API calls):

```bash
python -m scripts.figures --all      # writes docs/figures/*.png + docs/phase3_tables.md
python -m scripts.figures --check    # asserts committed numbers match their golden pins
```

Compare strategies on one scenario:

```bash
python -m scripts.compare --scenario configs/scenarios/haves_havenots_solar.yaml
```

## Tests

```bash
pytest
ruff check sim tests scripts
mypy
```

CI runs all three plus a `web` job (`svelte-check` + production build) on every push.

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
data_source: synthetic          # real-data adapters live in sim/adapters/ (NREL NSRDB solar, ResStock loads)
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
affiliations:                   # optional trust-circle overlays beyond geographic adjacency
  owner:
    owner_a: [r0c0, r2c3, r4c5] # one owner, three scattered properties
  dr_aggregator:
    agg_gridflex: [r0c0, r1c1, r2c2, r3c3, r4c4]
```

Failure modes (`failure_modes:` block) add `defector_fraction`, `obs_noise.{soc,load,solar}_std_frac`, and `comm.{drop_prob_by_circle, per_tick_budget}` — see the shipped `haves_havenots_solar__*.yaml` cells for working examples.

## Web demo

**Live URL:** <https://microgrid-llm-coordination.vercel.app/>

`web/` is a SvelteKit static site (`@sveltejs/adapter-static`) that replays four
already-committed live runs — clean, defectors, noise, comm — in the browser:
per-tick battery state across the 30-house grid, every executed transfer, and the
full peer-to-peer negotiation traffic the agents exchanged (12,258 REQUEST / OFFER
/ ACCEPT / COUNTER / REJECT rows for the clean cell — the templated INFORM state
broadcasts are downsampled out at export and ship as per-tick sent/delivered/dropped
counts instead). For the two cells that were actually judged, clean and defectors,
it also shows the 100 sampled rationales each and their scores. It is a **research
demo, not a deployment**, and it is purely a viewer: no backend, no API keys, no
live model calls. Everything it fetches is static JSON that
`python -m scripts.export_demo_data --out web/static/data` writes from the
committed `reference_runs/` artifacts, pinned against the published numbers by
`tests/test_demo_data_pins.py` so the demo cannot drift from the results section.

```bash
cd web && npm ci && npm run dev      # or: npm run build && npm run preview
```

Details — data contract, regeneration, and where the SvelteKit config actually
lives — are in [`web/README.md`](web/README.md).

## Limitations & scope

- **This is a research prototype, not a grid control system.** No claim of deployment readiness is made or implied; nobody's LLM coordination system is deployment-ready.
- The failure-cell results (defectors / noise / comm) are each a single seed compared against its own same-seed control; the clean-cell result is replicated across 3 seeds.
- The Rawlsian min-house floor is degenerate in this scenario family (identical across strategies), so fairness claims rest on Gini and Jain's index together.
- Selfish agents here *withhold* (hoard charge, decline requests). Their prompt also permits misreporting, but state broadcasts are generated by plain Python outside the LLM's control, so withholding is the only mechanism that actually operates — this is studied as a robustness axis, not sold as an adversarial-security contribution.
- Explanation quality is scored by an LLM judge (different model family from the authors, transparent rubric, consistency-checked across rubric paraphrases) — a method with known limitations; per-message scores are noisier than the aggregate means.
- Single dataset family (NREL ResStock / NSRDB, one climate); cross-climate cells were deferred.

## License

MIT — see [LICENSE](LICENSE).
