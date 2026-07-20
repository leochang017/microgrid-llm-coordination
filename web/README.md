# Microgrid LLM coordination — demo

A static viewer that replays four committed simulation runs from the
microgrid LLM-coordination research project (see the repo root
`README.md` and `docs/phase3_results.md` for the research question and results).

This is a **read-only replay of already-run experiments**. There is no
backend, no API keys, and no live model calls — everything the browser
fetches is prerendered static JSON exported from committed run artifacts
under `reference_runs/` at the repo root.

## Regenerating the data

The JSON under `static/data/` **is committed** (~12 MB across the four cells,
so the deployed site needs no build-time Python), but it is generated, not
hand-written: a Python exporter reads the committed run artifacts and writes
it. To regenerate it, run this from the **repo root** (not `web/`), with the
project's `.venv` active, then commit the diff:

```sh
python -m scripts.export_demo_data --out web/static/data
```

The exported numbers are pinned by `tests/test_demo_data_pins.py` (also at the
repo root) against `scripts.figures.EXPECTED_LIVE` — the same golden pins
`python -m scripts.figures --check` asserts the committed run artifacts against.
That test fails, on exact float equality, if the export ever drifts from them.

## Data contract

`src/lib/types.ts` is the frozen TypeScript contract for every file the
exporter writes (`meta.json`, `ticks.json`, `messages.json`,
`explanations.json`). Read it before touching `src/lib/load.ts` or any
component that consumes cell data — it documents real gotchas measured
against the actual exports (e.g. `explanations.json` is absent for two of
the four cells, and `messages.json` contains zero `INFORM` rows because
templated INFORMs are downsampled out at export time).

## Developing

```sh
npm install
npm run dev          # start a dev server
npm run check         # svelte-kit sync + svelte-check, must stay 0 errors/warnings
npm run build          # production build — must prerender `/` and all four `/run/<cell>/` routes
npm run preview        # preview the production build
```

## Where the SvelteKit config lives

This project has **no `svelte.config.js`**. With
`@sveltejs/vite-plugin-svelte` 7, the kit's `adapter` and `prerender`
options are passed inline to the `sveltekit()` plugin instead — see
`vite.config.ts`. If you're looking for the adapter or the list of
prerendered routes, that's the file, not a `svelte.config.js` that doesn't
exist.

## Deploying

Static build (`@sveltejs/adapter-static`), deployed via Vercel's Git
integration rooted at this `web/` directory. See `vercel.json`.
