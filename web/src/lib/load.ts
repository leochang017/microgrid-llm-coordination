import type { CellExplanations, CellMessages, CellMeta, CellTicks, Msg, Slug } from './types';

export interface LoadedCell {
	meta: CellMeta;
	ticks: CellTicks;
	messages: Msg[];
	/** `null` for cells with no committed explanations artifact (noise, comm). */
	explanations: CellExplanations | null;
	/** Tick index -> the messages sent on that tick, built once at load time. */
	msgsByTick: Map<number, Msg[]>;
}

export type FetchFn = typeof fetch;

async function getJson<T>(url: string, fetchFn: FetchFn): Promise<T> {
	const res = await fetchFn(url);
	if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
	return (await res.json()) as T;
}

/**
 * Optional artifact: a missing file must resolve to `null`, not throw.
 *
 * Only the noise and comm cells lack `explanations.json` today, but the whole
 * point of the `| null` return is that callers cannot assume otherwise.
 */
async function getJsonOrNull<T>(url: string, fetchFn: FetchFn): Promise<T | null> {
	try {
		const res = await fetchFn(url);
		if (!res.ok) return null;
		return (await res.json()) as T;
	} catch {
		return null;
	}
}

/** Fetch one cell's committed JSON payload. All four requests go out in parallel. */
export async function loadCell(slug: Slug, fetchFn: FetchFn = fetch): Promise<LoadedCell> {
	const base = `/data/${slug}`;
	const [meta, ticks, messages, explanations] = await Promise.all([
		getJson<CellMeta>(`${base}/meta.json`, fetchFn),
		getJson<CellTicks>(`${base}/ticks.json`, fetchFn),
		getJson<CellMessages>(`${base}/messages.json`, fetchFn),
		getJsonOrNull<CellExplanations>(`${base}/explanations.json`, fetchFn)
	]);

	const msgsByTick = new Map<number, Msg[]>();
	for (const m of messages.messages) {
		const bucket = msgsByTick.get(m.t);
		if (bucket) bucket.push(m);
		else msgsByTick.set(m.t, [m]);
	}

	return { meta, ticks, messages: messages.messages, explanations, msgsByTick };
}
