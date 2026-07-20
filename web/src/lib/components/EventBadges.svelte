<!--
	The physics-said-no strip: engine events at the currently scrubbed tick, grouped by
	kind, with the houses involved on hover.

	This is the channel that explains why promised energy did not move — the agents
	negotiate in messages, but the engine settles transfers against sender caps, receiver
	headroom and the bus, and these events are what it emits when it clips one.

	Kinds are read from the data, never hardcoded: whatever `ticks.events` carries at this
	tick is what gets a badge. Across the four committed cells only `sender_dod_floor` and
	`receiver_full` ever appear, so nothing here asserts a kind that may not exist.

	`sender_dod_floor` is the simulator's own event name and is deliberately shown
	verbatim so it matches the committed `events.jsonl`, but the name is narrower than the
	behaviour: it fires on ANY sender-side cap, including the sender's own load deficit
	and its battery rate limit, not only the depth-of-discharge floor. The hover text says
	so rather than letting the label mislead.

	`receiver_full` is the same class of misnomer and its hover text is written against the
	cap the engine actually applies, not against the name. `_transfer_caps` in
	`sim/engine.py` sets the receiver cap to
	`max(0, load - solar) + max(0, absorb_batt_kw - own_surplus)` — the receiver's own
	unmet load (served by DC bypass, needing no battery headroom at all) plus only the
	battery intake its own solar surplus is not already consuming. So the event also fires
	on a receiver with plenty of headroom that is busy filling it from its own panels, or
	one whose load deficit is simply used up. "Battery full" is one case of several.

	Counts are text, not colour — the badge colour is decoration and every fact here is
	also spelled out in the badge's own `title`.
-->
<script lang="ts">
	import type { CellTicks } from '$lib/types';
	import type { ReplayState } from '$lib/replay.svelte';

	interface Props {
		ticks: CellTicks;
		state: ReplayState;
	}

	const { ticks, state }: Props = $props();

	const KIND_HELP: Record<string, string> = {
		sender_dod_floor:
			'the sender could not release the energy it had promised — its own load, battery rate limit or depth-of-discharge floor capped the send',
		receiver_full:
			'more energy arrived than the receiver could usefully take — it can absorb only what its own load still needs, plus whatever battery headroom its own solar is not already filling'
	};

	interface Badge {
		kind: string;
		count: number;
		houses: string[];
	}

	const badges = $derived.by<Badge[]>(() => {
		const events = ticks.events[state.tick] ?? [];
		const byKind = new Map<string, Badge>();
		for (const e of events) {
			const b = byKind.get(e.kind);
			if (b) {
				b.count += 1;
				b.houses.push(...e.houses);
			} else {
				byKind.set(e.kind, { kind: e.kind, count: 1, houses: [...e.houses] });
			}
		}
		return [...byKind.values()];
	});

	function badgeTitle(b: Badge): string {
		const help = KIND_HELP[b.kind] ?? 'engine event';
		const houses = [...new Set(b.houses)].sort();
		return `${b.kind} — ${help}. Houses: ${houses.join(', ')}`;
	}
</script>

<div class="events">
	<span class="lead muted">physics said no:</span>
	{#if badges.length === 0}
		<span class="muted">nothing clipped at this tick</span>
	{:else}
		<ul>
			{#each badges as b (b.kind)}
				<li><span class="badge mono" title={badgeTitle(b)}>{b.kind} ×{b.count}</span></li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	.events {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.78rem;
	}

	.lead {
		letter-spacing: 0.04em;
		text-transform: uppercase;
		font-size: 0.7rem;
	}

	ul {
		list-style: none;
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin: 0;
		padding: 0;
	}

	.badge {
		display: inline-block;
		border: 1px solid var(--border);
		border-radius: 999px;
		padding: 0.15rem 0.55rem;
		background: var(--bg);
		font-variant-numeric: tabular-nums;
		cursor: help;
	}
</style>
