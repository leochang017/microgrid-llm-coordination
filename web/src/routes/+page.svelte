<!--
	Overview route — the demo's front door, implementing the approved Claude Design
	"Overview.dc.html" (project 333b65b9, 2026-07-21 redesign).

	Honesty constraints inherited from the project's advisor and enforced here:
	  * Gini is NEVER rendered without Jain's index adjacent to it.
	  * The comparison for the LLM condition is the zero-LLM control, not round-robin;
	    round-robin appears once, on the explainer gauge, labeled "context only".
	  * The comm cell's negative result is rendered signed and as prominently as the
	    wins (red card, "NEGATIVE RESULT" tag, gapClosedPhrase never Math.abs'd).
	  * Nothing implies deployment readiness: sticky banner here + the site-wide
	    footer in `+layout.svelte` (which also covers the replay routes).
	  * `judgeMeans` is absent for noise and comm — those cards say "not judged",
	    which is different from scoring zero.
	  * The defectors fine-print card renders `failureDescription` VERBATIM from the
	    data: it is the canonical two-part copy (the prompt permits misreporting; the
	    belief channel makes it inert; withholding operates) and quoting the shipped
	    string means the page cannot drift from it.

	Deviations from the design file, each because the data contract wins:
	  * Card mini-gauges use a 0-100% scale — the design's 0-85% scale would place
	    the defectors LP marker (96.7% served) off the track. The big explainer
	    gauge keeps the 0-85% scale (clean's max is the 76.8% LP ceiling) and its
	    caption names the scale.
	  * Quotes are first-ACCEPT / second-COUNTER / first-REJECT: the design picked
	    REQUEST/COUNTER/OFFER, but zero authored REQUEST or OFFER rows exist in any
	    committed cell (REQUESTs/OFFERs are templated; ACCEPT/COUNTER/REJECT carry
	    the LLM-authored rationales).
	  * The seed note states only the per-seed served values that ship in
	    `cleanSeedSpread` — the published "+5.8 ± 1.0 across 3 seeds" aggregate
	    needs per-seed controls the demo data does not carry, so it is not claimed.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import { gapClosedPhrase } from '$lib/gap';
	import type { CellMeta, Msg, Slug } from '$lib/types';

	const SLUGS: Slug[] = ['clean', 'defectors', 'noise', 'comm'];

	const GREEN = '#5ec8a8';
	const RED = '#e07b87';
	const FAINT = '#7d8a9c';

	let metas = $state<Record<Slug, CellMeta> | null>(null);
	let error = $state<string | null>(null);
	let quotePicks = $state<Msg[] | null>(null);
	let msgTotal = $state<number | null>(null);
	let open = $state<Record<string, boolean>>({});

	onMount(() => {
		Promise.all(
			SLUGS.map(async (slug) => {
				const res = await fetch(`${base}/data/${slug}/meta.json`);
				if (!res.ok) throw new Error(`${slug}/meta.json: HTTP ${res.status}`);
				return [slug, (await res.json()) as CellMeta] as const;
			})
		)
			.then((pairs) => {
				metas = Object.fromEntries(pairs) as Record<Slug, CellMeta>;
			})
			.catch((e) => {
				error = e instanceof Error ? e.message : String(e);
			});

		// Quotes load separately and lazily: 4 meta files paint the page; the clean
		// message log (~400 kB on the wire) only feeds the quotes section.
		fetch(`${base}/data/clean/messages.json`)
			.then((res) => {
				if (!res.ok) throw new Error(`clean/messages.json: HTTP ${res.status}`);
				return res.json();
			})
			.then((d: { messages: Msg[] }) => {
				const auth = d.messages.filter(
					(m) => m.authored && m.outcome === 'delivered' && m.why !== null && m.why.length > 60
				);
				const byPerf = (p: string) => auth.filter((m) => m.perf === p);
				quotePicks = [byPerf('ACCEPT')[0], byPerf('COUNTER')[1], byPerf('REJECT')[0]].filter(
					(m): m is Msg => Boolean(m)
				);
				msgTotal = d.messages.length;
			})
			.catch((e) => console.error('quotes load failed', e));
	});

	function toggle(k: string): void {
		open = { ...open, [k]: !open[k] };
	}

	const pct = (v: number) => (v * 100).toFixed(1) + '%';

	/** Big explainer gauge: 0-85% scale (clean cell only; its max is LP 76.8%). */
	const posG = (v: number) => ((v / 0.85) * 100).toFixed(1) + '%';
	/** Card mini-gauges: 0-100% scale so every cell's LP marker stays on the track. */
	const posC = (v: number) => (v * 100).toFixed(1) + '%';

	const COPY: Record<
		Slug,
		{ order: string; tag: string; title: string; tagColor: string; blurb: (m: CellMeta) => string }
	> = {
		clean: {
			order: 'I / IV',
			tag: 'CLEAN',
			title: 'Everything works',
			tagColor: FAINT,
			blurb: () =>
				'Honest sensors, reliable messaging. The agents beat the control — the main positive result. All three committed seeds of this cell ship with the demo.'
		},
		defectors: {
			order: 'II / IV',
			tag: 'DEFECTORS',
			title: 'Six houses act selfishly',
			tagColor: FAINT,
			blurb: (m) =>
				`${m.defectors.length} agents are prompted to hoard charge and decline requests. Misreporting has no channel — state broadcasts come from fixed code — so withholding is the lever. Most of the benefit survives.`
		},
		noise: {
			order: 'III / IV',
			tag: 'NOISE',
			title: 'Sensors are unreliable',
			tagColor: FAINT,
			blurb: () =>
				'Battery readings distorted by 10% Gaussian noise and load readings by 15%. The AI stays ahead of the control, by a reduced margin.'
		},
		comm: {
			order: 'IV / IV',
			tag: 'COMM — NEGATIVE RESULT',
			title: 'Messages get lost',
			tagColor: '#d98a94',
			blurb: () =>
				'Rationed, unreliable messaging. The AI scores below the control: negotiation consumes the messages sharing depends on. Reported as prominently as the wins.'
		}
	};

	const ctl = (m: CellMeta) => m.baselines.llm_fallback;
	const lp = (m: CellMeta) => m.baselines.lp_optimal;

	const cards = $derived(
		metas === null
			? []
			: SLUGS.map((slug) => {
					const m = metas![slug];
					const live = m.live.served_load_fraction;
					const control = ctl(m).served_load_fraction;
					const ceiling = lp(m).served_load_fraction;
					const delta = (live - control) * 100;
					const neg = delta < 0;
					return {
						slug,
						...COPY[slug],
						blurbText: COPY[slug].blurb(m),
						neg,
						deltaStr: (neg ? '−' : '+') + Math.abs(delta).toFixed(1) + ' pts',
						deltaColor: neg ? RED : GREEN,
						gapColor: neg ? RED : FAINT,
						controlPct: pct(control),
						livePct: pct(live),
						lpPct: pct(ceiling),
						pControl: posC(control),
						pLive: posC(live),
						pLp: posC(ceiling),
						segLeft: posC(Math.min(control, live)),
						segWidth: (Math.abs(live - control) * 100).toFixed(1) + '%',
						gapSentence: gapClosedPhrase(m.gapClosedControlToLp)
					};
				})
	);

	const hero = $derived.by(() => {
		if (metas === null) return null;
		const m = metas.clean;
		const haves = m.houses.filter((h) => h.have);
		const havenots = m.houses.filter((h) => !h.have);
		const kwhRange = (hs: typeof haves) => {
			const c = hs.map((h) => h.batteryKwh);
			return `${Math.round(Math.min(...c))}–${Math.round(Math.max(...c))} kWh`;
		};
		return {
			servedPct: pct(m.live.served_load_fraction),
			controlPct: pct(ctl(m).served_load_fraction),
			nHave: haves.length,
			nNot: havenots.length,
			nTotal: m.houses.length,
			haveKwh: kwhRange(haves),
			notKwh: kwhRange(havenots)
		};
	});

	const gauge = $derived.by(() => {
		if (metas === null) return null;
		const m = metas.clean;
		const s = (k: 'no_coordination' | 'llm_fallback' | 'round_robin' | 'lp_optimal') =>
			m.baselines[k].served_load_fraction;
		const live = m.live.served_load_fraction;
		return {
			pNoCoord: posG(s('no_coordination')),
			pControl: posG(s('llm_fallback')),
			pRr: posG(s('round_robin')),
			pLive: posG(live),
			pLp: posG(s('lp_optimal')),
			segWidth: (((live - s('llm_fallback')) / 0.85) * 100).toFixed(1) + '%',
			noCoordPct: pct(s('no_coordination')),
			controlPct: pct(s('llm_fallback')),
			rrPct: pct(s('round_robin')),
			livePct: pct(live),
			lpPct: pct(s('lp_optimal')),
			gapSentence: `the AI closed ${Math.round(m.gapClosedControlToLp * 100)}% of the distance from the control to the ceiling.`
		};
	});

	const seedNote = $derived.by(() => {
		if (metas === null) return null;
		const spread = metas.clean.cleanSeedSpread;
		if (!spread) return 'seed-spread data not present in this build.';
		const others = Object.entries(spread)
			.map(([s, v]) => `seed ${s} served ${pct(v)}`)
			.join(', ');
		return `Two other seeds of this cell are committed (${others}); this replay is seed ${metas.clean.seed}, the hardest of the three.`;
	});

	const fairness = $derived(
		metas === null
			? []
			: SLUGS.map((slug) => {
					const m = metas![slug];
					const g = m.live.gini_welfare;
					const j = m.live.jains_index;
					const gc = ctl(m).gini_welfare;
					const jc = ctl(m).jains_index;
					const fmt2 = (v: number | null) => (v === null ? 'n/a' : v.toFixed(2));
					let verdict = 'mixed vs the control';
					let verdictColor = FAINT;
					if (g !== null && j !== null && gc !== null && jc !== null) {
						if (g < gc && j > jc) {
							verdict = 'fairer than the control on both measures';
							verdictColor = GREEN;
						} else if (g > gc && j < jc) {
							verdict = 'less fair than the control on both measures';
							verdictColor = RED;
						}
					}
					return {
						slug,
						tag: COPY[slug].tag,
						tagColor: COPY[slug].tagColor,
						gini: fmt2(g),
						jain: fmt2(j),
						giniC: fmt2(gc),
						jainC: fmt2(jc),
						verdict,
						verdictColor
					};
				})
	);

	const judges = $derived(
		metas === null
			? []
			: SLUGS.map((slug) => {
					const m = metas![slug];
					return {
						slug,
						tag: COPY[slug].tag,
						tagColor: COPY[slug].tagColor,
						means: m.judgeMeans ?? null
					};
				})
	);

	const quotes = $derived.by(() => {
		if (quotePicks === null || metas === null) return null;
		const times = metas.clean.tickTimes;
		return quotePicks.map((q) => ({
			id: q.id,
			why: q.why ?? '',
			from: q.from,
			to: q.to,
			perf: q.perf,
			// ISO-string slicing, never Date math (project convention).
			time: `${times[q.t]?.slice(11, 16) ?? '??:??'} · tick ${q.t}`,
			authored: q.authored
		}));
	});
</script>

<svelte:head>
	<title>Microgrid LLM coordination — run replays</title>
	<meta
		name="description"
		content="Static replay of committed simulation runs in which per-household LLM agents negotiate energy sharing during a grid outage."
	/>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link
		href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400..700&family=IBM+Plex+Mono:wght@400;500;600&display=swap"
		rel="stylesheet"
	/>
</svelte:head>

<div class="ov">
	<div class="topbar">
		<span class="topbar-flag">● RESEARCH DEMO — NOT A DEPLOYMENT</span>
		<span class="topbar-sub">replaying committed runs · prerendered data · zero live AI calls</span>
	</div>

	<main>
		{#if error}
			<div class="errorbox" role="alert">
				<strong>Could not load the run data.</strong>
				<p class="mono">{error}</p>
			</div>
		{:else if metas === null || hero === null || gauge === null}
			<section class="loading" aria-busy="true">
				<p class="kicker">FOUR EXPERIMENTS · 30 HOUSES · ONE 24-HOUR BLACKOUT</p>
				<p class="sub">Loading the committed run data…</p>
			</section>
		{:else}
			<!-- HERO -->
			<section class="hero">
				<p class="kicker">
					FOUR EXPERIMENTS · {hero.nTotal} HOUSES · ONE 24-HOUR BLACKOUT
				</p>
				<h1>Can AI agents share power fairly during a blackout?</h1>
				<p class="lede">
					In this simulated 24-hour blackout, {hero.nTotal} houses share one neighborhood power line.
					{hero.nHave} have rooftop solar and large batteries; {hero.nNot} have neither. Each house is
					controlled by its own AI agent that must negotiate with the others to keep the lights on.
					This site replays four recorded experiments.
				</p>
				<div class="hero-row">
					<div>
						<div class="hero-num">{hero.servedPct}</div>
						<p class="hero-caption">
							of the electricity households needed was delivered when the agents negotiated — the
							<button
								type="button"
								class="term"
								aria-expanded={!!open.served}
								onclick={() => toggle('served')}>served-load fraction</button
							>. The same system without the AI delivered {hero.controlPct}. In the fourth
							experiment, the AI scored below that control.
						</p>
						{#if open.served}
							<div class="termbox">
								<strong>SERVED-LOAD FRACTION</strong> — of all the electricity households wanted over
								24 hours, the share they actually got. The main score, from 0 to 1.
							</div>
						{/if}
					</div>
					<a class="cta" href="{base}/run/clean/">▶ Watch a day in the neighborhood</a>
				</div>
				<div class="setup-grid">
					<div class="setup-card">
						<div class="setup-tag">1 · THE SETUP</div>
						<p>
							A 24-hour blackout cuts {hero.nTotal} houses off the grid. {hero.nHave} have rooftop solar
							and {hero.haveKwh} batteries; {hero.nNot} have no solar and {hero.notKwh} batteries. There
							is enough solar energy for everyone, but it arrives on {hero.nHave} roofs at midday while
							the others need it at night.
						</p>
					</div>
					<div class="setup-card">
						<div class="setup-tag">2 · THE AGENTS</div>
						<p>
							Each house is controlled by a small language model (Claude Haiku). Every 15 minutes,
							houses broadcast their battery level; agents then request, offer, counter, accept, or
							reject energy transfers, and write a one-sentence reason for each decision.
						</p>
					</div>
					<div class="setup-card">
						<div class="setup-tag">3 · THE COMPARISON</div>
						<p>
							Every run is scored against a control: the identical system with the AI replaced by a
							fixed rule. If the AI only matches the control, it added nothing. One of the four
							experiments falls below it — a negative result, reported alongside the wins.
						</p>
					</div>
				</div>
			</section>

			<!-- SCOREBOARD -->
			<section>
				<h2>What happened</h2>
				<p class="section-sub">
					Each card shows the score change vs the
					<button
						type="button"
						class="term term-muted"
						aria-expanded={!!open.control}
						onclick={() => toggle('control')}>zero-LLM control</button
					>
					— the same system with the AI replaced by a fixed rule. Positive means the AI helped; negative
					means it hurt.
				</p>
				{#if open.control}
					<div class="termbox wide">
						<strong>ZERO-LLM CONTROL</strong> — the identical agent machinery (same messages, same
						commitments, same executor) with the language model replaced by a fixed rule. If the AI
						only ties it, the value was in the plumbing and the AI added nothing. Round-robin appears
						as context only; it is seed-dependent and never the claim.
					</div>
				{/if}
				<div class="card-grid">
					{#each cards as c (c.slug)}
						<a href="{base}/run/{c.slug}/" class="cell-card" class:neg={c.neg}>
							<div class="cell-head">
								<span class="cell-tag" style="color:{c.tagColor}">{c.tag}</span>
								<span class="cell-order">{c.order}</span>
							</div>
							<div class="cell-title">{c.title}</div>
							<div class="cell-delta" style="color:{c.deltaColor}">{c.deltaStr}</div>
							<p class="cell-blurb">{c.blurbText}</p>
							<!-- Decorative: control / AI / ceiling are printed as text right below. -->
							<div class="mini" aria-hidden="true">
								<div class="mini-track"></div>
								<div
									class="mini-seg"
									style="left:{c.segLeft};width:{c.segWidth};background:{c.deltaColor}"
								></div>
								<div class="mini-tick" style="left:{c.pControl}"></div>
								<div class="mini-live" style="left:{c.pLive};background:{c.deltaColor}"></div>
								<div class="mini-tick faint" style="left:{c.pLp}"></div>
							</div>
							<div class="mini-labels">
								<span>control {c.controlPct}</span>
								<span style="color:{c.deltaColor}">AI {c.livePct}</span>
								<span>ceiling {c.lpPct}</span>
							</div>
							<div class="cell-gap" style="color:{c.gapColor}">{c.gapSentence}</div>
							<div class="cell-cta">watch the replay →</div>
						</a>
					{/each}
				</div>
			</section>

			<!-- GAUGE HOW-TO -->
			<section>
				<h2>How to read the scores</h2>
				<p class="section-sub">
					Every run is compared against four references on the same houses, weather, and random seed.
					The key quantity is where the AI lands between the control and the ceiling.
				</p>
				<div class="gauge-panel">
					<div class="gauge-caption">CLEAN EXPERIMENT · SERVED-LOAD FRACTION, 0–85% SCALE</div>
					<div class="gauge">
						<div class="g-track"></div>
						<div class="g-fill" style="width:{gauge.pControl}"></div>
						<div class="g-seg" style="left:{gauge.pControl};width:{gauge.segWidth}"></div>
						<div class="g-tick" style="left:{gauge.pNoCoord};top:42px;height:28px"></div>
						<div class="g-label top" style="left:{gauge.pNoCoord}">
							<div class="g-val">{gauge.noCoordPct}</div>
							<div class="g-name">no coordination</div>
						</div>
						<div class="g-tick strong" style="left:{gauge.pControl};top:44px;height:32px"></div>
						<div class="g-label below" style="left:{gauge.pControl}">
							<div class="g-val strong">{gauge.controlPct}</div>
							<div class="g-name strong">zero-LLM control</div>
						</div>
						<div class="g-tick dashed" style="left:{gauge.pRr};top:40px;height:32px"></div>
						<div class="g-label rr" style="left:{gauge.pRr}">
							<div class="g-name">round-robin {gauge.rrPct} (context only)</div>
						</div>
						<div class="g-live" style="left:{gauge.pLive}"></div>
						<div class="g-label live" style="left:{gauge.pLive}">
							<div class="g-val live">{gauge.livePct}</div>
							<div class="g-name live">LIVE AI</div>
						</div>
						<div class="g-tick lp" style="left:{gauge.pLp};top:38px;height:36px"></div>
						<div class="g-label top" style="left:{gauge.pLp}">
							<div class="g-val">{gauge.lpPct}</div>
							<div class="g-name">LP ceiling</div>
						</div>
					</div>
					<p class="gauge-read">
						The green segment is the result: <strong class="green">{gauge.gapSentence}</strong>
						Beating "no coordination" is easy; beating the control shows the language model itself added
						value. The
						<button
							type="button"
							class="term term-muted"
							aria-expanded={!!open.lp}
							onclick={() => toggle('lp')}>LP ceiling</button
						> is the best score any allocator could achieve. In the comm experiment the segment is red
						and points left.
					</p>
					{#if open.lp}
						<div class="termbox dark wide">
							<strong>LP CEILING</strong> — a linear-program optimizer given perfect information
							about every house and central control of everything.
							<strong>GAP CLOSED</strong> — where the AI landed between the control and this
							ceiling, as a percentage. Signed: negative means it landed <em>below</em> the control.
						</div>
					{/if}
				</div>
				<p class="seed-note">{seedNote}</p>
			</section>

			<!-- FAIRNESS -->
			<section>
				<h2>Sharing was also more equal</h2>
				<p class="section-sub">
					Two measures, always shown together because either alone can mislead:
					<button
						type="button"
						class="term term-muted"
						aria-expanded={!!open.fair}
						onclick={() => toggle('fair')}>Gini coefficient</button
					>
					(0 = perfectly equal, lower is fairer) and
					<button
						type="button"
						class="term term-muted"
						aria-expanded={!!open.fair}
						onclick={() => toggle('fair')}>Jain's index</button
					> (1 = perfectly equal, higher is fairer).
				</p>
				{#if open.fair}
					<div class="termbox wide">
						<strong>GINI COEFFICIENT</strong> — inequality of outcomes across the {hero.nTotal}
						houses; 0 means everyone was treated equally. <strong>JAIN'S INDEX</strong> — a second
						fairness measure where 1 is perfect equality. Gini is sensitive to the worst-off tail;
						Jain to overall spread — which is why neither appears alone on this site.
					</div>
				{/if}
				<div class="card-grid narrow">
					{#each fairness as f (f.slug)}
						<div class="fair-card">
							<div class="cell-tag" style="color:{f.tagColor}">{f.tag}</div>
							<div class="fair-grid">
								<div>
									<div class="fair-axis">GINI ↓ fairer</div>
									<div class="fair-num">{f.gini}</div>
									<div class="fair-ctl">control {f.giniC}</div>
								</div>
								<div>
									<div class="fair-axis">JAIN ↑ fairer</div>
									<div class="fair-num">{f.jain}</div>
									<div class="fair-ctl">control {f.jainC}</div>
								</div>
							</div>
							<div class="fair-verdict" style="color:{f.verdictColor}">{f.verdict}</div>
						</div>
					{/each}
				</div>
			</section>

			<!-- QUOTES -->
			<section>
				<h2>What the agents said</h2>
				<p class="section-sub">
					Each decision includes a one-sentence reason. Three real examples from the clean run —
					labeled <span class="badge authored">AI-AUTHORED</span> when the model wrote them,
					<span class="badge templated">TEMPLATED</span> when generated by fixed code.
				</p>
				{#if quotes === null}
					<p class="section-sub" aria-busy="true">Loading examples from the message log…</p>
				{:else}
					<div class="card-grid quotes">
						{#each quotes as q (q.id)}
							<figure class="quote-card">
								<blockquote>"{q.why}"</blockquote>
								<figcaption>
									{q.from} → {q.to} · {q.perf} · {q.time} ·
									<span class={q.authored ? 'green' : 'sub'}
										>{q.authored ? 'AI-AUTHORED' : 'TEMPLATED'}</span
									>
								</figcaption>
							</figure>
						{/each}
					</div>
				{/if}
				<p class="more-link">
					<a href="{base}/run/clean/"
						>Browse all {msgTotal === null ? '…' : msgTotal.toLocaleString('en-US')} negotiation messages
						in the replay's message panel →</a
					>
				</p>
			</section>

			<!-- JUDGE -->
			<section>
				<h2>How good were the explanations?</h2>
				<p class="section-sub wide">
					A Sonnet judge — a different model family from the Haiku agents — scored 100 sampled
					explanations in each of the two judged experiments (clean and defectors) on three axes,
					1–5. The explanations are coherent and useful, but the numbers agents quote about their own
					state often drift from the logged values. Scores join to explanations at the tick level,
					and the pairing can be ambiguous when a house sent several messages in one tick.
				</p>
				<div class="card-grid narrow">
					{#each judges as j (j.slug)}
						<div class="fair-card">
							<div class="cell-tag" style="color:{j.tagColor}">{j.tag}</div>
							{#if j.means}
								<div class="judge-rows">
									<div class="judge-row">
										<span class="fair-axis">state-accuracy</span>
										<span class="judge-num">{j.means.state_accuracy.toFixed(2)}<span class="of5"> / 5</span></span>
									</div>
									<div class="judge-row">
										<span class="fair-axis">actionability</span>
										<span class="judge-num">{j.means.actionability.toFixed(2)}<span class="of5"> / 5</span></span>
									</div>
									<div class="judge-row">
										<span class="fair-axis">consistency</span>
										<span class="judge-num">{j.means.consistency.toFixed(2)}<span class="of5"> / 5</span></span>
									</div>
								</div>
							{:else}
								<p class="not-judged">
									Not judged for this experiment — no scores exist, which is different from scoring
									zero.
								</p>
							{/if}
						</div>
					{/each}
				</div>
			</section>

			<!-- FINE PRINT -->
			<section class="last">
				<h2>The fine print, up front</h2>
				<div class="card-grid fine">
					<div class="fine-card">
						<div class="fine-tag">WHAT DEFECTORS CAN AND CANNOT DO</div>
						<!-- Verbatim from the data: the canonical two-part misreport/withhold copy. -->
						<p>{metas.defectors.failureDescription}</p>
					</div>
					<div class="fine-card">
						<div class="fine-tag">WHAT THIS SITE IS</div>
						<p>
							A viewer of finished experiments. Every model call was cached and committed to the
							repository, so published runs replay byte-for-byte with no API calls. No backend, no
							live AI. Every number on this page is read from the run data files.
						</p>
					</div>
					<div class="fine-card">
						<div class="fine-tag">WHAT THIS DOES NOT MEAN</div>
						<p>
							Nothing here implies AI should operate a real power grid: one simulated climate, small
							samples on the failure cases, a research prototype. The claims are deliberately narrow
							— the control comparison, the signed negative result, re-runs after bug fixes.
						</p>
					</div>
				</div>
				<!-- The full disclaimer + repo link live in the site-wide layout footer just below. -->
				<div class="cell-links">
					<span>replays:</span>
					<span>
						<a href="{base}/run/clean/">clean</a> · <a href="{base}/run/defectors/">defectors</a> ·
						<a href="{base}/run/noise/">noise</a> · <a href="{base}/run/comm/">comm</a>
					</span>
				</div>
			</section>
		{/if}
	</main>
</div>

<style>
	/* Design palette (Claude Design Overview.dc.html), scoped to this route. */
	.ov {
		--d-bg: #101318;
		--d-panel: #171c24;
		--d-panel2: #1a1f27;
		--d-border: #232a35;
		--d-text: #eef2f7;
		--d-sub: #a8b4c4;
		--d-faint: #7d8a9c;
		--d-green: #5ec8a8;
		--d-red: #e07b87;
		--d-amber: #e8b84b;
		--d-dotted: #4a5568;
		--sans: 'Space Grotesk', system-ui, sans-serif;
		--mono: 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
		background: var(--d-bg);
		color: var(--d-text);
		font-family: var(--sans);
		min-width: 320px;
	}

	.ov :global(a) {
		color: var(--d-green);
	}

	.ov :global(a:hover) {
		color: #8adcc4;
	}

	.topbar {
		position: sticky;
		top: 0;
		z-index: 50;
		background: var(--d-panel2);
		border-bottom: 1px solid var(--d-border);
		padding: 8px 24px;
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 12px;
		flex-wrap: wrap;
	}

	.topbar-flag {
		font: 600 11px var(--mono);
		letter-spacing: 0.12em;
		color: var(--d-amber);
	}

	.topbar-sub {
		font: 400 11px var(--mono);
		color: var(--d-faint);
	}

	main {
		max-width: 1160px;
		margin: 0 auto;
		padding: 0 24px;
	}

	section {
		padding: 44px 0;
		border-bottom: 1px solid var(--d-border);
	}

	section.last {
		border-bottom: none;
		padding-bottom: 64px;
	}

	h1 {
		font: 500 clamp(30px, 4.5vw, 52px) / 1.12 var(--sans);
		letter-spacing: -0.015em;
		margin: 0;
		max-width: 820px;
		text-wrap: pretty;
	}

	h2 {
		font: 500 24px var(--sans);
		margin: 0 0 6px;
		letter-spacing: -0.01em;
	}

	.kicker {
		font: 500 12px var(--mono);
		letter-spacing: 0.14em;
		color: var(--d-faint);
		margin: 0 0 18px;
	}

	.hero {
		padding: 64px 0 40px;
	}

	.lede {
		font: 400 16px/1.6 var(--sans);
		color: var(--d-sub);
		max-width: 680px;
		margin: 16px 0 0;
		text-wrap: pretty;
	}

	.hero-row {
		display: flex;
		gap: 40px;
		align-items: flex-end;
		flex-wrap: wrap;
		margin-top: 32px;
	}

	.hero-num {
		font: 600 76px/1 var(--sans);
		color: var(--d-green);
		letter-spacing: -0.02em;
		font-variant-numeric: tabular-nums;
	}

	.hero-caption {
		font: 400 15px/1.55 var(--sans);
		color: var(--d-sub);
		max-width: 420px;
		margin: 10px 0 0;
	}

	.term {
		background: none;
		border: none;
		padding: 0;
		font: inherit;
		color: var(--d-text);
		border-bottom: 2px dotted var(--d-dotted);
		cursor: pointer;
	}

	.term-muted {
		color: var(--d-sub);
	}

	.termbox {
		margin-top: 10px;
		background: var(--d-panel);
		border: 1px solid var(--d-border);
		border-left: 3px solid var(--d-green);
		border-radius: 6px;
		padding: 12px 16px;
		max-width: 420px;
		font: 400 13px/1.55 var(--sans);
		color: var(--d-sub);
	}

	.termbox.wide {
		max-width: 720px;
		margin: 0 0 20px;
	}

	.termbox.dark {
		background: var(--d-bg);
		margin-top: 10px;
	}

	.termbox strong {
		font: 600 11px var(--mono);
		color: var(--d-text);
		letter-spacing: 0.06em;
	}

	.cta {
		display: inline-block;
		background: var(--d-green);
		color: var(--d-bg) !important;
		font: 600 14px var(--sans);
		padding: 12px 22px;
		border-radius: 8px;
		text-decoration: none;
	}

	.setup-grid {
		margin-top: 32px;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
		gap: 12px;
	}

	.setup-card {
		background: var(--d-panel);
		border: 1px solid var(--d-border);
		border-radius: 8px;
		padding: 16px 18px;
	}

	.setup-tag {
		font: 600 11px var(--mono);
		color: var(--d-green);
		letter-spacing: 0.1em;
		margin-bottom: 8px;
	}

	.setup-card p {
		font: 400 13px/1.55 var(--sans);
		color: var(--d-sub);
		margin: 0;
	}

	.section-sub {
		font: 400 13px/1.55 var(--sans);
		color: var(--d-faint);
		margin: 0 0 20px;
		max-width: 720px;
	}

	.section-sub.wide {
		max-width: 760px;
	}

	.card-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
		gap: 14px;
	}

	.card-grid.narrow {
		grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
	}

	.card-grid.quotes {
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
	}

	.card-grid.fine {
		grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
	}

	.cell-card {
		display: block;
		text-decoration: none;
		background: var(--d-panel);
		border: 1px solid var(--d-border);
		border-radius: 10px;
		padding: 20px;
		transition: border-color 0.15s;
	}

	.cell-card:hover {
		border-color: var(--d-green);
	}

	.cell-card.neg {
		background: #20161a;
		border-color: #5c2f36;
	}

	.cell-card.neg:hover {
		border-color: var(--d-red);
	}

	.cell-head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
	}

	.cell-tag {
		font: 600 10px var(--mono);
		letter-spacing: 0.12em;
	}

	.cell-order {
		font: 500 10px var(--mono);
		color: var(--d-faint);
	}

	.cell-title {
		font: 500 19px/1.25 var(--sans);
		color: var(--d-text);
		margin: 10px 0 2px;
	}

	.cell-delta {
		font: 600 34px/1 var(--sans);
		margin: 10px 0 6px;
		font-variant-numeric: tabular-nums;
	}

	.cell-blurb {
		font: 400 12.5px/1.5 var(--sans);
		color: var(--d-sub);
		min-height: 56px;
		margin: 0;
	}

	.mini {
		position: relative;
		height: 26px;
		margin-top: 12px;
	}

	.mini-track {
		position: absolute;
		left: 0;
		right: 0;
		top: 11px;
		height: 4px;
		background: var(--d-border);
		border-radius: 2px;
	}

	.mini-seg {
		position: absolute;
		top: 11px;
		height: 4px;
		border-radius: 2px;
	}

	.mini-tick {
		position: absolute;
		top: 6px;
		height: 14px;
		width: 2px;
		background: var(--d-sub);
	}

	.mini-tick.faint {
		background: var(--d-dotted);
	}

	.mini-live {
		position: absolute;
		top: 4px;
		height: 18px;
		width: 3px;
		border-radius: 2px;
	}

	.mini-labels {
		display: flex;
		justify-content: space-between;
		font: 400 10px var(--mono);
		color: var(--d-faint);
		margin-top: 2px;
	}

	.cell-gap {
		font: 400 11.5px/1.5 var(--mono);
		margin-top: 10px;
	}

	.cell-cta {
		font: 500 12px var(--sans);
		color: var(--d-green);
		margin-top: 12px;
	}

	.gauge-panel {
		background: var(--d-panel);
		border: 1px solid var(--d-border);
		border-radius: 10px;
		padding: 28px 32px 22px;
	}

	.gauge-caption {
		font: 600 11px var(--mono);
		letter-spacing: 0.12em;
		color: var(--d-faint);
		margin-bottom: 22px;
	}

	.gauge {
		position: relative;
		height: 134px;
	}

	.g-track {
		position: absolute;
		left: 0;
		right: 0;
		top: 52px;
		height: 8px;
		background: var(--d-border);
		border-radius: 4px;
	}

	.g-fill {
		position: absolute;
		top: 52px;
		height: 8px;
		border-radius: 4px;
		background: linear-gradient(90deg, #2c3440, #3d4a5c);
		left: 0;
	}

	.g-seg {
		position: absolute;
		top: 52px;
		height: 8px;
		background: var(--d-green);
	}

	.g-tick {
		position: absolute;
		width: 2px;
		background: var(--d-dotted);
	}

	.g-tick.strong {
		background: var(--d-sub);
	}

	.g-tick.dashed {
		background: none;
		border-left: 2px dashed var(--d-dotted);
	}

	.g-tick.lp {
		background: var(--d-faint);
	}

	.g-live {
		position: absolute;
		top: 36px;
		height: 40px;
		width: 4px;
		border-radius: 2px;
		background: var(--d-green);
	}

	.g-label {
		position: absolute;
		transform: translateX(-50%);
		text-align: center;
	}

	.g-label.top {
		top: 12px;
	}

	.g-label.below {
		top: 78px;
	}

	.g-label.rr {
		top: 108px;
	}

	.g-label.live {
		top: 2px;
	}

	.g-val {
		font: 600 13px var(--mono);
		color: var(--d-faint);
	}

	.g-val.strong {
		color: var(--d-sub);
	}

	.g-val.live {
		font: 600 16px var(--mono);
		color: var(--d-green);
	}

	.g-name {
		font: 400 10px var(--mono);
		color: var(--d-faint);
		white-space: nowrap;
	}

	.g-name.strong {
		color: var(--d-sub);
	}

	.g-name.live {
		font-weight: 500;
		color: var(--d-green);
	}

	.gauge-read {
		font: 400 13px/1.6 var(--sans);
		color: var(--d-sub);
		margin: 14px 0 0;
		max-width: 760px;
	}

	.green {
		color: var(--d-green);
	}

	.sub {
		color: var(--d-sub);
	}

	.seed-note {
		font: 400 12px/1.5 var(--mono);
		color: var(--d-faint);
		margin: 12px 0 0;
	}

	.fair-card {
		background: var(--d-panel);
		border: 1px solid var(--d-border);
		border-radius: 10px;
		padding: 18px 20px;
	}

	.fair-card .cell-tag {
		margin-bottom: 12px;
	}

	.fair-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 10px;
	}

	.fair-axis {
		font: 400 10px var(--mono);
		color: var(--d-faint);
	}

	.fair-num {
		font: 600 22px var(--sans);
		color: var(--d-text);
		margin-top: 2px;
		font-variant-numeric: tabular-nums;
	}

	.fair-ctl {
		font: 400 10px var(--mono);
		color: var(--d-faint);
		margin-top: 2px;
	}

	.fair-verdict {
		font: 400 11px/1.5 var(--mono);
		margin-top: 12px;
	}

	.judge-rows {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.judge-row {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
	}

	.judge-row .fair-axis {
		font-size: 11px;
	}

	.judge-num {
		font: 600 16px var(--sans);
		color: var(--d-text);
		font-variant-numeric: tabular-nums;
	}

	.of5 {
		font: 400 11px var(--sans);
		color: var(--d-faint);
	}

	.not-judged {
		font: 400 13px/1.5 var(--sans);
		color: var(--d-faint);
		padding: 8px 0;
		margin: 0;
	}

	.badge {
		font: 500 10px var(--mono);
		padding: 2px 6px;
		border-radius: 3px;
	}

	.badge.authored {
		background: #17332a;
		color: var(--d-green);
	}

	.badge.templated {
		background: var(--d-border);
		color: var(--d-sub);
	}

	.quote-card {
		background: var(--d-panel);
		border: 1px solid var(--d-border);
		border-left: 3px solid var(--d-green);
		border-radius: 0 10px 10px 0;
		padding: 18px 20px;
		margin: 0;
	}

	.quote-card blockquote {
		font: italic 400 15px/1.55 var(--sans);
		color: var(--d-text);
		margin: 0;
	}

	.quote-card figcaption {
		font: 500 10px var(--mono);
		color: var(--d-faint);
		margin-top: 12px;
	}

	.more-link {
		font: 400 12px var(--mono);
		margin: 14px 0 0;
	}

	.fine-card {
		background: var(--d-panel);
		border: 1px solid var(--d-border);
		border-radius: 10px;
		padding: 18px 20px;
	}

	.fine-tag {
		font: 600 11px var(--mono);
		letter-spacing: 0.1em;
		color: var(--d-amber);
		margin-bottom: 8px;
	}

	.fine-card p {
		font: 400 13px/1.6 var(--sans);
		color: var(--d-sub);
		margin: 0;
	}

	.cell-links {
		font: 400 11px var(--mono);
		color: var(--d-faint);
		margin-top: 28px;
		display: flex;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 8px;
	}

	.loading {
		padding: 64px 0;
		border-bottom: none;
	}

	.loading .sub {
		color: var(--d-sub);
	}

	.errorbox {
		margin: 64px 0;
		border: 1px solid #7f1d1d;
		background: #24161a;
		border-radius: 8px;
		padding: 1rem;
	}

	.errorbox p {
		margin: 0.4rem 0 0;
		font-size: 0.85rem;
		color: var(--d-sub);
	}

	.mono {
		font-family: var(--mono);
	}
</style>
