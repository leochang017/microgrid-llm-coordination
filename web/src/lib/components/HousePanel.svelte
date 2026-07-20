<!--
	Per-house "why" panel: who this household is, what its battery did across the day,
	what it said at the current tick, and how the LLM judge scored its rationales.

	Facts rendered here are only the ones the exported data actually carries:
	  * `criticalLoadFrac` is the household's own `HouseholdProfile.critical_load_frac`
	    — "fraction of this household's load that is critical (medical devices,
	    refrigeration, heating minimums)" per `sim/types.py:40-44`. It is a share of the
	    house's OWN demand, not a share of the neighborhood's, and the label says so.
	  * The defector flag is the `prompt` realization used by every committed cell
	    (`configs/scenarios/haves_havenots_solar__defectors.yaml`:
	    `defector_realization: prompt`): the selfish system prompts in
	    `sim/agents/agent.py` (`_PLAN_SYSTEM_PROMPT_SELFISH` / `_REACT_SYSTEM_PROMPT_SELFISH`)
	    raise `share_min_soc_frac`, lower `max_share_kw_per_tick` and default to REJECT on
	    incoming REQUESTs — i.e. hoarding and declining. `_PLAN_SYSTEM_PROMPT_SELFISH`
	    (`sim/agents/agent.py:44-52`) ALSO licenses misreporting ("You MAY misreport your
	    state (SoC, load, need) to neighbors"), but the agent has no channel to act on it:
	    `emit_informs` (`agent.py:905-934`) is pure Python emitting `last_visible_own`, and
	    `peer_beliefs` is fed ONLY by INFORMs (`agent.py:245-247`), so a misreport could
	    only ever appear as words in a free-text rationale that updates nobody's belief.
	    Hence "INFORM broadcasts stay truthful" below — a statement about the mechanism,
	    not about what the prompt permits.
	  * `meta.circles` carries ONLY owner/manager/aggregator affiliations — geographic
	    4-neighbour adjacency is not in it (see `types.ts`) — so "no circles" is written
	    as "no owner/aggregator circle", never as "no neighbours".

	The sparkline carries its text equivalent in the caption below it (the same contract
	the tick scrubber's strip chart uses — start, peak, trough and the value at the
	cursor, all computed from the plotted array, never asserted). It is NOT aria-hidden,
	because it is genuinely operable: it is an ARIA slider over the tick axis (click to
	seek, arrows to step, Home/End to jump), with `aria-valuetext` naming the clock time
	and SoC it currently sits on.

	Judge scores join at TICK level, never per message: the committed eval rows carry only
	`(sender, t_sent)` and no correlation id, and a sender usually authored several
	messages in one tick. The honesty note under the list says exactly that rather than
	implying a rationale-level pairing the data cannot support.
-->
<script lang="ts">
	import { PERF_COLORS } from '$lib/colors';
	import type { CellExplanations, CellMeta, CellTicks, Msg } from '$lib/types';
	import type { ReplayState } from '$lib/replay.svelte';

	interface Props {
		meta: CellMeta;
		ticks: CellTicks;
		msgsByTick: Map<number, Msg[]>;
		/** `null` for cells with no committed judging artifact (noise, comm). */
		explanations: CellExplanations | null;
		state: ReplayState;
		/** Asks the host page to show the Messages tab (used by the judge-sample rows). */
		onShowMessages: () => void;
	}

	// Renamed on destructure: a binding called `state` shadows the `$state` rune.
	const { meta, ticks, msgsByTick, explanations, state: replay, onShowMessages }: Props =
		$props();

	/** Hard cap on the "all ticks" list; the count beside it always reports the true total. */
	const ALL_CAP = 300;

	const maxTick = $derived(meta.tickCount - 1);

	function hhmm(iso: string): string {
		return iso.slice(11, 16);
	}
	function pct(frac: number): number {
		return Math.round(Math.max(0, Math.min(1, frac)) * 100);
	}

	const house = $derived(meta.houses.find((h) => h.id === replay.selectedHouse) ?? null);
	// Indexed against `ticks.houseIds`, which is the documented column order of every
	// `CellTicks` matrix (`types.ts`). `meta.houses` happens to agree today, but it is a
	// separate array and using it would silently plot another house if an export reordered it.
	const idx = $derived(house ? ticks.houseIds.indexOf(house.id) : -1);

	const circleChips = $derived(
		house ? Object.entries(house.circles).map(([type, group]) => ({ type, group })) : []
	);

	// --- SoC sparkline ----------------------------------------------------------

	const SPARK_H = 34;

	/** This house's SoC fraction at every tick, in tick order. */
	const socSeries = $derived(
		idx < 0 ? [] : ticks.socFrac.map((row) => Math.max(0, Math.min(1, row[idx] ?? 0)))
	);

	const sparkPoints = $derived(
		socSeries.map((v, i) => `${i + 0.5},${(1 - v) * SPARK_H}`).join(' ')
	);

	function argmin(xs: number[]): number {
		let best = 0;
		for (let i = 1; i < xs.length; i++) if (xs[i] < xs[best]) best = i;
		return best;
	}
	function argmax(xs: number[]): number {
		let best = 0;
		for (let i = 1; i < xs.length; i++) if (xs[i] > xs[best]) best = i;
		return best;
	}

	/** Text equivalent of the aria-hidden sparkline: its start, extremes and cursor. */
	const sparkSummary = $derived.by(() => {
		if (socSeries.length === 0) return '';
		const lo = argmin(socSeries);
		const hi = argmax(socSeries);
		return (
			`starts at ${pct(socSeries[0])}%, ` +
			`peaks ${pct(socSeries[hi])}% at ${hhmm(meta.tickTimes[hi])}, ` +
			`bottoms ${pct(socSeries[lo])}% at ${hhmm(meta.tickTimes[lo])}; ` +
			`${pct(socSeries[replay.tick] ?? 0)}% at the cursor (${hhmm(meta.tickTimes[replay.tick])}).`
		);
	});

	function onSparkClick(e: MouseEvent): void {
		const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
		if (r.width <= 0) return;
		const t = Math.floor(((e.clientX - r.left) / r.width) * meta.tickCount);
		replay.seek(t, maxTick);
	}

	function onSparkKeydown(e: KeyboardEvent): void {
		const step =
			e.key === 'ArrowRight' || e.key === 'ArrowUp'
				? 1
				: e.key === 'ArrowLeft' || e.key === 'ArrowDown'
					? -1
					: 0;
		if (step !== 0) {
			e.preventDefault();
			replay.seek(replay.tick + step, maxTick);
			return;
		}
		if (e.key === 'Home') {
			e.preventDefault();
			replay.seek(0, maxTick);
		} else if (e.key === 'End') {
			e.preventDefault();
			replay.seek(maxTick, maxTick);
		}
	}

	// --- message feed -----------------------------------------------------------

	let showAll = $state(false);

	const tickRows = $derived(
		house
			? (msgsByTick.get(replay.tick) ?? []).filter(
					(m) => m.from === house.id || m.to === house.id
				)
			: []
	);

	// Built from the tick keys in numeric order rather than the Map's insertion order,
	// so the "all ticks" list is chronological regardless of how the export was written.
	const allRows = $derived.by(() => {
		if (!house) return [];
		const out: Msg[] = [];
		for (const t of [...msgsByTick.keys()].sort((a, b) => a - b)) {
			for (const m of msgsByTick.get(t) ?? []) {
				if (m.from === house.id || m.to === house.id) out.push(m);
			}
		}
		return out;
	});

	const rows = $derived(showAll ? allRows.slice(0, ALL_CAP) : tickRows);

	// --- judge samples ----------------------------------------------------------

	const judgeRows = $derived(
		explanations === null || !house
			? []
			: explanations.samples
					.filter((s) => s.sender === house.id)
					.sort((a, b) => a.t - b.t)
	);

	function onJudgeClick(t: number): void {
		replay.seek(t, maxTick);
		onShowMessages();
	}
</script>

<div class="hp">
	{#if !house}
		<p class="muted empty">
			Click a house on the grid (or Tab to one and press Enter) to see who lives there, what its
			battery did across the day, and what it said.
		</p>
	{:else}
		<h3 class="hid mono">{house.id}</h3>

		<dl class="ident">
			<dt>type</dt>
			<dd>{house.have ? 'have (rooftop PV)' : 'have-not (no rooftop PV)'}</dd>
			<dt>PV peak</dt>
			<dd class="num">{house.pvKwPeak.toFixed(2)} kW</dd>
			<dt>battery</dt>
			<dd class="num">{house.batteryKwh.toFixed(2)} kWh</dd>
			<dt>critical load</dt>
			<dd class="num">{pct(house.criticalLoadFrac)}% of its own demand</dd>
			<dt>circles</dt>
			<dd>
				{#if circleChips.length === 0}
					<span class="muted">no owner or aggregator circle</span>
				{:else}
					{#each circleChips as c (c.type)}
						<span class="chip mono">{c.group}</span>
						<span class="muted ctype">({c.type})</span>
					{/each}
				{/if}
			</dd>
			<dt>prompting</dt>
			<dd>
				{#if house.defector}
					<span class="flag">defector</span>
					<span class="muted"
						>— selfish-prompted: hoards charge and declines requests. Its INFORM broadcasts stay
						truthful.</span
					>
				{:else}
					<span class="muted">cooperative (standard prompt)</span>
				{/if}
			</dd>
		</dl>

		<h4>State of charge across the day</h4>
		<svg
			class="spark"
			viewBox="0 0 {meta.tickCount} {SPARK_H}"
			preserveAspectRatio="none"
			role="slider"
			tabindex="0"
			aria-label="state of charge for {house.id} across the day — seek"
			aria-valuemin="0"
			aria-valuemax={maxTick}
			aria-valuenow={replay.tick}
			aria-valuetext="{hhmm(meta.tickTimes[replay.tick])}, state of charge {pct(
				socSeries[replay.tick] ?? 0
			)} percent"
			onclick={onSparkClick}
			onkeydown={onSparkKeydown}
		>
			<line x1="0" y1={SPARK_H} x2={meta.tickCount} y2={SPARK_H} class="spark-base" />
			<polyline class="spark-line" points={sparkPoints} />
			<rect x={replay.tick} y="0" width="1" height={SPARK_H} class="spark-cursor" />
		</svg>
		<p class="spark-caption muted">
			SoC as a fraction of this house's own {house.batteryKwh.toFixed(2)} kWh battery over all
			{meta.tickCount} ticks — {sparkSummary} Click or use the arrow keys to seek.
		</p>

		<h4>
			What {house.id} said
			{#if showAll}across the whole run{:else}at {hhmm(meta.tickTimes[replay.tick])}{/if}
		</h4>

		<label class="opt">
			<input type="checkbox" bind:checked={showAll} />
			show all ticks
		</label>

		<p class="count muted">
			{#if showAll}
				showing {allRows.length > ALL_CAP ? 'the first ' : ''}{rows.length} of {allRows.length}
				messages involving {house.id} across all ticks{allRows.length > ALL_CAP
					? ` (capped at ${ALL_CAP} — later ticks are not listed)`
					: ''}
			{:else}
				{rows.length}
				{rows.length === 1 ? 'message' : 'messages'} sent or received at {hhmm(
					meta.tickTimes[replay.tick]
				)}
			{/if}
		</p>

		{#if rows.length === 0}
			<p class="muted empty">No messages involve {house.id} here.</p>
		{:else}
			<ul class="rows">
				{#each rows as m (m.id)}
					<li class="row">
						<div class="head">
							<span class="pill" style="background: {PERF_COLORS[m.perf]}">{m.perf}</span>
							<span class="dir">{m.from === house.id ? 'sent to' : 'received from'}</span>
							<span class="pair mono">{m.from === house.id ? m.to : m.from}</span>
							{#if showAll}
								<span class="at mono">{hhmm(meta.tickTimes[m.t])}</span>
							{/if}
							{#if m.kwh !== undefined}
								<span class="num">{m.kwh.toFixed(2)} kWh</span>
							{/if}
							<span class="badge {m.authored ? 'authored' : ''}"
								>{m.authored ? 'LLM-authored' : 'templated'}</span
							>
						</div>
						{#if m.why}
							{#if m.authored}
								<blockquote class="why">{m.why}</blockquote>
							{:else}
								<p class="why templated muted">{m.why}</p>
							{/if}
						{/if}
					</li>
				{/each}
			</ul>
		{/if}

		<h4>Judge scores</h4>
		{#if explanations === null}
			<p class="muted note">
				No judged sample for this cell — judging ran on clean + defectors.
			</p>
		{:else if judgeRows.length === 0}
			<p class="muted note">
				No judged sample from {house.id}. The committed evaluation scored {explanations.nScored}
				rationales drawn from across this run, and none of them is this house's.
			</p>
		{:else}
			<ul class="judge">
				<!--
					Keyed by position, not by `(sender, t)`: that pair is NOT unique in the
					committed data — clean has one collision (r1c2 @ 32) and defectors two
					(r0c3 @ 65, r1c1 @ 36) — and Svelte 5 throws `each_key_duplicate` in prod
					as well as dev. The very ambiguity the note below discloses is what makes
					the pair unusable as a key. Index keying is safe here because `judgeRows`
					is `$derived` and fully recreated whenever the selected house changes.
				-->
				{#each judgeRows as s, i (i)}
					<li>
						<button type="button" onclick={() => onJudgeClick(s.t)}>
							<span class="mono">{hhmm(meta.tickTimes[s.t])}</span>
							· accuracy <span class="num">{s.stateAccuracy}</span>
							· actionability <span class="num">{s.actionability}</span>
							· consistency <span class="num">{s.consistency}</span>
						</button>
					</li>
				{/each}
			</ul>
			<p class="muted note">
				Each score is 1–5. Scores attach to a sampled rationale from this tick; where several
				rationales share the tick the pairing is ambiguous (the committed eval predates
				per-message ids). Selecting a row seeks the replay to that tick and opens the Messages
				tab filtered to this house.
			</p>
		{/if}
	{/if}
</div>

<style>
	.hp {
		display: grid;
		gap: 0.6rem;
		min-width: 0;
	}

	.empty {
		margin: 0;
		font-size: 0.82rem;
		line-height: 1.5;
	}

	.hid {
		margin: 0;
		font-size: 1rem;
	}

	h4 {
		margin: 0.3rem 0 0;
		font-size: 0.78rem;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--muted);
	}

	.ident {
		margin: 0;
		display: grid;
		grid-template-columns: max-content minmax(0, 1fr);
		gap: 0.2rem 0.6rem;
		font-size: 0.78rem;
	}

	.ident dt {
		color: var(--muted);
	}

	.ident dd {
		margin: 0;
		min-width: 0;
		overflow-wrap: anywhere;
	}

	.chip {
		border: 1px solid var(--border);
		border-radius: 999px;
		padding: 0.02rem 0.4rem;
		font-size: 0.7rem;
	}

	.ctype {
		font-size: 0.7rem;
	}

	.flag {
		color: #f87171;
		border: 1px solid #7f3131;
		border-radius: 999px;
		padding: 0.02rem 0.4rem;
		font-size: 0.7rem;
	}

	.spark {
		width: 100%;
		height: 44px;
		display: block;
		cursor: pointer;
	}

	.spark:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.spark-base {
		stroke: var(--border);
		stroke-width: 1;
	}

	.spark-line {
		fill: none;
		stroke: var(--accent);
		stroke-width: 1.5;
		vector-effect: non-scaling-stroke;
	}

	.spark-cursor {
		fill: var(--text);
		opacity: 0.55;
	}

	.spark-caption,
	.note {
		margin: 0;
		font-size: 0.72rem;
		line-height: 1.45;
	}

	.opt {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		font-size: 0.75rem;
	}

	.count {
		margin: 0;
		font-size: 0.72rem;
	}

	.rows {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.45rem;
		max-height: 24rem;
		overflow-y: auto;
		min-width: 0;
	}

	.row {
		min-width: 0;
		border: 1px solid var(--border);
		border-radius: 6px;
		padding: 0.4rem 0.55rem;
		background: var(--bg);
	}

	.head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.75rem;
	}

	.pill {
		color: var(--bg);
		border-radius: 4px;
		padding: 0.05rem 0.35rem;
		font-size: 0.68rem;
		font-weight: 600;
		letter-spacing: 0.03em;
	}

	.dir {
		color: var(--muted);
	}

	.at,
	.num {
		font-variant-numeric: tabular-nums;
	}

	.badge {
		margin-left: auto;
		border: 1px solid var(--border);
		border-radius: 999px;
		padding: 0.05rem 0.4rem;
		font-size: 0.68rem;
		color: var(--muted);
	}

	.badge.authored {
		color: var(--accent);
		border-color: #7a6a15;
	}

	.why {
		margin: 0.35rem 0 0;
		overflow-wrap: anywhere;
		font-size: 0.75rem;
		line-height: 1.45;
		border-left: 2px solid var(--border);
		padding-left: 0.5rem;
	}

	.why.templated {
		max-width: 100%;
		border-left: none;
		padding-left: 0;
		font-size: 0.72rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.judge {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.3rem;
	}

	.judge button {
		width: 100%;
		text-align: left;
		background: var(--bg);
		border: 1px solid var(--border);
		border-radius: 6px;
		color: var(--text);
		font: inherit;
		font-size: 0.75rem;
		padding: 0.3rem 0.5rem;
		cursor: pointer;
	}

	.judge button:hover {
		border-color: var(--accent);
	}

	.judge button:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
</style>
