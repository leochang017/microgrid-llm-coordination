<!--
	Message-flow overlay: one thin arc per message SENT at the currently scrubbed tick,
	drawn on the neighborhood canvas.

	This is a separate component rather than a fourth layer inside `NeighborhoodGrid`
	on purpose — the grid already carries houses, transfers and circles+lattice, and two
	reviews flagged that piling more onto it is the wrong direction. It renders a bare
	`<g>`, so the parent drops it inside its own `<svg>` and the two share one viewBox
	via `$lib/geom` without sharing a file.

	Reading the arcs:
	  * COLOUR is the performative (`PERF_COLORS`) — decoration only. Every message is
	    also listed as text in the MessagePanel beside the grid, and the grid's own
	    aria-label carries this tick's message count, so nothing here is colour-only.
	  * SHAPE is the outcome: a delivered message is a solid arc, a dropped one is dashed
	    at half opacity. Curvature is signed by direction, so a->b and b->a bow to
	    opposite sides instead of stacking on one line.

	The layer is `aria-hidden` + `pointer-events: none`. Both are deliberate: 80 arcs
	crossing the cells would intercept hover and steal the house rects' click target,
	and the panel next to it is the accessible equivalent (same precedent as the strip
	chart's summary line). No `<title>` tooltips here for the same reason.

	CAP: at most `MAX_ARCS` arcs per tick, because the busiest committed tick sends 177
	messages and drawing them all is unreadable. Priority is non-INFORM first, then
	authored INFORMs, then the rest — note that `messages.json` contains zero INFORM
	rows in all four cells (every INFORM in these runs is templated and the exporter
	drops those; the INFORM story lives in `CellTicks.informCounts`), so the INFORM tiers
	are dead today by construction and exist only so the rule is honest if that changes.
	The "+N more" note counts messages that had geometry and were cut by the cap — NOT
	messages skipped for having no drawable endpoints, which would make the note a lie.
-->
<script lang="ts">
	import { PERF_COLORS } from '$lib/colors';
	import { houseCenters, VIEW_H } from '$lib/geom';
	import type { CellMeta, Msg } from '$lib/types';
	import type { ReplayState } from '$lib/replay.svelte';

	interface Props {
		meta: CellMeta;
		msgsByTick: Map<number, Msg[]>;
		state: ReplayState;
	}

	const { meta, msgsByTick, state }: Props = $props();

	/** Above this many arcs the canvas is noise, not information. */
	const MAX_ARCS = 80;
	/** Pull-back from each house centre so an arc starts outside the cell's label block. */
	const TRIM = 26;
	/** Bow height as a fraction of the chord, signed by direction. */
	const BOW = 0.16;

	const centers = $derived(houseCenters(meta));

	function rank(m: Msg): number {
		if (m.perf !== 'INFORM') return 0;
		return m.authored ? 1 : 2;
	}

	interface Arc {
		key: string;
		d: string;
		color: string;
		dropped: boolean;
	}

	const layer = $derived.by<{ arcs: Arc[]; hidden: number }>(() => {
		const msgs = msgsByTick.get(state.tick) ?? [];
		// Stable sort by tier; within a tier the export's own order is kept.
		const ordered = msgs.map((m, i) => ({ m, i })).sort((a, b) => rank(a.m) - rank(b.m) || a.i - b.i);

		const arcs: Arc[] = [];
		let drawable = 0;
		for (const { m } of ordered) {
			const a = centers.get(m.from);
			const b = centers.get(m.to);
			if (!a || !b) continue;
			const dx = b[0] - a[0];
			const dy = b[1] - a[1];
			const len = Math.hypot(dx, dy);
			if (len <= 2 * TRIM) continue;
			drawable += 1;
			if (arcs.length >= MAX_ARCS) continue;
			const ux = dx / len;
			const uy = dy / len;
			const x1 = a[0] + ux * TRIM;
			const y1 = a[1] + uy * TRIM;
			const x2 = b[0] - ux * TRIM;
			const y2 = b[1] - uy * TRIM;
			// Perpendicular of the direction vector: flipping from/to flips its sign, so the
			// two directions of one pair bow apart instead of overdrawing each other.
			const cx = (x1 + x2) / 2 - uy * len * BOW;
			const cy = (y1 + y2) / 2 + ux * len * BOW;
			arcs.push({
				key: m.id,
				d: `M ${x1.toFixed(1)} ${y1.toFixed(1)} Q ${cx.toFixed(1)} ${cy.toFixed(1)} ${x2.toFixed(1)} ${y2.toFixed(1)}`,
				color: PERF_COLORS[m.perf],
				dropped: m.outcome === 'dropped'
			});
		}
		return { arcs, hidden: Math.max(0, drawable - arcs.length) };
	});
</script>

<g class="messages" aria-hidden="true">
	{#each layer.arcs as arc (arc.key)}
		<path class="arc" class:dropped={arc.dropped} d={arc.d} stroke={arc.color} fill="none" />
	{/each}
	{#if layer.hidden > 0}
		<text class="more" x="8" y={VIEW_H - 6}>+{layer.hidden} more messages this tick</text>
	{/if}
</g>

<style>
	.messages {
		pointer-events: none;
	}

	.arc {
		stroke-width: 1.4;
		opacity: 0.85;
	}

	.arc.dropped {
		opacity: 0.5;
		stroke-dasharray: 4 4;
	}

	.more {
		fill: var(--muted);
		font-size: 12px;
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
	}
</style>
