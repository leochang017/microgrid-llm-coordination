/**
 * Frozen data contract for the Phase 4b demo.
 *
 * SOURCE OF TRUTH: `scripts/export_demo_data.py` in the repo root. Every interface
 * below mirrors the keys that script's `build_*` / `build_meta` functions actually
 * emit — if the two ever disagree, the exporter wins and this file is the bug.
 *
 * Each cell ships 3 or 4 files under `static/data/<slug>/`:
 *   meta.json, ticks.json, messages.json, and explanations.json ONLY when the run
 *   has a committed `explanations_eval.json` (clean and defectors do; noise and
 *   comm do NOT — see `loadCell`, which resolves those to `null`).
 */

export type Slug = 'clean' | 'defectors' | 'noise' | 'comm';

/** One household. `circles` maps affiliation type -> group id (e.g. owner -> "own2"). */
export interface HouseMeta {
	id: string;
	row: number;
	col: number;
	/** true iff the house owns rooftop PV (`pvKwPeak > 0`). */
	have: boolean;
	pvKwPeak: number;
	batteryKwh: number;
	criticalLoadFrac: number;
	circles: Record<string, string>;
	defector: boolean;
}

/**
 * A method's headline metrics (`figures.METRIC_KEYS`, copied UNROUNDED).
 *
 * Only `served_load_fraction` is guaranteed. The LP ceiling is a throughput oracle,
 * not an engine run, so it defines served + gini only and the exporter reads the
 * rest with `.get(...)` — those keys arrive as JSON `null`, present but empty.
 */
export interface Metrics {
	served_load_fraction: number;
	gini_welfare: number | null;
	jains_index: number | null;
	min_house_served_fraction: number | null;
	served_critical_load_fraction: number | null;
}

export type BaselineMethod = 'no_coordination' | 'llm_fallback' | 'round_robin' | 'lp_optimal';

/** `meta.json` — everything that is not per-tick. */
export interface CellMeta {
	/** Scenario cell name, e.g. `haves_havenots_solar__comm`. */
	cell: string;
	/** Human label from `figures.CELL_LABEL`, e.g. "comm". */
	label: string;
	slug: Slug;
	seed: number;
	/** Provenance: the committed run directory this cell was exported from. */
	runDir: string;
	/** Agent model id; `null` if the scenario YAML omits `llm.model`. */
	model: string | null;
	scenarioBlurb: string;
	failureDescription: string;
	dtHours: number;
	tickCount: number;
	/** ISO timestamps, one per tick; index == tick number everywhere else. */
	tickTimes: string[];
	outage: { start: string; end: string };
	rows: number;
	cols: number;
	busMaxKw: number;
	houses: HouseMeta[];
	/** affiliation type -> group id -> member house ids. Geographic adjacency is NOT here. */
	circles: Record<string, Record<string, string[]>>;
	defectors: string[];
	live: Metrics;
	baselines: Record<BaselineMethod, Metrics>;
	gapClosedControlToLp: number;
	/** Bus-level message tallies: sent, delivered, dropped_*, pending_at_end. */
	messageCounts: Record<string, number>;
	negotiation: {
		commitmentsMade: number | null;
		commitmentsExpired: number | null;
		transferCount: number;
	};
	/** Present only when the cell has a committed explanations artifact. */
	judgeMeans?: { state_accuracy: number; actionability: number; consistency: number };
	/** Clean cell only: served_load_fraction for the other two seeds, keyed "1" and "7". */
	cleanSeedSpread?: Record<string, number>;
}

export interface TransferEvent {
	from: string;
	to: string;
	kw: number;
}

/** A non-transfer, non-outage_started engine event (sender_dod_floor, receiver_full, …). */
export interface GridEvent {
	kind: string;
	houses: string[];
	kw: number;
}

/**
 * `ticks.json` — columnar `[tick][house]` arrays. The house axis is `houseIds`
 * order for every 2-D array; the tick axis is `meta.tickTimes` order.
 */
export interface CellTicks {
	houseIds: string[];
	/** SoC as a fraction of the house's own battery capacity, 0..1. */
	socFrac: number[][];
	solarKw: number[][];
	loadKw: number[][];
	unmetKwh: number[][];
	/** Cumulative served-load fraction through tick k; last entry == `meta.live.served_load_fraction`. */
	servedFracCum: number[];
	transfers: TransferEvent[][];
	events: GridEvent[][];
	/** Per-tick INFORM aggregate — this is the whole comm-cell story (templated INFORMs are downsampled out of messages.json). */
	informCounts: { sent: number; delivered: number; dropped: number }[];
}

/**
 * `INFORM` is kept in this union because it is the simulator's own literal
 * (the color map needs a stable key for it) — NOT because `messages.json`
 * contains any. See `Msg` below: every INFORM in these runs is templated,
 * and the exporter's `keep_message` filter (`scripts/export_demo_data.py`)
 * drops templated INFORMs by design. Measured across all four committed
 * cells: zero `INFORM` rows in any `messages.json`. Do not build an INFORM
 * filter chip off the message list — there is nothing for it to filter.
 */
export type Performative = 'INFORM' | 'REQUEST' | 'OFFER' | 'ACCEPT' | 'COUNTER' | 'REJECT';

/**
 * One kept message. Templated INFORM broadcasts are downsampled out by the
 * exporter (`keep_message`), and in practice EVERY INFORM in these runs is
 * templated — so `messages.json` contains zero `perf: 'INFORM'` rows today
 * (measured across all four cells; clean's performative histogram is
 * `{REQUEST 4147, OFFER 4063, ACCEPT 2175, COUNTER 1168, REJECT 705}`, no
 * INFORM). The INFORM story — sent/delivered/dropped per tick, which is
 * exactly what makes the `comm` cell's message-loss visible — lives in
 * `CellTicks.informCounts`, not here. Build any INFORM-related UI off that,
 * not off this message list.
 *
 * Consequently `soc` (INFORM-only) is also present on zero rows today — do
 * not build UI on it without re-measuring against a fresh export.
 */
export interface Msg {
	/**
	 * UNIQUE per message (`m00000`, `m00001`, …). This is the ONLY safe key for a
	 * keyed `{#each ... (msg.id)}`.
	 */
	id: string;
	/**
	 * The negotiation THREAD id (the simulation's `correlation_id`). A REQUEST and
	 * its ACCEPT/COUNTER/REJECT reply deliberately SHARE one — on clean@23, 12,258
	 * messages carry only 8,210 distinct values. Use it to group a thread; NEVER as
	 * a unique key.
	 */
	cid: string;
	/** Tick index into `meta.tickTimes` / `CellTicks` rows. */
	t: number;
	perf: Performative;
	from: string;
	to: string;
	outcome: 'delivered' | 'dropped' | 'pending_at_end';
	/** Drop reason (`comm_drop`, `budget_overflow`) or `null` when not dropped. */
	reason: string | null;
	/** The agent's natural-language rationale (`rationale_nl`); `null` if the row had none. */
	why: string | null;
	/** true iff LLM-authored (i.e. not a templated message). */
	authored: boolean;
	/** Energy in the payload (`kwh`, else `deficit_estimate`); absent when neither is set. */
	kwh?: number;
	/** INFORM only: the sender's self-reported SoC in kWh. */
	soc?: number;
}

/** `messages.json`. */
export interface CellMessages {
	messages: Msg[];
}

export interface JudgeSample {
	sender: string;
	/** Tick index, joined from the sample's `t_sent`. */
	t: number;
	stateAccuracy: number;
	actionability: number;
	consistency: number;
}

/** `explanations.json` — absent for the noise and comm cells. */
export interface CellExplanations {
	rubricVariant: string;
	means: { state_accuracy: number; actionability: number; consistency: number };
	nScored: number;
	nAuthored: number;
	nTemplated: number;
	samples: JudgeSample[];
}
