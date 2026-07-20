/**
 * Grid coordinate helpers, shared by every layer drawn on the replay canvas.
 *
 * These used to live as private constants inside `NeighborhoodGrid.svelte`. They
 * were lifted here when the message overlay landed (Task 7): that component was
 * already ~330 lines carrying three layers, and a fourth inline layer would have
 * made it the place where every future overlay accretes. Extracting the geometry
 * lets `MessageArcs.svelte` be its own component on the SAME canvas — it renders a
 * `<g>` inside the grid's `<svg>`, so it shares the viewBox without sharing the file.
 *
 * The numbers are the canvas contract: cells are 96x96 on a 109-unit pitch starting
 * at 6, inside `viewBox="0 0 660 560"`. Change them here and every layer moves together.
 */
import type { CellMeta } from './types';

export const CELL = 96;
export const STEP = 109;
export const ORIGIN = 6;
export const HALF = CELL / 2;

export const VIEW_W = 660;
export const VIEW_H = 560;

export function cellX(col: number): number {
	return ORIGIN + col * STEP;
}

export function cellY(row: number): number {
	return ORIGIN + row * STEP;
}

/** house id -> the centre point of its cell. */
export function houseCenters(meta: CellMeta): Map<string, [number, number]> {
	return new Map(meta.houses.map((h) => [h.id, [cellX(h.col) + HALF, cellY(h.row) + HALF]]));
}
