/**
 * Trust-circle presentation helpers, shared by the grid's corner ribbons and the
 * legend that decodes them.
 *
 * `meta.circles` is `affiliation type -> group id -> member house ids`. Geographic
 * 4-neighbour adjacency is deliberately NOT in there (see `types.ts`) — the grid
 * draws that layer from the row/col lattice instead, which is why it gets its own
 * faint-lines treatment rather than a ribbon colour.
 *
 * The `slot` is load-bearing, not decoration: it is the ribbon's band index counted
 * outward from the cell corner, so circle membership is encoded by POSITION as well
 * as by colour. Colour-blind readers get the same fact from the band position, the
 * legend spells the mapping out in words, and each house's own `aria-label`/`<title>`
 * already lists its circle ids in text.
 */
import type { CellMeta } from './types';

/** The three group ids the four committed cells actually ship. */
const CIRCLE_COLORS: Record<string, string> = {
	owner_a: '#f59e0b', // amber
	owner_b: '#2dd4bf', // teal
	agg_gridflex: '#a78bfa' // violet
};

/** Used only if a future export introduces a group id not in the map above. */
const FALLBACK_COLORS = ['#f472b6', '#60a5fa', '#facc15'];

export interface CircleGroup {
	/** Affiliation type, e.g. `owner`, `dr_aggregator`. */
	type: string;
	/** Group id, e.g. `owner_a`. */
	group: string;
	members: string[];
	color: string;
	/** Band index outward from the cell corner; also the legend's ordering. */
	slot: number;
}

/**
 * Flatten `meta.circles` into a stable, ordered list. Order is the JSON's own key
 * order, which for every committed cell is owner_a, owner_b, agg_gridflex.
 */
export function circleGroups(meta: CellMeta): CircleGroup[] {
	const out: CircleGroup[] = [];
	for (const [type, groups] of Object.entries(meta.circles)) {
		for (const [group, members] of Object.entries(groups)) {
			const slot = out.length;
			out.push({
				type,
				group,
				members,
				color: CIRCLE_COLORS[group] ?? FALLBACK_COLORS[slot % FALLBACK_COLORS.length],
				slot
			});
		}
	}
	return out;
}

/** house id -> the groups it belongs to, in `circleGroups` order. */
export function groupsByHouse(groups: CircleGroup[]): Map<string, CircleGroup[]> {
	const m = new Map<string, CircleGroup[]>();
	for (const g of groups) {
		for (const id of g.members) {
			const list = m.get(id);
			if (list) list.push(g);
			else m.set(id, [g]);
		}
	}
	return m;
}
