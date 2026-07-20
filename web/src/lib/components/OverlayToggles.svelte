<!--
	Overlay controls for the replay grid, plus the legend that decodes the trust-circle
	ribbons when that overlay is on.

	These live outside `NeighborhoodGrid` on purpose: that component's root element is
	the <svg> itself, and it already carries the SoC cells and both overlays. Controls
	and their key belong beside it, not inside its canvas.

	Each button is a real toggle: `aria-pressed` carries the on/off state, and the
	pressed state is also drawn with a border + filled dot rather than colour alone.
-->
<script lang="ts">
	import { circleGroups } from '$lib/circles';
	import type { CellMeta } from '$lib/types';
	import type { ReplayState } from '$lib/replay.svelte';

	interface Props {
		meta: CellMeta;
		state: ReplayState;
	}

	const { meta, state }: Props = $props();

	const groups = $derived(circleGroups(meta));

	const ORDINALS = ['1st', '2nd', '3rd', '4th', '5th'];
	function bandLabel(slot: number): string {
		return `${ORDINALS[slot] ?? `${slot + 1}th`} band from the corner`;
	}
</script>

<div class="toggles">
	<button
		type="button"
		class="toggle"
		aria-pressed={state.showTransfers}
		onclick={() => (state.showTransfers = !state.showTransfers)}
	>
		<span class="dot" aria-hidden="true"></span> Transfers
	</button>
	<button
		type="button"
		class="toggle"
		aria-pressed={state.showCircles}
		onclick={() => (state.showCircles = !state.showCircles)}
	>
		<span class="dot" aria-hidden="true"></span> Trust circles
	</button>
	<!-- Only overlays that actually draw something get a button. `state.showMessages`
	     exists on ReplayState but has no layer behind it yet, and a control that visibly
	     does nothing is worse than an absent one — it gets its button back in the same
	     change that gives it something to toggle. -->
</div>

{#if state.showCircles}
	<ul class="legend">
		{#each groups as g (g.group)}
			<li>
				<span class="swatch" style="background: {g.color}" aria-hidden="true"></span>
				<span class="mono">{g.group}</span>
				<span class="muted"
					>{g.type} · {g.members.length} houses · {bandLabel(g.slot)}</span
				>
			</li>
		{/each}
		<li>
			<span class="swatch lattice-swatch" aria-hidden="true"></span>
			<span class="mono">geographic</span>
			<span class="muted">4-neighbour adjacency, drawn as the faint lattice</span>
		</li>
	</ul>
{/if}

<style>
	.toggles {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.toggle {
		display: inline-flex;
		align-items: center;
		gap: 0.45rem;
		background: var(--bg);
		color: var(--muted);
		border: 1px solid var(--border);
		border-radius: 999px;
		padding: 0.3rem 0.75rem;
		font: inherit;
		font-size: 0.8rem;
		cursor: pointer;
	}

	.toggle:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.dot {
		width: 0.55rem;
		height: 0.55rem;
		border-radius: 50%;
		border: 1px solid var(--muted);
	}

	.toggle[aria-pressed='true'] {
		color: var(--text);
		border-color: var(--accent);
	}

	.toggle[aria-pressed='true'] .dot {
		background: var(--accent);
		border-color: var(--accent);
	}

	.legend {
		list-style: none;
		margin: 0.6rem 0 0;
		padding: 0;
		display: grid;
		gap: 0.25rem;
		font-size: 0.78rem;
	}

	.legend li {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.swatch {
		width: 0.85rem;
		height: 0.85rem;
		border-radius: 3px;
		flex: none;
	}

	.lattice-swatch {
		background: transparent;
		border-top: 2px dashed var(--border);
		border-radius: 0;
		height: 0;
	}
</style>
