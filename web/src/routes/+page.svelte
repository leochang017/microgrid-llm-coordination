<!--
	Overview route — the demo's front door.

	One card per committed cell in story order (clean → defectors → noise → comm), each
	with its served-load comparison bars, fairness chips and (where a judge evaluation
	was actually run) explanation-quality chips.

	Honesty constraints inherited from the project's advisor and enforced here:
	  * Gini is NEVER rendered without Jain's index adjacent to it.
	  * The comparison bar for the LLM condition is the zero-LLM control, not round-robin.
	  * Nothing implies deployment readiness. The "research demo — not a deployment"
	    footer lives in `+layout.svelte` so that EVERY route carries it, not just this
	    one — the replay pages are the ones that render the performance numbers.
	  * `judgeMeans` is absent for noise and comm — those cards show no judge chips at all
	    rather than a zero or a dash that would read as a score.
	  * `Metrics` fields other than `served_load_fraction` are `number | null` (the LP
	    ceiling ships them null), so every render goes through `fmt`.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import ComparisonBar from '$lib/components/ComparisonBar.svelte';
	import type { CellMeta, Slug } from '$lib/types';

	const SLUGS: Slug[] = ['clean', 'defectors', 'noise', 'comm'];

	let cells = $state<CellMeta[] | null>(null);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			cells = await Promise.all(
				SLUGS.map(async (slug) => {
					const res = await fetch(`${base}/data/${slug}/meta.json`);
					if (!res.ok) throw new Error(`${slug}/meta.json: HTTP ${res.status}`);
					return (await res.json()) as CellMeta;
				})
			);
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	});

	/** Metrics are `number | null`; a missing value must never reach `.toFixed`. */
	function fmt(v: number | null, digits = 3): string {
		return v === null || !Number.isFinite(v) ? 'n/a' : v.toFixed(digits);
	}

	const model = $derived(cells?.[0]?.model ?? null);
</script>

<svelte:head>
	<title>Microgrid LLM coordination — run replays</title>
	<meta
		name="description"
		content="Static replay of committed simulation runs in which per-household LLM agents negotiate energy sharing during a grid outage."
	/>
</svelte:head>

<main>
	<header>
		<h1>Can LLM agents share power fairly in a blackout?</h1>
		<p class="blurb">
			Thirty households ride out a 24-hour outage on a shared distribution bus. Some own rooftop
			solar and large batteries; most do not. Each household is driven by its own language-model
			agent that negotiates peer-to-peer, in natural language, over who sends energy to whom. These
			four replays compare that live negotiation against a zero-LLM control running the same fixed
			policy, plus a round-robin protocol and a centralized linear-program ceiling.
		</p>
		<p class="provenance muted">
			<span class="mono">{model ?? 'agent model: see run pages'}</span>
			<span aria-hidden="true">·</span>
			static replay of committed reference runs — no live LLM calls, no backend
		</p>
	</header>

	{#if error}
		<div class="errorbox" role="alert">
			<strong>Could not load the run data.</strong>
			<p class="mono">{error}</p>
		</div>
	{:else if cells === null}
		<ul class="cards" aria-busy="true">
			{#each SLUGS as slug (slug)}
				<li class="panel card skeleton">
					<span class="sr-only">Loading {slug}…</span>
					<div class="skel skel-title" aria-hidden="true"></div>
					<div class="skel skel-line" aria-hidden="true"></div>
					<div class="skel skel-line" aria-hidden="true"></div>
					<div class="skel skel-block" aria-hidden="true"></div>
				</li>
			{/each}
		</ul>
	{:else}
		<ul class="cards">
			{#each cells as cell (cell.slug)}
				<li class="panel card">
					<h2>
						<a href="{base}/run/{cell.slug}/">{cell.label}</a>
						<span class="seed muted">seed {cell.seed}</span>
					</h2>
					<p class="failure">{cell.failureDescription}</p>
					<p class="scenario muted">{cell.scenarioBlurb}</p>

					<ComparisonBar meta={cell} />

					<!-- Gini and Jain are always rendered as a pair: a Gini number alone is not
					     an acceptable fairness claim on this project. -->
					<h3 class="cap">Fairness (live-Haiku)</h3>
					<ul class="chips">
						<li class="chip">Gini <span class="num">{fmt(cell.live.gini_welfare)}</span></li>
						<li class="chip">Jain <span class="num">{fmt(cell.live.jains_index)}</span></li>
						<li class="chip">
							served critical <span class="num">{fmt(cell.live.served_critical_load_fraction)}</span>
						</li>
					</ul>

					{#if cell.judgeMeans}
						<h3 class="cap">Explanation quality (1–5)</h3>
						<ul class="chips">
							<li class="chip">
								accuracy <span class="num">{cell.judgeMeans.state_accuracy.toFixed(2)}</span>
							</li>
							<li class="chip">
								actionability <span class="num">{cell.judgeMeans.actionability.toFixed(2)}</span>
							</li>
							<li class="chip">
								consistency <span class="num">{cell.judgeMeans.consistency.toFixed(2)}</span>
							</li>
							<li class="chip subtle">n=100, Sonnet judge</li>
						</ul>
					{/if}

					{#if cell.cleanSeedSpread}
						<p class="note muted">
							Other seeds served
							{Object.entries(cell.cleanSeedSpread)
								.map(([s, v]) => `${s}: ${v.toFixed(3)}`)
								.join(' · ')} — this replay is seed {cell.seed}, the hardest of the three.
						</p>
					{/if}

					<p class="cta"><a href="{base}/run/{cell.slug}/">Replay this run →</a></p>
				</li>
			{/each}
		</ul>
	{/if}
</main>

<style>
	main {
		margin: 0 auto;
		max-width: 68rem;
		padding: 3rem 1.5rem 4rem;
	}

	header {
		margin-bottom: 2rem;
	}

	h1 {
		font-size: clamp(1.6rem, 4vw, 2.3rem);
		max-width: 24ch;
	}

	.blurb {
		max-width: 68ch;
		margin: 0 0 0.9rem;
	}

	.provenance {
		font-size: 0.85rem;
		margin: 0;
	}

	.cards {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 1.25rem;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 26rem), 1fr));
	}

	.card h2 {
		display: flex;
		align-items: baseline;
		gap: 0.6rem;
		font-size: 1.25rem;
		margin-bottom: 0.35rem;
	}

	.seed {
		font-size: 0.8rem;
		font-weight: 400;
	}

	.failure {
		margin: 0 0 0.5rem;
		font-size: 0.9rem;
	}

	.scenario {
		margin: 0 0 1rem;
		font-size: 0.8rem;
	}

	.cap {
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--muted);
		margin: 1rem 0 0.45rem;
	}

	.chips {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
	}

	.chip {
		background: #1f242c;
		border: 1px solid var(--border);
		border-radius: 999px;
		padding: 0.15rem 0.6rem;
		font-size: 0.8rem;
		color: var(--text);
	}

	.chip.subtle {
		color: var(--muted);
		background: transparent;
	}

	.chip .num {
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-variant-numeric: tabular-nums;
	}

	.note {
		font-size: 0.8rem;
		margin: 0.9rem 0 0;
	}

	.cta {
		margin: 1rem 0 0;
		font-size: 0.9rem;
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

	.skeleton {
		min-height: 18rem;
	}

	.skel {
		background: #222831;
		border-radius: 4px;
		margin-bottom: 0.6rem;
	}

	.skel-title {
		height: 1.4rem;
		width: 40%;
	}

	.skel-line {
		height: 0.8rem;
		width: 85%;
	}

	.skel-block {
		height: 9rem;
		width: 100%;
		margin-top: 1rem;
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
		white-space: nowrap;
	}
</style>
