<!--
	Replay route — one committed simulation cell, scrubbed tick by tick.

	Left column: the SoC neighborhood grid + tick scrubber. Right column: the per-tick
	message panel (Task 7). The per-house "why" panel lands in Task 8 and turns that
	column's single heading into a two-tab strip; it must not be built ahead of it here.

	Honesty constraints carried over from the overview route: Gini is never rendered
	without Jain adjacent; the comparison implied by "gap-closed" is always control->LP,
	never round-robin; the sign of `gapClosedControlToLp` is rendered honestly (it is
	negative on the comm cell) rather than `Math.abs`'d into a false positive framing.
-->
<script lang="ts">
	import { page } from '$app/state';
	import { base } from '$app/paths';
	import { loadCell, type LoadedCell } from '$lib/load';
	import { gapClosedPhrase } from '$lib/gap';
	import type { Slug } from '$lib/types';
	import { ReplayState } from '$lib/replay.svelte';
	import NeighborhoodGrid from '$lib/components/NeighborhoodGrid.svelte';
	import TickScrubber from '$lib/components/TickScrubber.svelte';
	import OverlayToggles from '$lib/components/OverlayToggles.svelte';
	import EventBadges from '$lib/components/EventBadges.svelte';
	import MessagePanel from '$lib/components/MessagePanel.svelte';

	const SLUGS: Slug[] = ['clean', 'defectors', 'noise', 'comm'];
	// `page.params` is typed as the union of every route's params app-wide (it's a global,
	// not scoped to this file's route), so `cell` comes through as `string | undefined`
	// even though this route always supplies it at runtime.
	function isSlug(x: string | undefined): x is Slug {
		return x !== undefined && (SLUGS as readonly string[]).includes(x);
	}

	const rawCell = $derived(page.params.cell);
	const slug = $derived<Slug | null>(isSlug(rawCell) ? rawCell : null);

	let loaded = $state<LoadedCell | null>(null);
	let error = $state<string | null>(null);
	const replay = new ReplayState();

	// Keyed on the slug, NOT `onMount`: a client-side nav from one /run/<cell>/ to another
	// reuses this component instance, so an init-time read would keep showing the previous
	// cell's data. Each (re)run resets the replay position and cancels a load still in
	// flight, so a slow fetch for the cell we just left can't overwrite the new one.
	$effect(() => {
		const s = slug;
		loaded = null;
		error = null;
		replay.tick = 0;
		replay.playing = false;
		replay.selectedHouse = null;
		if (!s) return;
		let cancelled = false;
		loadCell(s)
			.then((c) => {
				if (!cancelled) loaded = c;
			})
			.catch((e: unknown) => {
				if (!cancelled) error = e instanceof Error ? e.message : String(e);
			});
		return () => {
			cancelled = true;
		};
	});

	// Play loop: advances `replay.tick` every `450 / speed` ms while playing, auto-pausing
	// at the last tick. Depends on `replay.playing` / `replay.speed` / `loaded` — NOT
	// `replay.tick` — so the interval is (re)built only when playback starts/stops or the
	// speed changes, not on every single tick.
	$effect(() => {
		if (!replay.playing || !loaded) return;
		const max = loaded.meta.tickCount - 1;
		const ms = 450 / replay.speed;
		const id = setInterval(() => {
			if (replay.tick >= max) {
				replay.playing = false;
				return;
			}
			replay.seek(replay.tick + 1, max);
		}, ms);
		return () => clearInterval(id);
	});

	function fmt(v: number | null, digits = 3): string {
		return v === null || !Number.isFinite(v) ? 'n/a' : v.toFixed(digits);
	}

	// Same shared helper the overview card uses — see `$lib/gap` for why the sign matters.
	const gapText = $derived(gapClosedPhrase(loaded ? loaded.meta.gapClosedControlToLp : 0));
</script>

<svelte:head>
	<title>{slug ? `${slug} replay` : 'Unknown cell'} — Microgrid LLM coordination</title>
</svelte:head>

{#if !slug}
	<main class="unknown">
		<h1>Unknown cell</h1>
		<p class="muted">"{rawCell ?? '(none)'}" is not one of the four replayed cells.</p>
		<p><a href="{base}/">← Back to all cells</a></p>
	</main>
{:else}
	<main>
		<p class="back"><a href="{base}/">← All cells</a></p>

		{#if error}
			<div class="errorbox" role="alert">
				<strong>Could not load this run's data.</strong>
				<p class="mono">{error}</p>
			</div>
		{:else if loaded === null}
			<p class="muted" aria-busy="true">Loading {slug}…</p>
		{:else}
			<header>
				<h1>{loaded.meta.label}</h1>
				<p class="failure">{loaded.meta.failureDescription}</p>
				<p class="scenario muted">{loaded.meta.scenarioBlurb}</p>
				<p class="headline">
					Live Haiku served
					<span class="num">{fmt(loaded.meta.live.served_load_fraction)}</span>
					— {gapText}.
				</p>
			</header>

			<ul class="stats">
				<li>
					<span class="lbl">served</span>
					<span class="num">{fmt(loaded.meta.live.served_load_fraction)}</span>
				</li>
				<li>
					<span class="lbl">gini</span>
					<span class="num">{fmt(loaded.meta.live.gini_welfare)}</span>
				</li>
				<li>
					<span class="lbl">Jain</span>
					<span class="num">{fmt(loaded.meta.live.jains_index)}</span>
				</li>
				<li>
					<span class="lbl">transfers</span>
					<span class="num">{loaded.meta.negotiation.transferCount}</span>
				</li>
			</ul>

			<div class="layout">
				<section class="panel replay-col">
					<!-- OverlayToggles emits two root elements (.toggles + .legend); this
					     wrapper keeps them one row of `replay-col`'s flex gap, not two. -->
					<div>
						<OverlayToggles meta={loaded.meta} state={replay} />
					</div>
					<NeighborhoodGrid
						meta={loaded.meta}
						ticks={loaded.ticks}
						msgsByTick={loaded.msgsByTick}
						state={replay}
					/>
					<EventBadges ticks={loaded.ticks} state={replay} />
					<TickScrubber meta={loaded.meta} ticks={loaded.ticks} state={replay} />
				</section>

				<!-- One titled section today. Task 8 adds the per-house panel and turns this
				     heading into a two-tab strip; keeping the content behind a single heading
				     means that change is a swap of the heading, not a rebuild of the column. -->
				<aside class="panel side-col">
					<h2 class="side-title">Messages</h2>
					<MessagePanel
						meta={loaded.meta}
						msgsByTick={loaded.msgsByTick}
						informCounts={loaded.ticks.informCounts}
						state={replay}
					/>
				</aside>
			</div>
		{/if}
	</main>
{/if}

<style>
	main {
		margin: 0 auto;
		max-width: 78rem;
		padding: 2.5rem 1.5rem 4rem;
	}

	.unknown {
		max-width: 40rem;
	}

	.back {
		margin: 0 0 1.25rem;
		font-size: 0.85rem;
	}

	header {
		margin-bottom: 1.25rem;
	}

	h1 {
		font-size: clamp(1.4rem, 3.5vw, 1.9rem);
		text-transform: capitalize;
	}

	.failure {
		margin: 0 0 0.35rem;
		font-size: 0.92rem;
	}

	.scenario {
		margin: 0 0 0.75rem;
		font-size: 0.82rem;
	}

	.headline {
		margin: 0;
		font-size: 0.95rem;
	}

	.stats {
		list-style: none;
		margin: 0 0 1.5rem;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
		gap: 1.25rem;
	}

	.stats li {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}

	.stats .lbl {
		font-size: 0.72rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--muted);
	}

	.stats .num {
		font-size: 1.1rem;
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
	}

	.layout {
		display: grid;
		grid-template-columns: minmax(0, 2.1fr) minmax(16rem, 1fr);
		gap: 1.25rem;
		align-items: start;
	}

	@media (max-width: 60rem) {
		.layout {
			grid-template-columns: 1fr;
		}
	}

	.replay-col {
		display: grid;
		gap: 1rem;
	}

	.side-col {
		min-height: 8rem;
	}

	.side-title {
		margin: 0 0 0.6rem;
		font-size: 0.8rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--muted);
	}

	.errorbox {
		border: 1px solid #7f1d1d;
		background: #24161a;
		border-radius: 8px;
		padding: 1rem;
	}

	.errorbox p {
		margin: 0.4rem 0 0;
		font-size: 0.85rem;
		color: var(--muted);
	}
</style>
