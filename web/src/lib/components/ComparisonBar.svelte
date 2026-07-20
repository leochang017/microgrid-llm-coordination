<!--
	Served-load comparison bars for one cell.

	Method order and labels mirror `scripts/figures.py`'s METHOD_ORDER / METHOD_LABEL so
	the demo and the paper figures never disagree. The mandatory comparison bar for the
	LLM condition is the zero-LLM control (`llm_fallback`), not round-robin.

	Accessibility: the <svg> bars are decorative (`aria-hidden`) — every row prints its
	label and its numeric value as real text, so a screen reader reads
	"control 0.627" rather than an unlabelled graphic.
-->
<script lang="ts">
	import type { CellMeta } from '$lib/types';
	import { gapClosedPhrase } from '$lib/gap';

	interface Props {
		meta: CellMeta;
	}

	const { meta }: Props = $props();

	interface Row {
		key: string;
		label: string;
		value: number;
		live: boolean;
	}

	const rows: Row[] = $derived([
		{
			key: 'no_coordination',
			label: 'no-coord',
			value: meta.baselines.no_coordination.served_load_fraction,
			live: false
		},
		{
			key: 'llm_fallback',
			label: 'control',
			value: meta.baselines.llm_fallback.served_load_fraction,
			live: false
		},
		{
			key: 'round_robin',
			label: 'round-robin',
			value: meta.baselines.round_robin.served_load_fraction,
			live: false
		},
		{ key: 'live', label: 'live-Haiku', value: meta.live.served_load_fraction, live: true },
		{
			key: 'lp_optimal',
			label: 'LP ceiling',
			value: meta.baselines.lp_optimal.served_load_fraction,
			live: false
		}
	]);

	// The x-domain is the full [0, 1] served-load range, so bar lengths are comparable
	// across cells, not just within one card.
	function pct(v: number): number {
		return Math.min(100, Math.max(0, v * 100));
	}

	// The gap-closed figure is signed (NEGATIVE on the comm cell). The phrasing is shared
	// with the replay page via `$lib/gap` so the two sites can never drift apart.
	const gap = $derived(meta.gapClosedControlToLp);
	const gapText = $derived(gapClosedPhrase(gap));
</script>

<div class="bars">
	<h3 class="cap">Served load fraction</h3>
	<ul>
		{#each rows as row (row.key)}
			<li class:live={row.live}>
				<span class="lbl">{row.label}</span>
				<svg class="track" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true">
					<rect x="0" y="0" width="100" height="10" class="bg" />
					<rect x="0" y="0" width={pct(row.value)} height="10" class="fill" />
				</svg>
				<span class="val num">{row.value.toFixed(3)}</span>
			</li>
		{/each}
	</ul>
	<p class="gap" class:negative={gap < 0}>live-Haiku {gapText}</p>
</div>

<style>
	.cap {
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--muted);
		margin: 0 0 0.5rem;
	}

	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.3rem;
	}

	li {
		display: grid;
		grid-template-columns: 5.5rem 1fr 3rem;
		align-items: center;
		gap: 0.5rem;
	}

	.lbl {
		font-size: 0.82rem;
		color: var(--muted);
	}

	li.live .lbl,
	li.live .val {
		color: var(--text);
		font-weight: 600;
	}

	.track {
		width: 100%;
		height: 12px;
		display: block;
	}

	.bg {
		fill: #222831;
	}

	.fill {
		fill: var(--muted);
	}

	li.live .fill {
		fill: var(--accent);
	}

	.val {
		font-size: 0.82rem;
		text-align: right;
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-variant-numeric: tabular-nums;
	}

	.gap {
		margin: 0.55rem 0 0;
		font-size: 0.82rem;
		color: var(--accent);
	}

	.gap.negative {
		color: #f8a5a5;
	}
</style>
