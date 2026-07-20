<!--
	Per-tick message panel: every negotiation message SENT at the currently scrubbed tick,
	as text, in DOM order — this is the accessible equivalent of the arc overlay next to it.

	`Msg.t` is the tick a message was SENT on (the exporter reads `t_sent`). The bus
	delivers one tick later — `MessageBus.deliver_pending` in `sim/agents/protocol.py`
	admits a message once `t_sent + dt <= now` — so a row marked `delivered` here reached
	its recipient's inbox on the FOLLOWING tick, and `pending` means the run ended before
	that happened. The outcome copy below is written against that, not against a guess.

	The two drop reasons are the simulator's own strings and their explanations were read
	off `MessageBus.send` (`sim/agents/protocol.py:119-185`) rather than inferred:
	  * `budget_overflow` — the budget counter is keyed `(t_sent, sender)`, so it is a
	    PER-SENDER, PER-TICK message cap; the (n+1)th message a house sends in a tick is
	    refused before it ever enters the queue.
	  * `comm_drop` — a probabilistic link failure. The bus picks the circle connecting
	    the two houses (`_circle_between`) and drops with that circle's configured
	    probability; on the comm cell those are geographic 0.30 / dr_aggregator 0.10 /
	    owner 0.05.
	A third reason, `invalid_recipient`, exists in the simulator but appears on zero rows
	in the four committed cells, so it gets the generic badge rather than bespoke copy.

	INFORM strip: `messages.json` contains ZERO INFORM rows in any cell — every INFORM in
	these runs is templated and the exporter downsamples templated INFORMs out — so the
	INFORM story is only visible as the per-tick `{sent, delivered, dropped}` aggregate,
	which is exactly what this strip renders. There is deliberately no INFORM filter chip:
	it could never match a row.

	Filters are text controls with `aria-pressed`/`checked`, never colour-only, and the
	performative pills carry their name as text next to the colour.
-->
<script lang="ts">
	import { PERF_COLORS } from '$lib/colors';
	import type { CellMeta, CellTicks, Msg, Performative } from '$lib/types';
	import type { ReplayState } from '$lib/replay.svelte';

	interface Props {
		meta: CellMeta;
		msgsByTick: Map<number, Msg[]>;
		informCounts: CellTicks['informCounts'];
		state: ReplayState;
	}

	// Destructured under a different local name on purpose: a binding literally called
	// `state` shadows the `$state` rune for the compiler, and this component uses runes.
	const { meta, msgsByTick, informCounts, state: replay }: Props = $props();

	/** Rendering order for the filter chips; INFORM is deliberately absent (see header). */
	const PERF_ORDER: Performative[] = ['REQUEST', 'OFFER', 'ACCEPT', 'COUNTER', 'REJECT'];

	const tickMsgs = $derived(msgsByTick.get(replay.tick) ?? []);

	/** Only offer a chip for a performative this cell actually ships. */
	const perfsPresent = $derived.by(() => {
		const seen = new Set<Performative>();
		for (const list of msgsByTick.values()) for (const m of list) seen.add(m.perf);
		return PERF_ORDER.filter((p) => seen.has(p));
	});

	// A Set of the perfs currently switched OFF keeps "everything on" as the default
	// without having to seed it from the data. It is reassigned (never mutated in
	// place) on every toggle, so a plain Set inside `$state` is reactive enough.
	let perfOff = $state<ReadonlySet<Performative>>(new Set());
	let authoredOnly = $state(false);

	// House filter follows the grid selection, but is independently clearable: clicking
	// "clear" empties it without deselecting the house on the grid, and the effect below
	// only re-fires when `replay.selectedHouse` itself changes. A hand-off from another
	// tab (HousePanel's judge rows) needs no extra signal: the host page renders the two
	// tab panels under `{#if}/{:else}`, so this component is destroyed on tab switch and
	// remounts with `houseFilter = null`, and the effect re-applies the selection on mount.
	let houseFilter = $state<string | null>(null);
	$effect(() => {
		houseFilter = replay.selectedHouse;
	});

	const rows = $derived(
		tickMsgs.filter(
			(m) =>
				!perfOff.has(m.perf) &&
				(!authoredOnly || m.authored) &&
				(houseFilter === null || m.from === houseFilter || m.to === houseFilter)
		)
	);

	const inform = $derived(
		informCounts[replay.tick] ?? { sent: 0, delivered: 0, dropped: 0 }
	);

	// The exporter tallies `delivered` and `dropped` only (`export_demo_data.py`), so
	// the remainder is the third outcome the bus can record: `pending_at_end`. The bus
	// admits a message only once `t_sent + dt <= now` (`MessageBus.deliver_pending`,
	// sim/agents/protocol.py), so INFORMs broadcast on the FINAL tick never get a
	// delivery pass — the run ends first. Measured: this is non-zero at tick 95 and
	// nowhere else, in all four cells. Rendering only `sent · delivered · dropped`
	// there showed 126 broadcasts vanishing with no account of where they went.
	const informPending = $derived(Math.max(0, inform.sent - inform.delivered - inform.dropped));

	// Built as one string rather than inline markup: an `{#if}` inside the sentence
	// eats the separator's surrounding whitespace and renders "0 dropped· 126 pending".
	const informStrip = $derived(
		`INFORMs: ${inform.sent} sent · ${inform.delivered} delivered · ${inform.dropped} dropped` +
			(informPending > 0 ? ` · ${informPending} pending` : '')
	);

	function togglePerf(p: Performative): void {
		const next = new Set(perfOff);
		if (next.has(p)) next.delete(p);
		else next.add(p);
		perfOff = next;
	}

	interface Badge {
		label: string;
		tone: 'ok' | 'bad' | 'warn' | 'idle';
		help: string;
	}

	function badge(m: Msg): Badge {
		if (m.outcome === 'delivered') {
			return {
				label: 'delivered',
				tone: 'ok',
				help: "entered the bus queue and reached the recipient's inbox on the following tick"
			};
		}
		if (m.outcome === 'pending_at_end') {
			return {
				label: 'pending',
				tone: 'idle',
				help: 'still in the bus queue when the run ended — the bus delivers one tick after a message is sent'
			};
		}
		if (m.reason === 'comm_drop') {
			return {
				label: 'dropped: comm_drop',
				tone: 'bad',
				help: 'the link failed — the bus drops a message with the probability configured for the circle connecting these two houses'
			};
		}
		if (m.reason === 'budget_overflow') {
			return {
				label: 'dropped: budget_overflow',
				tone: 'warn',
				help: 'the sender had already used its per-tick message budget — the bus refused this one before it entered the queue'
			};
		}
		return {
			label: `dropped${m.reason ? `: ${m.reason}` : ''}`,
			tone: 'bad',
			help: 'the bus refused this message, so the recipient never saw it'
		};
	}
</script>

<div class="mp">
	<p class="inform-strip mono">
		{informStrip}
	</p>
	{#if informPending > 0}
		<p class="inform-note muted">
			Pending INFORMs were still in the bus queue when the run ended: the bus delivers a
			message on the tick after it is sent, so anything broadcast at the last tick never gets
			a delivery pass. They were not lost.
		</p>
	{/if}
	{#if meta.slug === 'comm'}
		<p class="inform-note muted">
			INFORMs are the per-tick state broadcasts agents learn their neighbours' needs from, and
			the simulator sends them last in each tick — so under this cell's per-sender message
			budget they are the first traffic to lose its slot, on top of the per-circle link drops.
			That loss is visible only in this strip: templated INFORMs are downsampled out of the
			message list below.
		</p>
	{/if}

	<div class="filters">
		<div class="chips">
			{#each perfsPresent as p (p)}
				<button
					type="button"
					class="chip"
					aria-pressed={!perfOff.has(p)}
					onclick={() => togglePerf(p)}
				>
					<span class="swatch" style="background: {PERF_COLORS[p]}" aria-hidden="true"></span>
					{p}
				</button>
			{/each}
		</div>
		<div class="opts">
			<label class="opt">
				<input type="checkbox" bind:checked={authoredOnly} />
				authored only
			</label>
			{#if houseFilter !== null}
				<span class="opt">
					<span class="mono">{houseFilter}</span> only
					<button type="button" class="clear" onclick={() => (houseFilter = null)}>clear</button>
				</span>
			{/if}
		</div>
	</div>

	<p class="count muted">
		{rows.length} of {tickMsgs.length} messages sent at tick {replay.tick}
	</p>

	{#if rows.length === 0}
		<p class="muted empty">No messages match at this tick.</p>
	{:else}
		<ul class="rows">
			{#each rows as m (m.id)}
				{@const b = badge(m)}
				<li class="row">
					<div class="head">
						<span class="pill" style="background: {PERF_COLORS[m.perf]}">{m.perf}</span>
						<span class="pair mono">{m.from} → {m.to}</span>
						{#if m.kwh !== undefined}
							<span class="kwh mono">{m.kwh.toFixed(2)} kWh</span>
						{/if}
						<span class="badge {b.tone}" title={b.help}>{b.label}</span>
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
</div>

<style>
	.mp {
		display: grid;
		gap: 0.6rem;
		/* Grid items default to `min-width: auto`, which lets a child size to its widest
		   unbreakable content — and `.why.templated` below is deliberately one nowrap line.
		   Without this the whole list grows past the aside and the rows clip. */
		min-width: 0;
	}

	.inform-strip {
		margin: 0;
		font-size: 0.78rem;
		border: 1px solid var(--border);
		border-radius: 6px;
		padding: 0.35rem 0.6rem;
		background: var(--bg);
		font-variant-numeric: tabular-nums;
	}

	.inform-note {
		margin: -0.2rem 0 0;
		font-size: 0.75rem;
		line-height: 1.45;
	}

	.filters {
		display: grid;
		gap: 0.4rem;
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
	}

	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		background: var(--bg);
		color: var(--muted);
		border: 1px solid var(--border);
		border-radius: 999px;
		padding: 0.15rem 0.5rem;
		font: inherit;
		font-size: 0.7rem;
		cursor: pointer;
	}

	.chip[aria-pressed='true'] {
		color: var(--text);
		border-color: var(--accent);
	}

	.chip[aria-pressed='false'] .swatch {
		opacity: 0.25;
	}

	.chip:focus-visible,
	.clear:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.swatch {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 50%;
		flex: none;
	}

	.opts {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.75rem;
		font-size: 0.75rem;
	}

	.opt {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
	}

	.clear {
		background: none;
		border: none;
		color: var(--accent);
		font: inherit;
		font-size: 0.75rem;
		padding: 0;
		cursor: pointer;
		text-decoration: underline;
	}

	.count {
		margin: 0;
		font-size: 0.72rem;
	}

	.empty {
		margin: 0;
		font-size: 0.8rem;
	}

	.rows {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.45rem;
		/* The busiest committed tick sends 177 messages; the list scrolls inside the
		   panel rather than stretching the page next to the grid. */
		max-height: 34rem;
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

	.kwh {
		font-variant-numeric: tabular-nums;
	}

	.badge {
		margin-left: auto;
		border: 1px solid var(--border);
		border-radius: 999px;
		padding: 0.05rem 0.4rem;
		font-size: 0.68rem;
		cursor: help;
	}

	.badge.ok {
		color: #4ade80;
		border-color: #2f6f47;
	}

	.badge.bad {
		color: #f87171;
		border-color: #7f3131;
	}

	.badge.warn {
		color: #fbbf24;
		border-color: #7a5a15;
	}

	.badge.idle {
		color: var(--muted);
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
</style>
