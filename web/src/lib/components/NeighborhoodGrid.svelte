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
-->
<script lang="ts">
	import { socColor } from '$lib/colors';
	import type { CellMeta, CellTicks } from '$lib/types';
	import type { ReplayState } from '$lib/replay.svelte';

	interface Props {
		meta: CellMeta;
		ticks: CellTicks;
		state: ReplayState;
	}

	const { meta, ticks, state }: Props = $props();

	const CELL = 96;
	const STEP = 109;
	const ORIGIN = 6;

	function cellX(col: number): number {
		return ORIGIN + col * STEP;
	}
	function cellY(row: number): number {
		return ORIGIN + row * STEP;
	}

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
</script>

<svg
	class="grid"
	viewBox="0 0 660 560"
	role="group"
	aria-label="Neighborhood grid, {meta.rows} by {meta.cols} houses, coloured by state of charge"
>
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
</svg>

<style>
	.grid {
		display: block;
		width: 100%;
		height: auto;
	}

	.cell {
		cursor: pointer;
	}

	.cell:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

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
