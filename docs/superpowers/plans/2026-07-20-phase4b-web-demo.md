# Phase 4b — Web demo (SvelteKit static viewer on Vercel)

**Spec:** `docs/superpowers/specs/2026-07-20-phase4-paper-demo-design.md` · **Gate:** Phase 3.3 complete (met) · **Cost:** $0 (no API calls; the demo is a viewer of committed artifacts).

**Working rules:** smallest-possible diffs; one commit per task (Conventional Commits, no Claude attribution); append a Progress-log row to `CLAUDE.md` in the SAME commit as the task's artifacts; flip this plan's task checkbox in the same commit. Python tasks are TDD (red test first) and verify CI-equivalently in a fresh 3.12 venv (`pip install -e ".[dev,data]"`, then `ruff check sim tests scripts` + `mypy` + `pytest`). JS tasks: TDD is waived (repo test policy is Python-only; the risky data transformation is TDD'd on the Python side) — the gate is `npm run check` (svelte-check, 0 errors) + `npm run build`, run from `web/`. NEVER copy `llm_cache/` or `judge_cache/` anywhere near `web/`. NO secrets anywhere: before every push run `git diff --cached | grep -cE 'sk-ant-(api|oat)[0-9a-zA-Z_-]{15,}'` → must print `0`.

**Pinned-literal rule:** the test constants in this plan (message counts, seed-spread floats, tick indices, judge-sample values) were measured from the committed artifacts at planning time. If any comes up red at execution, re-derive it by measuring the committed artifact and correct the constant WITH the measurement evidence recorded in the progress-log row — never force-fit, never delete the assertion (house precedent: Test-Accuracy plan Task 6, "derived by running, never invented").

**Payload budget:** committed demo data ≤ 20 MB total, every file ≤ 15 MB (pre-commit `check-added-large-files --maxkb=15000`). Measured at design time: ~12.3 MB total, largest file 3.53 MB (`clean/messages.json`).

**Verified substrate facts this plan relies on (do not re-litigate):**
- `1 − Σ unmet_kwh / (Σ load_kw · 0.25)` over `state.jsonl` reproduces `summary.json.served_load_fraction` exactly (checked on clean__seed23: 0.6725764138021589).
- `explanations_eval*.json` samples carry only `sender`, `t_sent`, and the three scores — NO `correlation_id`; `(sender, t_sent)` is ambiguous for most samples (multiple authored messages per sender-tick). Judge scores therefore join at tick level.
- comm cell drops: `messages.jsonl` outcome=dropped with `reason` ∈ {`comm_drop`: 1498, `budget_overflow`: 11194}; almost all budget drops are templated INFORMs.
- `summary.json.failure_modes_active.defector_house_ids` is `[]` for random assignment — defectors must be re-derived via `sim.agents.failure_modes.assign_defectors(house_ids, cfg, scenario_seed)` (deterministic).

---

## Task 0 — Environment preflight (no commit)

1. Build the CI-parity venv in the scratchpad: `python3.12 -m venv $SCRATCH/venv && $SCRATCH/venv/bin/pip install -e ".[dev,data]"`. Run `ruff check sim tests scripts`, `mypy`, `pytest -q` — record the green baseline (407 passed expected).
2. Check node: `node --version` must be ≥ 20.19 (Vite 7 floor) and `npm --version` works (v24.10.0 / 11.6.0 confirmed present at planning time). If node is missing/old, STOP and ask Leo before proceeding.
3. Confirm `python -m scripts.figures --check` passes (golden pins intact) using the venv.
4. **Verify:** all four commands green. This venv + node are what every later verify uses.
- [ ] Task 0 complete

## Task 1 — `scripts/export_demo_data.py` data layer (TDD)

Pure transformation functions + CLI. All functions take parsed data so tests can run without regenerating baselines except one integration test.

1. RED: new `tests/test_export_demo_data.py`. Module-level fixtures load the real committed clean cell once:
   ```python
   CLEAN_DIR = Path("reference_runs/haves_havenots_solar__llm/llm_agent/clean__seed23")
   ```
   Write these tests (they must fail with ImportError first):
   - `test_demo_cells_pins`: `DEMO_CELLS == {"clean": ("haves_havenots_solar__llm", 23), "defectors": ("haves_havenots_solar__defectors", 7), "noise": ("haves_havenots_solar__noise", 23), "comm": ("haves_havenots_solar__comm", 23)}`.
   - `test_tick_times`: `ts = tick_times(load_jsonl(CLEAN_DIR / "state.jsonl"))`; assert `len(ts) == 96`, `ts[0] == "2018-01-01T00:00:00"`, `ts[-1] == "2018-01-01T23:45:00"`, strictly increasing.
   - `test_build_houses_rederivation`: `houses = build_houses(scenario_for("clean"), load_jsonl(CLEAN_DIR / "state.jsonl"))`; assert 30 entries in row-major order (`houses[0]["id"] == "r0c0"`, `houses[29]["id"] == "r4c5"`); for every house `have == (pv_kw_peak > 0)`; the house `r0c0` has `circles == {"owner": "owner_a", "dr_aggregator": "agg_gridflex"}`; every house's `battery_kwh >= max observed soc_kwh - 1e-9` (read from state rows); every have has some tick with `solar_kw > 0` and every havenot has all `solar_kw == 0`; `defector is False` for all (clean cell).
   - `test_build_houses_defectors`: for the defectors cell, `sum(h["defector"] for h in houses) == 6` (round(30 · 0.2)) and the set equals `assign_defectors(sorted(ids), scenario.failure_modes, 7)`.
   - `test_keep_message_policy`: rows = `load_jsonl(CLEAN_DIR / "messages.jsonl")`; kept = `[m for m in rows if keep_message(m)]`; assert `len(kept) == 12258`; every kept row satisfies `m["performative"] != "INFORM" or not m["templated"]`; no kept row's serialized form contains the key `t_decided` after `build_messages` (slimming works).
   - `test_build_messages_comm_drops`: on the comm cell's `messages.jsonl`, the built list contains > 0 entries with `outcome == "dropped"` and `reason == "comm_drop"`; sum over ticks of `informCounts[i]["dropped"]` + count of built messages with outcome "dropped" == 12692.
   - `test_build_ticks_shapes_and_served_identity`: on clean, `t = build_ticks(state_rows, events_rows, messages_rows, tick_of, house_order, dt_hours=0.25)`; assert `len(t["socFrac"]) == 96`, `len(t["socFrac"][0]) == 30`, all values in `[0, 1.001]`; `len(t["transfers"][2]) >= 1` (first transfer at tick 2 = 00:30); `t["servedFracCum"][-1] == pytest.approx(0.6725764138021589, abs=5e-5)` (5e-5 because stored values are rounded to 4 dp).
   - `test_build_explanations`: on clean's `explanations_eval.json`, result has `means == {"state_accuracy": 3.03, "actionability": 4.05, "consistency": 4.46}`, `nScored == 100`, 100 samples each with keys `{sender, t, stateAccuracy, actionability, consistency}` and `t` a valid tick index in `[0, 95]`.
   - `test_export_cell_integration` (the one slow test, ~60–90 s — same cost class as the existing `test_collect_cell_merges_baselines_and_live`): `export_cell("clean", tmp_path)`; assert files `meta.json`, `ticks.json`, `messages.json`, `explanations.json` exist under `tmp_path / "clean"`; `meta["live"]["served_load_fraction"] == 0.6725764138021589` exactly; `meta["baselines"]` has keys `{"no_coordination", "llm_fallback", "round_robin", "lp_optimal"}`; `0 < meta["gapClosedControlToLp"] < 1`; `meta["cleanSeedSpread"] == {"1": 0.8248454685184583, "7": 0.7963806526129852}`; `meta["outage"] == {"start": "2018-01-01T00:00:00", "end": "2018-01-02T00:00:00"}`; every emitted file's size < 15_000_000 bytes; every file ends with a single trailing newline (pre-commit `end-of-file-fixer` parity).
   Run `pytest tests/test_export_demo_data.py -q` → all fail (red).
2. GREEN: new `scripts/export_demo_data.py` (mypy-strict, ruff-clean). Contents:
   - `DEMO_CELLS: dict[str, tuple[str, int]]` as pinned above; `FAILURE_DESCRIPTIONS: dict[str, str]` and `SCENARIO_BLURB: str` (human text: clean = "No failure modes; hardest of three committed seeds (23; seeds 1/7 shown as spread)"; defectors = "20% of agents (6 houses, seeded assignment) are prompted to hoard and mislead"; noise = "Agents observe SoC with 10% and load with 15% Gaussian noise"; comm = "2-msg/tick send budget + per-circle drops (geo 30%, owner 5%, DR 10%) — most INFORMs never arrive").
   - `load_jsonl(path: Path) -> list[dict[str, Any]]`.
   - `scenario_for(slug: str) -> Scenario`: `dataclasses.replace(load_scenario(SCEN / f"{cell}.yaml"), seed=seed)` — mirrors `scripts/figures.py:176`.
   - `tick_times(state_rows) -> list[str]`: sorted unique `t`.
   - `build_houses(scenario, state_rows) -> list[dict[str, Any]]`: `sample_households(scenario, np.random.default_rng(scenario.seed))` (mirrors `figures.py:194`); row-major list of `{id, row, col, have, pvKwPeak (3dp), batteryKwh (3dp), criticalLoadFrac (3dp), circles, defector}`; `have = pv_kw_peak > 0.0`; defectors via `assign_defectors(sorted(households), scenario.failure_modes, scenario.seed)`; raises `ValueError` if the state.jsonl solar/battery cross-checks fail (drift tripwire).
   - `keep_message(m) -> bool`; `build_messages(rows, tick_of) -> dict[str, Any]`: `{"messages": [...]}` with per-row `{id, t (tick int of t_sent), perf, from, to, outcome, reason, why, authored, kwh? (2dp), soc? (2dp)}` (`kwh` from payload `kwh`/`deficit_estimate` when present; `soc` from INFORM payload `soc_kwh`).
   - `build_ticks(state_rows, events_rows, messages_rows, tick_of, house_order, dt_hours) -> dict[str, Any]`: columnar `{houseIds, socFrac, solarKw, loadKw, unmetKwh, servedFracCum, transfers, events, informCounts}` (shapes per the TS interfaces in Task 2; floats 3dp, servedFracCum 4dp; `transfers[k]` from `transfer_executed` events `{from: house_ids[0], to: house_ids[1], kw (2dp)}`; `events[k]` = non-transfer, non-outage events `{kind, houses, kw}`; `informCounts[k]` = INFORM-only `{sent, delivered, dropped}` from messages at that tick).
   - `build_explanations(obj, tick_of) -> dict[str, Any]`: `{rubricVariant, means, nScored, nAuthored: n_llm_authored, nTemplated: n_templated, samples: [{sender, t, stateAccuracy, actionability, consistency}]}`.
   - `build_meta(slug, scenario, houses, methods, summary, tick_ts, expl) -> dict[str, Any]`: `{cell, label (figures.CELL_LABEL), slug, seed, runDir, model (config llm.model), scenarioBlurb, failureDescription, dtHours, tickCount, tickTimes, outage (first entry of scenario.outages ISO), rows, cols, busMaxKw, houses, circles (scenario.affiliations as plain dict), defectors (ids), live (5 METRIC_KEYS from summary, unrounded), baselines ({method: metrics via .get for LP}, unrounded), gapClosedControlToLp (figures.cell_served_gap_closed(methods)), messageCounts (summary.message_counts), negotiation {commitmentsMade, commitmentsExpired, transferCount}, judgeMeans (from expl or absent), cleanSeedSpread (clean slug only, via read_live_summary(CLEAN, 1/7))}`.
   - `export_cell(slug, out_root) -> None`: resolves run dir via `figures.LIVE_CELLS`, loads the three jsonl + summary + config + optional `explanations_eval.json`, computes `methods = figures.collect_cell(cell, seed)` (this is what regenerates baselines AND runs the C6-3 frozen-config guard), asserts the served identity `< 1e-9` before rounding, writes the 3–4 JSON files with `json.dumps(obj, separators=(",", ":"))` + `"\n"`.
   - `main(argv) -> int` + `if __name__ == "__main__"`: `python -m scripts.export_demo_data [--out web/static/data] [--cells clean,comm]`; prints one line per cell: slug, file names, byte sizes; refuses to write any file ≥ 15 MB.
3. Run `pytest tests/test_export_demo_data.py -q` → green. Do NOT run the CLI against `web/` yet (dir doesn't exist until Task 2; data lands in Task 3).
4. **Verify:** in the venv — `pytest tests/test_export_demo_data.py -q` → `9 passed`; `ruff check sim tests scripts` → `All checks passed!`; `mypy` → success; full `pytest -q` still green (416 total expected).
5. **Commit:** `feat(demo): export_demo_data script — compact per-cell JSON for the web demo` (+ Progress-log row, + checkbox).
- [x] Task 1 complete

## Task 2 — Scaffold `web/` SvelteKit static app

1. `npx sv create web --template minimal --types ts --no-add-ons --install npm` (if the flags are rejected by the installed `sv` version, run `npx sv create web` interactively: minimal template, TypeScript, no add-ons, npm). Then in `web/`: `npm i -D @sveltejs/adapter-static` and `npm uninstall @sveltejs/adapter-auto`.
2. `web/svelte.config.js`: `import adapter from '@sveltejs/adapter-static';` with `kit: { adapter: adapter(), prerender: { entries: ['/', '/run/clean', '/run/defectors', '/run/noise', '/run/comm'] } }`.
3. `web/src/routes/+layout.ts`: `export const prerender = true; export const trailingSlash = 'always';`.
4. `web/src/lib/types.ts` — the frozen data contract (mirrors Task 1 exactly):
   ```ts
   export type Slug = 'clean' | 'defectors' | 'noise' | 'comm';
   export interface HouseMeta { id: string; row: number; col: number; have: boolean;
     pvKwPeak: number; batteryKwh: number; criticalLoadFrac: number;
     circles: Record<string, string>; defector: boolean; }
   export interface Metrics { served_load_fraction: number; gini_welfare?: number;
     jains_index?: number; min_house_served_fraction?: number; served_critical_load_fraction?: number; }
   export interface CellMeta { cell: string; label: string; slug: Slug; seed: number; runDir: string;
     model: string; scenarioBlurb: string; failureDescription: string; dtHours: number;
     tickCount: number; tickTimes: string[]; outage: { start: string; end: string };
     rows: number; cols: number; busMaxKw: number; houses: HouseMeta[];
     circles: Record<string, Record<string, string[]>>; defectors: string[];
     live: Metrics; baselines: Record<'no_coordination'|'llm_fallback'|'round_robin'|'lp_optimal', Metrics>;
     gapClosedControlToLp: number; messageCounts: Record<string, number>;
     negotiation: { commitmentsMade: number; commitmentsExpired: number; transferCount: number };
     judgeMeans?: { state_accuracy: number; actionability: number; consistency: number; nScored: number };
     cleanSeedSpread?: Record<string, number>; }
   export interface TransferEvent { from: string; to: string; kw: number }
   export interface GridEvent { kind: string; houses: string[]; kw: number }
   export interface CellTicks { houseIds: string[]; socFrac: number[][]; solarKw: number[][];
     loadKw: number[][]; unmetKwh: number[][]; servedFracCum: number[];
     transfers: TransferEvent[][]; events: GridEvent[][];
     informCounts: { sent: number; delivered: number; dropped: number }[]; }
   export type Performative = 'INFORM'|'REQUEST'|'OFFER'|'ACCEPT'|'COUNTER'|'REJECT';
   export interface Msg { id: string; t: number; perf: Performative; from: string; to: string;
     outcome: 'delivered'|'dropped'|'pending_at_end'; reason: string | null;
     why: string; authored: boolean; kwh?: number; soc?: number; }
   export interface CellMessages { messages: Msg[] }
   export interface JudgeSample { sender: string; t: number; stateAccuracy: number;
     actionability: number; consistency: number; }
   export interface CellExplanations { rubricVariant: string;
     means: { state_accuracy: number; actionability: number; consistency: number };
     nScored: number; nAuthored: number; nTemplated: number; samples: JudgeSample[]; }
   ```
5. `web/src/lib/load.ts`: `loadCell(slug: Slug, fetchFn = fetch): Promise<{meta, ticks, messages, explanations|null}>` — four parallel fetches from `/data/${slug}/…` (explanations fetched with a 404-tolerant catch → null); builds `msgsByTick: Map<number, Msg[]>` once.
6. `web/src/lib/colors.ts`: `VIRIDIS = ['#440154','#472d7b','#3b528b','#2c728e','#21918c','#28ae80','#5ec962','#addc30','#fde725']`; `socColor(frac: number): string` piecewise-linear RGB interpolation over the 9 stops; `PERF_COLORS: Record<Performative, string> = { REQUEST:'#f59e0b', OFFER:'#38bdf8', ACCEPT:'#4ade80', COUNTER:'#c084fc', REJECT:'#f87171', INFORM:'#94a3b8' }`.
7. `web/src/app.css` (imported in `+layout.svelte`): dark theme tokens — `--bg:#0e1116; --panel:#171b22; --border:#2a3038; --text:#e6e9ee; --muted:#9aa4b2; --accent:#fde725;` system font stack, `font-variant-numeric: tabular-nums` on metric classes, `@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }`.
8. Placeholder `web/src/routes/+page.svelte` (h1 "Microgrid LLM coordination — demo") so build succeeds; `web/static/data/.gitkeep`. Append to root `.gitignore`: `web/node_modules/`, `web/.svelte-kit/`, `web/build/`. Commit `web/package-lock.json` (needed by `npm ci` in CI). Also add `web/vercel.json`: `{ "framework": null, "buildCommand": "npm run build", "outputDirectory": "build", "trailingSlash": true }`.
9. **Verify:** from `web/` — `npm run check` → `svelte-check found 0 errors and 0 warnings`; `npm run build` → completes, `ls build/index.html` exists. From repo root: `pytest -q` still green (no Python touched).
10. **Commit:** `feat(demo): scaffold SvelteKit static app under web/ (adapter-static, TS, dark theme tokens)` (+ Progress-log row, + checkbox).
- [ ] Task 2 complete

## Task 3 — Export the four cells, commit the data + drift-pin test

1. RED: new `tests/test_demo_data_pins.py` (cheap — file reads only, no regen):
   - `test_all_cells_exported`: for each slug in `DEMO_CELLS`, `web/static/data/<slug>/meta.json`, `ticks.json`, `messages.json` exist; `explanations.json` exists for exactly `{"clean", "defectors"}`.
   - `test_live_numbers_match_golden_pins`: for each slug, load meta; assert `meta["live"]["served_load_fraction"] == figures.EXPECTED_LIVE[(cell, seed)]["served_load_fraction"]` and same for `gini_welfare` — EXACT float equality (same contract as `python -m scripts.figures --check`).
   - `test_clean_seed_spread_matches_pins`: clean meta's `cleanSeedSpread` equals the seed-1/seed-7 `served_load_fraction` pins from `EXPECTED_LIVE`.
   - `test_lp_is_ceiling`: for each slug, `baselines["lp_optimal"]["served_load_fraction"] >= live served − 1e-9` and ≥ each other baseline's served.
   - `test_no_secrets_or_caches_in_data`: no file under `web/static/data/` matches `sk-ant-` and no path contains `llm_cache` or `judge_cache`.
   Run → red (data missing).
2. GREEN: `python -m scripts.export_demo_data --out web/static/data` (venv; ~4–6 min — regenerates baselines for all four cells; the C6-3 guard will abort loudly if any scenario YAML drifted).
3. `du -sh web/static/data` → expect ~12–13 MB; `ls -la web/static/data/clean` → 4 files, `messages.json` ≈ 3.5 MB.
4. **Verify:** `pytest tests/test_demo_data_pins.py -q` → `5 passed`; full `pytest -q` green; `ruff check sim tests scripts` clean; `mypy` clean; pre-commit hooks pass on the staged data files (large-file + end-of-file).
5. **Commit:** `feat(demo): commit exported four-cell demo data + golden-pin drift test` (+ Progress-log row, + checkbox).
- [ ] Task 3 complete

## Task 4 — Overview route `/` (cell picker + comparison bars)

1. `web/src/lib/components/ComparisonBar.svelte` — props `{ meta: CellMeta }`. Horizontal SVG bars, method order `no_coordination / llm_fallback / round_robin / live / lp_optimal` with labels `no-coord / control / round-robin / live-Haiku / LP ceiling` (mirrors `figures.METHOD_ORDER`/`METHOD_LABEL`); bar length ∝ `served_load_fraction` (x-domain [0,1]); live bar in `--accent`, others `--muted`; value printed at bar end (3 dp); annotation over live bar: `closes {(gapClosedControlToLp*100).toFixed(0)}% of control→LP gap`.
2. `web/src/routes/+page.svelte`: `onMount` fetches all four `meta.json` in parallel. Renders: title + one-paragraph project blurb; provenance strip (model id, "static replay of committed reference runs — no live LLM calls, no backend"); a card per cell in story order clean → defectors → noise → comm, each with label, `scenarioBlurb`/`failureDescription`, `ComparisonBar`, fairness chips (`gini {v.toFixed(3)}` + `Jain {v.toFixed(3)}` — always together, never Gini alone), judge-means chips when `judgeMeans` present (`accuracy 3.03 · actionability 4.05 · consistency 4.46 (n=100, Sonnet judge)`), and for clean a footnote `seeds 1/7 served 0.825 / 0.796 (this replay: seed 23, the hardest)`; card links to `/run/{slug}/`. Footer: GitHub repo link, MIT, "research demo — not a deployment".
3. Loading + error states: skeleton cards while fetching; a visible error box if a fetch fails.
4. **Verify:** `npm run check` → 0 errors; `npm run build`; `npm run preview` then open `http://localhost:4173/` in the browser — four cards, clean card shows served 0.673 with the comparison bars and a gap-closed annotation.
5. **Commit:** `feat(demo): overview route — cell picker with baseline comparison bars and fairness chips` (+ Progress-log row, + checkbox).
- [ ] Task 4 complete

## Task 5 — Replay route: SoC neighborhood grid + tick scrubber

1. `web/src/lib/replay.svelte.ts`:
   ```ts
   export class ReplayState {
     tick = $state(0); playing = $state(false); speed = $state(1); // 1|2|4
     selectedHouse = $state<string | null>(null);
     showTransfers = $state(true); showMessages = $state(false); showCircles = $state(false);
     seek(t: number, max: number) { /* clamp to [0, max] */ } togglePlay() { this.playing = !this.playing; }
   }
   ```
   Play loop in the page: `setInterval` at `450 / speed` ms advancing `tick`, auto-pause at `tickCount − 1`.
2. `web/src/lib/components/NeighborhoodGrid.svelte` — props `{ meta, ticks, state: ReplayState }`. SVG `viewBox="0 0 660 560"`; house cell = `<rect>` 96×96 at `x = 6 + col*109`, `y = 6 + row*109`, `rx=8`, fill `socColor(ticks.socFrac[state.tick][idx])`; haves get `stroke: #e6e9ee; stroke-width: 2.5` + a small sun-dot circle top-right; defectors a red corner wedge path + `<title>` including "defector"; unmet load this tick (`unmetKwh > 0`) shows a small warning triangle bottom-left. Each rect: `tabindex="0" role="button"` with `aria-label` = `"house r0c0 — SoC 34%, have, owner_a"`; click/Enter sets `state.selectedHouse`. Selected house gets an accent outline. House id text label (muted, 10 px) inside each cell.
3. `web/src/lib/components/TickScrubber.svelte` — props `{ meta, ticks, state }`. Native `<input type="range" min=0 max={tickCount-1}>` bound to `state.tick` (native arrow-key support); play/pause button (space via `on:keydown` on the wrapper); speed toggle 1×/2×/4×; clock label from `tickTimes[tick]` rendered as `HH:MM`; beneath the slider a 96-bin strip chart (tiny SVG) of total `solarKw` per tick (yellow area) and total `unmetKwh` (red), so users see day/night and the pain hours; outage window annotation ("grid down 00:00–24:00 for all 30 houses" from `meta.outage`).
4. `web/src/routes/run/[cell]/+page.svelte`: reads `page.params.cell`, validates against the four slugs (else "unknown cell" message + link home); `onMount` → `loadCell`; layout: header (cell label, blurb, live served + gap-closed, link back), left = grid + scrubber, right = panels (Tasks 7–8; placeholder aside for now). Headline stat row: served / gini / Jain / transfers (from meta, tabular-nums).
5. **Verify:** `npm run check` → 0 errors; `npm run build` → prerenders `/run/clean/` etc. (4 entries); `npm run preview` → open `http://localhost:4173/run/clean/`, scrub to ~12:00 — the 12 have-house cells visibly brighten (viridis toward yellow) as midday solar charges them; keyboard arrows move the slider; space toggles play.
6. **Commit:** `feat(demo): replay view — SoC neighborhood grid + tick scrubber with day/night strip` (+ Progress-log row, + checkbox).
- [ ] Task 5 complete

## Task 6 — Transfer arrows, trust-circle overlay, event badges

1. In `NeighborhoodGrid.svelte`, add a transfer layer (when `state.showTransfers`): for each `ticks.transfers[state.tick]`, draw an SVG line+arrowhead from center(from) to center(to); `stroke-width = clamp(1.5, kw * 1.2, 6)`; green `#4ade80`; animated `stroke-dasharray` flow (CSS animation, disabled under reduced-motion); `<title>` = `"r0c3 → r0c2 · 1.65 kW"`.
2. Circle overlay (when `state.showCircles`): from `meta.circles`, colored corner ribbons per group (owner_a amber, owner_b teal, agg_gridflex violet) on member cells + a legend; geographic layer shown as faint lattice lines between 4-neighbors. Toggle buttons for `showTransfers` / `showCircles` / `showMessages` above the grid (aria-pressed).
3. Event badges: for `ticks.events[state.tick]`, render a compact strip under the grid: `sender_dod_floor ×3 · receiver_full ×1 · bus_saturated` with house ids on hover — this is the physics-said-no channel that explains why promised energy didn't move.
4. **Verify:** `npm run check` 0 errors; `npm run build`; preview `/run/clean/` at tick 2 (00:30) shows the first transfer arrow; circles toggle shows the owner_a ribbon on exactly r0c0, r2c3, r4c5.
5. **Commit:** `feat(demo): transfer arrows, trust-circle overlay, physics event badges` (+ Progress-log row, + checkbox).
- [ ] Task 6 complete

## Task 7 — Message-flow overlay + per-tick message panel (drop reasons)

1. Message overlay on the grid (when `state.showMessages`): for the current tick's `msgsByTick.get(tick)`, draw thin arcs colored by `PERF_COLORS[perf]`; dropped messages dashed at 50% opacity; cap at 80 arcs per tick (priority: non-INFORM first, then authored INFORMs) with a "+N more" note — keeps the comm cell legible.
2. `web/src/lib/components/MessagePanel.svelte` — props `{ meta, msgsByTick, informCounts, state }`. Shows the current tick's messages as rows: perf pill (colored), `from → to`, kwh when present, outcome badge (`delivered` green / `dropped: comm_drop` red / `dropped: budget_overflow` orange / `pending` gray), and the `why` rationale text (authored rationales full-width in a quote style; templated ones muted single-line). Filters: performative toggles, "authored only" checkbox, house filter (auto-follows `state.selectedHouse`, clearable). Header strip always shows the INFORM aggregate for this tick: `INFORMs: {sent} sent · {delivered} delivered · {dropped} dropped` — on the comm cell this is the story, so when `slug === 'comm'` add one explanatory sentence under the strip.
3. Wire the panel into `/run/[cell]/+page.svelte` right column (tab 1 of 2; tab 2 is HousePanel, Task 8).
4. **Verify:** `npm run check` 0 errors; `npm run build`; preview `/run/comm/` — message panel shows rows with `dropped: comm_drop` badges and the INFORM strip shows large dropped counts; on `/run/clean/` filter to REQUEST shows amber pills with kWh amounts and rationale text.
5. **Commit:** `feat(demo): message-flow overlay + per-tick message panel with drop reasons` (+ Progress-log row, + checkbox).
- [ ] Task 7 complete

## Task 8 — Per-house "why" panel (rationales + judge scores)

1. `web/src/lib/components/HousePanel.svelte` — props `{ meta, ticks, msgsByTick, explanations, state }`. When no house selected: prompt "click a house". When selected:
   - Identity card: id, have/have-not, PV kW, battery kWh, critical-load frac, circles, defector flag (explicit text, not just color).
   - SoC sparkline: 96-tick SVG line of `socFrac[·][idx]` with a cursor at `state.tick`; clicking the sparkline seeks.
   - "Why" feed: this house's messages at the current tick (sent and received), authored rationales rendered prominently (`authored` badge = "LLM-authored"; templated = "templated"); a "show all ticks" toggle lists every non-INFORM message involving the house (capped 300 rows + count).
   - Judge scores section (only when `explanations !== null`): samples where `sender === selectedHouse`, each row like `22:15 · accuracy 2 · actionability 4 · consistency 4`, click seeks the scrubber to `t` and flips to the message tab with the house filter on. Honesty note (one line): "scores attach to a sampled rationale from this tick; where several rationales share the tick the pairing is ambiguous (the committed eval predates per-message ids)". Cells without eval files (noise, comm) say "no judged sample for this cell — judging ran on clean + defectors".
2. Right column becomes tabs: `Messages` / `House`. Selecting a house on the grid switches to the House tab.
3. **Verify:** `npm run check` 0 errors; `npm run build`; preview `/run/clean/`, click `r4c4`, judge section lists a sample with three axis scores; clicking it moves the scrubber to that tick.
4. **Commit:** `feat(demo): per-house why panel — rationales, SoC sparkline, judge scores` (+ Progress-log row, + checkbox).
- [ ] Task 8 complete

## Task 9 — CI web job + docs sync

1. `.github/workflows/ci.yml`: add a second job (existing `test` job untouched):
   ```yaml
   web:
     runs-on: ubuntu-latest
     defaults: { run: { working-directory: web } }
     steps:
       - uses: actions/checkout@v4
       - uses: actions/setup-node@v4
         with: { node-version: "22", cache: npm, cache-dependency-path: web/package-lock.json }
       - run: npm ci
       - run: npm run check
       - run: npm run build
   ```
2. Clean-install dry-run rule (new top-level dir + workflow change): fresh 3.12 venv in the scratchpad, `pip install -e ".[dev,data]"` → succeeds; `python -c "import sim"` works; confirm `web` is not importable/packaged (`pip show -f microgrid-sim | grep -c web` → `0`).
3. New `web/README.md`: what the demo is (viewer of committed artifacts, no backend/keys), how to rebuild data (`python -m scripts.export_demo_data --out web/static/data`), dev commands (`npm run dev` / `check` / `build` / `preview`), data-contract pointer to `src/lib/types.ts` + `tests/test_demo_data_pins.py`.
4. Root `README.md`: add a "Web demo" section (architecture one-liner; URL placeholder filled in Task 10). `CLAUDE.md`: add `web/` + this plan to Critical files; note the JS gate (svelte-check + build; TDD Python-only).
5. **Verify:** venv `ruff check sim tests scripts` + `mypy` + `pytest -q` green; `web/` `npm ci && npm run check && npm run build` green from a clean `node_modules` (proves the CI job as written); `git diff --cached | grep -cE 'sk-ant-(api|oat)[0-9a-zA-Z_-]{15,}'` → `0`.
6. **Commit:** `ci(demo): web build job (npm ci + svelte-check + build) + demo docs sync` (+ Progress-log row, + checkbox).
- [ ] Task 9 complete

## Task 10 — Scripted click-through, Vercel deploy (Leo-gated), wrap

1. Full local verification: `npm run build && npm run preview`, then a scripted Playwright click-through with the local browser tooling (nothing committed):
   - `/` → four cards render; clean card text contains `0.673`; comm card contains `0.494`.
   - `/run/clean/` → scrub to tick 48 (12:00); read `aria-label` of `r0c0`; click `r4c4` → House tab shows a judge sample; toggle circles → owner_a ribbon on r0c0/r2c3/r4c5.
   - `/run/comm/` → message panel shows `dropped: budget_overflow` and the INFORM aggregate strip.
   - `/run/defectors/` → 6 houses carry the defector marker.
   - No console errors on any page; largest network transfer (messages.json) < 5 MB uncompressed.
   Record pass/fail per check in the session notes; fix-forward anything red before proceeding.
2. **Leo-gated deploy (STOP and hand off — executor does not touch the Vercel account):** Leo imports the GitHub repo in the Vercel dashboard, sets **Root Directory = `web`** (the committed `web/vercel.json` supplies the rest), deploys, and pastes the production URL. No env vars, no secrets, no CLI tokens.
3. Executor verifies the live URL: all four routes load over the network, brotli/gzip served for `/data/...` JSON, deep link `https://<url>/run/comm/` works.
4. Fill the demo URL into root `README.md` "Web demo" section; final Progress-log row (payload size, URL, verification summary). No phase tag here — `paper-v1` lands with the paper half per the roadmap exit.
5. **Verify:** live URL loads all four cells; `python -m scripts.figures --check` still green; full venv `pytest -q` green; secrets grep on staged diff → `0`.
6. **Commit:** `docs(demo): live demo URL + phase 4b wrap` (+ Progress-log row, + checkbox). Push.
- [ ] Task 10 complete

---

**Deferred, tracked so they aren't silently dropped:** Sonnet ablation cell page (add later if the advisor wants the capability story visible); rubric-variant (terse/roleplay) judge tables (paper appendix material); per-message judge joins (blocked on re-running `scripts/eval_explanations.py` with per-message ids, which costs judge money and is Leo-gated).
