# Reference Runs (Phase 2)

These are cache-warmed reference runs that ship with the repo so any reviewer can
re-run Phase 2 experiments byte-identically without paying for the LLM API.

Each subdirectory under `<scenario>/llm_agent/<cell>/` contains:

- `state.jsonl` / `events.jsonl` / `messages.jsonl` / `config.json` / `summary.json`
  — exactly the same outputs `scripts/run.py` produces.
- `llm_cache/<model>/<sha256>.json` — every LLM call's prompt + response,
  content-addressed. The `LLMClient` checks this cache before hitting the API;
  cache-warm replays make zero network calls.

## Re-running

```bash
python -m scripts.run \
    --scenario configs/scenarios/haves_havenots__llm.yaml \
    --reference-cell clean
```

This re-uses the cache; the output `state.jsonl` etc. should be byte-identical
to the files in this directory.

## Status (2026-06-13)

- `haves_havenots/llm_agent/clean/` — primary reference run (haves_havenots__llm.yaml).
- `haves_havenots/llm_agent/defectors/` — **deferred follow-up** (Phase 2 ships
  with mock-LLM evidence only; live run is a tracked TODO).
- `long_outage_72h/llm_agent/clean/` — **deferred follow-up**.

Mock-LLM integration tests in `tests/test_llm_agent_{integration,replay,failure_axes}.py`
are the Phase 2 evidence base; live runs round out the reproducibility story.
