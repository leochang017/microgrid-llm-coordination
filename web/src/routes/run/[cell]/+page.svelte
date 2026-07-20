<!--
	Placeholder replay route — the real replay UI (SoC grid, scrubber, transfer arrows,
	message panel, why-panel) lands in a later Phase 4b task. It exists now so the
	prerender entries in vite.config.ts resolve and the static build succeeds.
-->
<script lang="ts">
	import { page } from '$app/state';
</script>

<main>
	<h1>Run replay — {page.params.cell}</h1>
	<p class="muted">Scaffold. The replay viewer lands in a later task.</p>
	<p><a href="/">Back to overview</a></p>
</main>

<style>
	main {
		margin: 0 auto;
		max-width: 60rem;
		padding: 3rem 1.5rem;
	}
</style>
