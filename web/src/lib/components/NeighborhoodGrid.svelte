<!--
	SoC neighborhood grid — one SVG cell per household, colour = state of charge
	(viridis, dark purple empty -> bright yellow full) at the currently scrubbed tick.

	Every non-colour fact gets its own SHAPE, not just a colour, so nothing here is
	colour-only: "have" is a light stroke ring + a small sun dot, "defector" is a red
	corner wedge, "unmet load this tick" is an amber corner triangle. All three (plus
	the SoC percentage itself) are also spelled out in the cell's `aria-label` and
	`<title>` tooltip, so a screen reader or a mouse-hover gets the same facts a
	sighted user reads off the shapes.

	The interactive element is the `<rect>` itself (per spec): tabindex + role=button +
	aria-label, so keyboard users can Tab through houses and press Enter/Space to
	select one. Every decorative overlay (sun dot, wedge, triangle, label text, the
	selected-house outline) sits on top with `pointer-events: none` so it can never
	steal the click/keyboard target away from the rect underneath it.

	The wrapper <svg> is `role="group"`, deliberately NOT `role="img"`: the `img` role is
	children-presentational in WAI-ARIA, so conforming assistive tech would expose the
	whole grid as a single graphic and prune the subtree — every house rect would stay
	keyboard-focusable while not being exposed as a button. `group` keeps the same
	labelled container without hiding its children.

	Three optional overlays sit on this same canvas:

	* TRANSFERS (`state.showTransfers`) — one arrow per settled transfer at the current
	  tick, drawn on top of the houses. Direction is an arrowhead (shape, not colour),
	  magnitude is stroke width, and the exact pair + kW is in each arrow's `<title>`;
	  the svg's own aria-label also carries the transfer count for this tick, so the
	  layer is never colour-only. The arrows are the ONLY overlay that keeps pointer
	  events, because a `<title>` tooltip needs hit-testing to appear — they are trimmed
	  30px at each end so most of a same-row arrow lies in the gutter between cells, but
	  where an arrow does cross a cell its stroke intercepts hover along that stripe.
	  The house rect stays clickable everywhere else and fully keyboard-reachable, and
	  the layer is toggleable.
	* MESSAGES (`state.showMessages`, Task 7) — one thin arc per message sent at this tick.
	  That layer lives in its own component (`MessageArcs.svelte`) rather than inline here:
	  this file was already carrying three layers, and it renders a `<g>` that drops into
	  the same `<svg>`, sharing the canvas contract through `$lib/geom` instead of the file.
	  It is aria-hidden; the MessagePanel beside the grid is its text equivalent, and the
	  svg's aria-label carries this tick's message count.
	* CIRCLES (`state.showCircles`) — the geographic 4-neighbour lattice as faint dashed
	  lines drawn OVER the houses (deliberately — see the comment at the lattice markup;
	  underneath, the 13-unit gutters leave it invisible), plus corner ribbons on
	  trust-circle members. Ribbons are
	  `pointer-events: none` on purpose: the rect's existing aria-label/<title> already
	  names every circle the house belongs to, so the ribbon needs no tooltip of its own
	  and should not steal the cell's click target to provide one.
-->
<script lang="ts">
	import { socColor } from '$lib/colors';
	import { circleGroups, groupsByHouse } from '$lib/circles';
	import { CELL, VIEW_H, VIEW_W, cellX, cellY, houseCenters } from '$lib/geom';
	import MessageArcs from './MessageArcs.svelte';
	import type { CellMeta, CellTicks, Msg } from '$lib/types';
	import type { ReplayState } from '$lib/replay.svelte';

	interface Props {
		meta: CellMeta;
		ticks: CellTicks;
		msgsByTick: Map<number, Msg[]>;
		state: ReplayState;
	}

	const { meta, ticks, msgsByTick, state }: Props = $props();

	function pct(frac: number): number {
		return Math.round(Math.max(0, Math.min(1, frac)) * 100);
	}

	/** Shared by the rect's aria-label and its <title> hover tooltip — one source of truth. */
	function describe(idx: number): string {
		const h = meta.houses[idx];
		const frac = ticks.socFrac[state.tick]?.[idx] ?? 0;
		const parts = [`house ${h.id} — SoC ${pct(frac)}%`, h.have ? 'have' : 'have-not'];
		const circleNames = Object.values(h.circles);
		if (circleNames.length > 0) parts.push(circleNames.join(', '));
		if (h.defector) parts.push('defector');
		if ((ticks.unmetKwh[state.tick]?.[idx] ?? 0) > 0) parts.push('unmet load this tick');
		return parts.join(', ');
	}

	function select(id: string): void {
		state.selectedHouse = state.selectedHouse === id ? null : id;
	}

	function onKeydown(e: KeyboardEvent, id: string): void {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			select(id);
		}
	}

	// --- overlay geometry -------------------------------------------------------

	/** How far each arrow is pulled back from both house centres, in user units. */
	const TRIM = 30;
	/** Innermost ribbon band's distance from the cell corner; clears the unmet triangle. */
	const RIBBON_START = 20;
	const RIBBON_WIDTH = 6;
	const RIBBON_GAP = 10;

	const groups = $derived(circleGroups(meta));
	const byHouse = $derived(groupsByHouse(groups));

	const centers = $derived(houseCenters(meta));

	/** Geographic 4-neighbour adjacency, derived from row/col (it is not in `meta.circles`). */
	const lattice = $derived.by(() => {
		const at = new Map(meta.houses.map((h) => [`${h.row},${h.col}`, h]));
		const out: { key: string; x1: number; y1: number; x2: number; y2: number }[] = [];
		for (const h of meta.houses) {
			for (const [dr, dc] of [
				[0, 1],
				[1, 0]
			]) {
				const n = at.get(`${h.row + dr},${h.col + dc}`);
				if (!n) continue;
				const a = centers.get(h.id);
				const b = centers.get(n.id);
				if (!a || !b) continue;
				out.push({ key: `${h.id}-${n.id}`, x1: a[0], y1: a[1], x2: b[0], y2: b[1] });
			}
		}
		return out;
	});

	const transfers = $derived(state.showTransfers ? (ticks.transfers[state.tick] ?? []) : []);

	/** Arrow endpoints, trimmed at both ends; self-pairs and unknown ids are skipped. */
	const arrows = $derived.by(() =>
		transfers.flatMap((tr, i) => {
			const a = centers.get(tr.from);
			const b = centers.get(tr.to);
			if (!a || !b) return [];
			const dx = b[0] - a[0];
			const dy = b[1] - a[1];
			const len = Math.hypot(dx, dy);
			if (len <= 2 * TRIM) return [];
			const ux = dx / len;
			const uy = dy / len;
			return [
				{
					key: `${tr.from}>${tr.to}#${i}`,
					x1: a[0] + ux * TRIM,
					y1: a[1] + uy * TRIM,
					x2: b[0] - ux * TRIM,
					y2: b[1] - uy * TRIM,
					width: Math.min(6, Math.max(1.5, tr.kw * 1.2)),
					label: `${tr.from} → ${tr.to} · ${tr.kw.toFixed(2)} kW`
				}
			];
		})
	);

	function ribbonPath(x: number, y: number, slot: number): string {
		const a = RIBBON_START + slot * RIBBON_GAP;
		const b = a + RIBBON_WIDTH;
		const bottom = y + CELL;
		return `M ${x} ${bottom - a} L ${x} ${bottom - b} L ${x + b} ${bottom} L ${x + a} ${bottom} Z`;
	}

	const gridLabel = $derived(
		`Neighborhood grid, ${meta.rows} by ${meta.cols} houses, coloured by state of charge` +
			(state.showTransfers ? `; ${transfers.length} transfers at this tick` : '') +
			(state.showMessages
				? `; ${(msgsByTick.get(state.tick) ?? []).length} messages sent at this tick, listed in the message panel`
				: '')
	);
</script>

<svg class="grid" viewBox="0 0 {VIEW_W} {VIEW_H}" role="group" aria-label={gridLabel}>
	<defs>
		<!-- userSpaceOnUse so the head stays one size while the shaft width encodes kW. -->
		<marker
			id="transfer-arrowhead"
			markerUnits="userSpaceOnUse"
			markerWidth="10"
			markerHeight="10"
			refX="8"
			refY="5"
			orient="auto"
		>
			<!-- Colour comes from `--transfer-color` on `.grid` so the head and the shaft
			     below cannot drift apart. -->
			<path class="arrowhead" d="M 0 0 L 9 5 L 0 10 Z" />
		</marker>
	</defs>

	{#each meta.houses as house, idx (house.id)}
		{@const x = cellX(house.col)}
		{@const y = cellY(house.row)}
		{@const frac = ticks.socFrac[state.tick]?.[idx] ?? 0}
		{@const unmet = (ticks.unmetKwh[state.tick]?.[idx] ?? 0) > 0}
		{@const selected = state.selectedHouse === house.id}
		{@const label = describe(idx)}
		<g class="house">
			<rect
				class="cell"
				x={x}
				y={y}
				width={CELL}
				height={CELL}
				rx="8"
				fill={socColor(frac)}
				stroke={house.have ? '#e6e9ee' : 'none'}
				stroke-width={house.have ? 2.5 : 0}
				tabindex="0"
				role="button"
				aria-label={label}
				aria-pressed={selected}
				onclick={() => select(house.id)}
				onkeydown={(e) => onKeydown(e, house.id)}
			>
				<title>{label}</title>
			</rect>

			{#if house.have}
				<circle class="sun" cx={x + CELL - 11} cy={y + 11} r="5" />
			{/if}

			{#if state.showCircles}
				{#each byHouse.get(house.id) ?? [] as g (g.group)}
					<path class="ribbon" d={ribbonPath(x, y, g.slot)} fill={g.color} />
				{/each}
			{/if}

			{#if house.defector}
				<path
					class="defector-wedge"
					d="M {x + CELL - 18} {y + CELL} L {x + CELL} {y + CELL} L {x + CELL} {y + CELL - 18} Z"
				>
					<title>{house.id} — defector (selfish-prompted: hoards, declines requests)</title>
				</path>
			{/if}

			{#if unmet}
				<path
					class="unmet-warn"
					d="M {x + 7} {y + CELL - 4} L {x + 19} {y + CELL - 4} L {x + 13} {y + CELL - 16} Z"
				>
					<title>{house.id} — unmet load this tick</title>
				</path>
			{/if}

			{#if selected}
				<rect
					class="selected-outline"
					x={x - 2}
					y={y - 2}
					width={CELL + 4}
					height={CELL + 4}
					rx="10"
					fill="none"
				/>
			{/if}

			<rect class="label-bg" x={x + 3} y={y + 3} width="42" height="27" rx="4" />
			<text class="label" x={x + 7} y={y + 14}>{house.id}</text>
			<text class="soc" x={x + 7} y={y + 26}>{pct(frac)}%</text>
		</g>
	{/each}

	<!-- Above the houses, not under them: the cells occupy 96 of the 109-unit pitch, so a
	     lattice drawn underneath survives only as 13-unit stubs in the gutters and reads as
	     nothing at all. Drawn on top it is legible as a lattice while staying faint, and it
	     cannot be confused with a transfer (grey dashes, no arrowhead, always symmetric). -->
	{#if state.showCircles}
		<g class="lattice" aria-hidden="true">
			{#each lattice as edge (edge.key)}
				<line x1={edge.x1} y1={edge.y1} x2={edge.x2} y2={edge.y2} />
			{/each}
		</g>
	{/if}

	<!-- Under the transfer arrows on purpose: transfers are the settled physics and keep
	     both the visual and the hit-testing priority; message arcs are pointer-inert. -->
	{#if state.showMessages}
		<MessageArcs {meta} {msgsByTick} {state} />
	{/if}

	{#if state.showTransfers}
		<g class="transfers">
			{#each arrows as arrow (arrow.key)}
				<line
					class="arrow"
					x1={arrow.x1}
					y1={arrow.y1}
					x2={arrow.x2}
					y2={arrow.y2}
					stroke-width={arrow.width}
					marker-end="url(#transfer-arrowhead)"
				>
					<title>{arrow.label}</title>
				</line>
			{/each}
		</g>
	{/if}
</svg>

<style>
	.grid {
		/* The single definition of the transfer green: the arrowhead's fill and the
		   shaft's stroke both read it, so they can never drift apart. */
		--transfer-color: #4ade80;
		display: block;
		width: 100%;
		height: auto;
	}

	.arrowhead {
		fill: var(--transfer-color);
	}

	.cell {
		cursor: pointer;
	}

	.cell:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.lattice line {
		stroke: var(--muted);
		stroke-width: 1.5;
		stroke-dasharray: 3 6;
		opacity: 0.5;
	}

	.arrow {
		stroke: var(--transfer-color);
		stroke-linecap: round;
		stroke-dasharray: 7 5;
		animation: flow 0.9s linear infinite;
	}

	@keyframes flow {
		to {
			stroke-dashoffset: -12;
		}
	}

	/* Explicit kill-switch. app.css already zeroes `animation` on `*` under
	   prefers-reduced-motion; this keeps the guarantee local to the component that
	   owns the only moving thing on the page. */
	@media (prefers-reduced-motion: reduce) {
		.arrow {
			animation: none;
		}
	}

	.lattice,
	.ribbon,
	.sun,
	.defector-wedge,
	.unmet-warn,
	.selected-outline,
	.label-bg,
	.label,
	.soc {
		pointer-events: none;
	}

	.sun {
		fill: #fde725;
		stroke: #171b22;
		stroke-width: 1;
	}

	.defector-wedge {
		fill: #f87171;
	}

	.unmet-warn {
		fill: #fbbf24;
	}

	.selected-outline {
		stroke: var(--accent);
		stroke-width: 3;
	}

	.label-bg {
		fill: rgba(14, 17, 22, 0.45);
	}

	.label,
	.soc {
		font-size: 10px;
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-variant-numeric: tabular-nums;
	}

	.label {
		/* Spec calls for a "muted" house-id label; --muted still reads clearly against the
		   dark backdrop rect regardless of the cell's own viridis fill underneath it. */
		fill: var(--muted);
	}

	.soc {
		/* The SoC percentage is the number the label-bg backdrop exists to protect — give it
		   full-text contrast, one step up from the muted id label above it. */
		fill: var(--text);
		opacity: 0.9;
	}
</style>
