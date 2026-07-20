<!--
	Tick scrubber: a native range slider (free keyboard arrow-key support) plus
	play/pause, a 1x/2x/4x speed toggle, a clock readout, and a tiny per-tick strip
	chart of total solar (yellow, above the baseline) and total unmet load (red,
	below it) so the day/night cycle and the "pain hours" are visible at a glance
	without scrubbing to find them. The two series are each normalized to their own
	peak, so the chart is not a magnitude comparison between them — the caption says
	so, and carries the peak-solar / worst-unmet hours as the SVG's text equivalent
	(the SVG itself is aria-hidden).
-->
<script lang="ts">
	import type { CellMeta, CellTicks } from '$lib/types';
	import type { ReplayState } from '$lib/replay.svelte';

	interface Props {
		meta: CellMeta;
		ticks: CellTicks;
		state: ReplayState;
	}

	const { meta, ticks, state }: Props = $props();

	const maxTick = $derived(meta.tickCount - 1);

	function hhmm(iso: string): string {
		return iso.slice(11, 16);
	}
	function datePart(iso: string): string {
		return iso.slice(0, 10);
	}

	const clock = $derived(hhmm(meta.tickTimes[state.tick] ?? meta.tickTimes[0]));

	// Pure string slicing on the ISO timestamps, deliberately not `Date` math — this
	// project has been bitten before by timezone-parsing bugs on ISO strings without
	// an offset, and all we need here is "does the outage window cross midnight."
	const outageLabel = $derived.by(() => {
		const { start, end } = meta.outage;
		const startLabel = hhmm(start);
		const crossesDay = datePart(end) !== datePart(start);
		const endLabel = crossesDay && hhmm(end) === '00:00' ? '24:00' : hhmm(end);
		// No affected-house list is exported (`meta.outage` is only {start, end}), so this
		// deliberately makes no claim about WHICH houses the outage covers.
		return `grid down ${startLabel}–${endLabel}`;
	});

	function onSliderInput(e: Event): void {
		const raw = Number((e.currentTarget as HTMLInputElement).value);
		state.seek(raw, maxTick);
	}

	// "space toggles play" (spec step 3) needs to work no matter which control inside
	// the scrubber has focus (the slider, most likely) WITHOUT double-firing when the
	// play button itself is focused — a focused <button> already toggles play on its
	// own native Enter/Space activation, so this handler skips button targets and only
	// intercepts Space when some other element (e.g. the range input) has focus.
	function onWrapperKeydown(e: KeyboardEvent): void {
		if (e.code !== 'Space') return;
		if ((e.target as HTMLElement).tagName === 'BUTTON') return;
		e.preventDefault();
		state.togglePlay();
	}

	const SPEEDS: (1 | 2 | 4)[] = [1, 2, 4];

	const totalSolar = $derived(ticks.solarKw.map((row) => row.reduce((a, b) => a + b, 0)));
	const totalUnmet = $derived(ticks.unmetKwh.map((row) => row.reduce((a, b) => a + b, 0)));
	const maxSolar = $derived(Math.max(1e-9, ...totalSolar));
	const maxUnmet = $derived(Math.max(1e-9, ...totalUnmet));

	const STRIP_H = 40;
	const STRIP_MID = STRIP_H / 2;

	// Textual equivalent of the (aria-hidden) strip chart: the two facts it exists to
	// convey — when the sun peaks and when the pain is worst — computed from the same
	// arrays the bars are drawn from, never asserted.
	function argmax(xs: number[]): number {
		let best = 0;
		for (let i = 1; i < xs.length; i++) if (xs[i] > xs[best]) best = i;
		return best;
	}
	const peakSolar = $derived(argmax(totalSolar));
	const worstUnmet = $derived(argmax(totalUnmet));
	const stripSummary = $derived.by(() => {
		const solarPart =
			totalSolar[peakSolar] > 0
				? `neighborhood solar peaks at ${hhmm(meta.tickTimes[peakSolar])} (${totalSolar[peakSolar].toFixed(1)} kW)`
				: 'no solar generation at any tick';
		const unmetPart =
			totalUnmet[worstUnmet] > 0
				? `unmet load is worst at ${hhmm(meta.tickTimes[worstUnmet])} (${totalUnmet[worstUnmet].toFixed(2)} kWh that tick)`
				: 'no unmet load at any tick';
		return `${solarPart}; ${unmetPart}.`;
	});
</script>

<!--
	This div itself is not interactive — the listener only intercepts Space bubbling up
	from its focused children (the slider; see `onWrapperKeydown`'s reasoning above), it
	is never a keyboard/click target in its own right.
-->
<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div class="scrubber" role="group" aria-label="tick scrubber" onkeydown={onWrapperKeydown}>
	<div class="controls">
		<button
			type="button"
			class="play"
			aria-pressed={state.playing}
			aria-keyshortcuts="Space"
			onclick={() => state.togglePlay()}
		>
			{state.playing ? '⏸ Pause' : '▶ Play'}
		</button>

		<div class="speed" role="group" aria-label="playback speed">
			{#each SPEEDS as s (s)}
				<button type="button" aria-pressed={state.speed === s} onclick={() => (state.speed = s)}>
					{s}×
				</button>
			{/each}
		</div>

		<span class="clock num mono">{clock}</span>
	</div>

	<input
		type="range"
		class="slider"
		min="0"
		max={maxTick}
		value={state.tick}
		oninput={onSliderInput}
		aria-label="tick, {clock}"
	/>

	<svg
		class="strip"
		viewBox="0 0 {meta.tickCount} {STRIP_H}"
		preserveAspectRatio="none"
		aria-hidden="true"
	>
		<line x1="0" y1={STRIP_MID} x2={meta.tickCount} y2={STRIP_MID} class="baseline" />
		{#each totalSolar as v, i (i)}
			{@const h = (v / maxSolar) * STRIP_MID}
			<rect x={i} y={STRIP_MID - h} width="1" height={h} class="solar-bar" />
		{/each}
		{#each totalUnmet as v, i (i)}
			{@const h = (v / maxUnmet) * STRIP_MID}
			<rect x={i} y={STRIP_MID} width="1" height={h} class="unmet-bar" />
		{/each}
		<rect x={state.tick} y="0" width="1" height={STRIP_H} class="playhead" />
	</svg>
	<p class="strip-caption muted">
		solar (yellow, above) and unmet load (red, below) across all {meta.tickCount} ticks — each
		series is normalized to its own peak, so bar heights compare within a series, not between
		them. {stripSummary}
	</p>

	<p class="outage muted">{outageLabel}</p>
</div>

<style>
	.scrubber {
		display: grid;
		gap: 0.5rem;
	}

	.controls {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	button {
		background: #1f242c;
		border: 1px solid var(--border);
		color: var(--text);
		border-radius: 6px;
		padding: 0.3rem 0.65rem;
		font-size: 0.85rem;
		cursor: pointer;
	}

	button[aria-pressed='true'] {
		border-color: var(--accent);
		color: var(--accent);
	}

	.speed {
		display: flex;
		gap: 0.25rem;
	}

	.clock {
		margin-left: auto;
		font-size: 0.95rem;
	}

	.slider {
		width: 100%;
	}

	.strip {
		width: 100%;
		height: 40px;
		display: block;
	}

	.baseline {
		stroke: var(--border);
		stroke-width: 0.5;
	}

	.solar-bar {
		fill: var(--accent);
		opacity: 0.85;
	}

	.unmet-bar {
		fill: #f87171;
		opacity: 0.85;
	}

	.playhead {
		fill: var(--text);
		opacity: 0.55;
	}

	.strip-caption {
		margin: 0;
		font-size: 0.72rem;
	}

	.outage {
		margin: 0;
		font-size: 0.8rem;
	}
</style>
