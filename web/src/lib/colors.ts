import type { Performative } from './types';

/** Nine viridis stops, low SoC (dark purple) to full (yellow). */
export const VIRIDIS = [
	'#440154',
	'#472d7b',
	'#3b528b',
	'#2c728e',
	'#21918c',
	'#28ae80',
	'#5ec962',
	'#addc30',
	'#fde725'
] as const;

function hexToRgb(hex: string): [number, number, number] {
	return [
		parseInt(hex.slice(1, 3), 16),
		parseInt(hex.slice(3, 5), 16),
		parseInt(hex.slice(5, 7), 16)
	];
}

const STOPS: [number, number, number][] = VIRIDIS.map(hexToRgb);

/** Piecewise-linear viridis interpolation for a state-of-charge fraction in [0, 1]. */
export function socColor(frac: number): string {
	const f = Number.isFinite(frac) ? Math.min(1, Math.max(0, frac)) : 0;
	const x = f * (STOPS.length - 1);
	const i = Math.min(STOPS.length - 2, Math.floor(x));
	const w = x - i;
	const a = STOPS[i];
	const b = STOPS[i + 1];
	const c = [0, 1, 2].map((k) => Math.round(a[k] + (b[k] - a[k]) * w));
	return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

/** One colour per message performative, used by the message panel and transfer arrows. */
export const PERF_COLORS: Record<Performative, string> = {
	REQUEST: '#f59e0b',
	OFFER: '#38bdf8',
	ACCEPT: '#4ade80',
	COUNTER: '#c084fc',
	REJECT: '#f87171',
	INFORM: '#94a3b8'
};
