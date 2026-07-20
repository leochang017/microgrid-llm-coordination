import { base } from '$app/paths';
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
 *
 * "Missing" means a real 404 — the file genuinely isn't in the export. A 500,
 * a CDN failure, or any other non-404 non-ok status is a real failure and must
 * throw, not be swallowed into a silent `null` that the UI would render as
 * "no explanations available" for a cell that actually has them.
 *
 * The one exception is `res.json()` itself throwing a parse error: a static
 * host serving a 200 HTML SPA-fallback page in place of a missing file is a
 * real deployment scenario, and it should also read as "absent."
 */
async function getJsonOrNull<T>(url: string, fetchFn: FetchFn): Promise<T | null> {
	const res = await fetchFn(url);
	if (res.status === 404) return null;
	if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
	try {
		return (await res.json()) as T;
	} catch {
		return null;
	}
}

/** Fetch one cell's committed JSON payload. All four requests go out in parallel. */
export async function loadCell(slug: Slug, fetchFn: FetchFn = fetch): Promise<LoadedCell> {
	// `base` (imported above from `$app/paths`) is `paths.base` — empty string
	// unless a base path is configured; prefixing here keeps this working under
	// any deploy path, not just root.
	const dataBase = `${base}/data/${slug}`;
	const [meta, ticks, messages, explanations] = await Promise.all([
		getJson<CellMeta>(`${dataBase}/meta.json`, fetchFn),
		getJson<CellTicks>(`${dataBase}/ticks.json`, fetchFn),
		getJson<CellMessages>(`${dataBase}/messages.json`, fetchFn),
		getJsonOrNull<CellExplanations>(`${dataBase}/explanations.json`, fetchFn)
	]);

	const msgsByTick = new Map<number, Msg[]>();
	for (const m of messages.messages) {
		const bucket = msgsByTick.get(m.t);
		if (bucket) bucket.push(m);
		else msgsByTick.set(m.t, [m]);
	}

	return { meta, ticks, messages: messages.messages, explanations, msgsByTick };
}
