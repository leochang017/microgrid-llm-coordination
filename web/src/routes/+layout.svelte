<!--
	Root layout.

	The "research demo — not a deployment" footer lives HERE, not on the overview
	route, because all five routes are separately prerendered and separately
	deep-linkable: each `/run/<cell>/` page renders a served-load figure, a signed
	gap-closed sentence and a Gini/Jain row — every performance claim this demo
	makes — and a reader arriving from a shared link or a search result must see the
	disclaimer on that page, not only on the front door. Putting it in the layout is
	what makes the advisor's rule structurally true instead of true on one route.
-->
<script lang="ts">
	import favicon from '$lib/assets/favicon.svg';
	import '../app.css';

	const REPO = 'https://github.com/leochang017/microgrid-llm-coordination';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

{@render children()}

<footer class="site-footer">
	<p>
		<strong>Research demo — not a deployment.</strong> These are offline simulation replays produced
		for a research project. Nothing here is a validated grid control system, and no claim of real-world
		deployment readiness is intended.
	</p>
	<p class="muted">
		Source and data: <a href={REPO}>{REPO}</a> · MIT licensed.
	</p>
</footer>

<style>
	.site-footer {
		margin: 0 auto;
		/* Matches the WIDEST route's content column (`/run/[cell]` is 78rem), so the
		   footer never sits narrower than the page above it. It is not flush on every
		   route: the overview column is 68rem, so at wide viewports the footer runs
		   80px proud on each side there. Measured at 1440px — run 89-1337 vs main
		   89-1337; overview 89-1337 vs main 169-1257. */
		max-width: 78rem;
		padding: 0 1.5rem 3rem;
		font-size: 0.85rem;
	}

	.site-footer p {
		border-top: 0 solid var(--border);
		margin: 0 0 0.5rem;
		max-width: 68ch;
	}

	.site-footer p:first-child {
		border-top-width: 1px;
		padding-top: 1.25rem;
	}
</style>
