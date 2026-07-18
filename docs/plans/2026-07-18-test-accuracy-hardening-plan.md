# Plan A — Test-suite accuracy hardening (2026-07-18)

> **Batch position: 2 of 4** (run after `2026-07-18-phase3-accuracy-plan.md`, before the cleanup and full-review plans). One execution session.
> **Source brief:** `docs/notes/2026-07-18-audit-cleanup-brief.md`, items 1 (partial) and 2.

## Goal

Make the test suite measure what it claims: no order-dependent tests, no env leaks, no untested live-LLM error paths, exact pins on the end-to-end surfaces that today only assert "result is in [0, 1]", and a mypy net that actually covers `scripts/` (which the docs' "mypy --strict clean" claim currently excludes).

## Context (verified 2026-07-18 by static audit)

- CI installs `.[dev,data]` and runs `ruff check sim tests scripts`, bare `mypy` (→ `pyproject.toml files=["sim"]` — **`scripts/` and `tests/` are never type-checked**), and `pytest -v`. Claimed 349 tests reconcile exactly (320 `def test_` + 29 parametrize expansions; 21 scenario YAMLs drive +20 of those).
- **Zero** skip/skipif/xfail/importorskip markers anywhere in `tests/` — nothing silently skips. Determinism coverage is strong (byte-identical replay, cross-process PYTHONHASHSEED test).
- Real gaps found:
  1. `tests/test_strategy_llm_agent.py:167` `test_negotiation_counters_reach_summary` calls `update_summary_with_counts(tmp_path)` with **no registry**, relying on the module-global `_REGISTRY` set by whichever test ran `prepare()` earlier — fails or false-passes in isolation.
  2. `tests/test_adapters.py:147-159` writes `os.environ["TZ"]` + `time.tzset()` with a manual try/finally instead of `monkeypatch` — a hard crash mid-test can leak TZ into later tests.
  3. `sim/agents/llm.py:187-220`: only `RateLimitError` is exercised in the retry loop; `APIConnectionError` / `InternalServerError` (same except-tuple, lines 211-215) and the **retry-exhaustion re-raise** (lines 219-220) have no test. The OAuth `auth_token=` vs `api_key=` SDK-constructor routing (lines 164-170) is never asserted directly.
  4. Reference-cell resume (`_reference_cache_dir`) is tested only as path resolution (`tests/test_strategy_llm_agent.py:193-210`); there is no end-to-end test that a resumed run replays from cache with **zero** provider calls — the property that twice saved paid runs in the field.
  5. Weak e2e assertions: `tests/test_engine.py:86,141,192` and `tests/test_llm_agent_integration.py:93` assert only ranges; `tests/test_llm_agent_failure_axes.py:85-121` asserts only `a != b` vs clean.
  6. The "349 tests" figure silently drifts with the scenario-YAML count (data-driven parametrize).

## Decisions

- **mypy expands to `scripts/`, not `tests/`.** `scripts/` is production-adjacent (imported by the suite and by paper tooling); typing `tests/` under `--strict` is high-cost/low-yield. FLAGGED: if Leo wants `tests/` typed later, that is a separate batch.
- **Exact pins are derived, not invented**: run the deterministic scenario once, copy the full-precision value, pin with `pytest.approx(abs=5e-7)` — the same methodology as `tests/test_golden_numbers.py`. This plan runs AFTER the Phase-3 accuracy plan (Plan B) precisely so commitment-behavior changes land first and pins are derived once.
- Failure-axis tests get exact pins too (mock runs are byte-deterministic), replacing bare `a != b`. A future intentional physics change must consciously re-derive them — that is the point.

## Global constraints

- TDD: red → green per task; never skip the red run.
- After each task: `ruff check sim tests scripts && mypy && pytest -q` must pass; pre-commit hooks gate the commit (re-stage if hooks reformat; never `--no-verify`).
- Frozen: every pin in `tests/test_golden_numbers.py`, the committed-summary pin `0.6725764138021589` in `tests/test_figures.py`, all determinism/replay tests. If any of these breaks, STOP — you introduced a behavior change; this plan must not change any `sim/` behavior (Task 5's mypy fixes must be annotation-only; if a mypy fix would alter runtime behavior, stop and report).
- One conventional commit per task, progress-log row in CLAUDE.md in the same commit, no Claude attribution.
- Task 5 touches `pyproject.toml` → the clean-install dry-run rule applies (fresh venv, `pip install -e ".[dev,data]"`, full suite) before that commit. After every push, glance at `gh run list --limit 1`.

## Traceability

| Brief item | Covered by |
|---|---|
| 2 — "make sure the tests ran as accurately as possible" | Tasks 1-8 (all) |
| 1 — "review all the code" (test-code portion) | Tasks 1-4, 6 fix every defect the 2026-07-18 test-code audit found; the full source review is Plan `2026-07-18-full-repo-review-plan.md` |

---

## Task 1 — Make `test_negotiation_counters_reach_summary` self-sufficient

**Red:** `.venv/bin/python -m pytest "tests/test_strategy_llm_agent.py::test_negotiation_counters_reach_summary" -q` **in isolation**. Expected: fails (or errors) because no `prepare()` has populated the module-global `_REGISTRY` in this process. If it passes in isolation, inspect why before proceeding (a conftest import may have prepared a registry — the fix below is still correct, but record the observed behavior in the commit body).

**Current code** (`tests/test_strategy_llm_agent.py:180-190`):
```python
    # and update_summary_with_counts writes the detailed dict through:
    (tmp_path / "summary.json").write_text("{}")
    llm_strat.update_summary_with_counts(tmp_path)  # module-global registry from last prepare
    detailed = json.loads((tmp_path / "summary.json").read_text())["llm_call_counts_detailed"]
```

**Replace with** (uses the file's existing `_prepare_with_failure` helper — see its use at line 158 — and the explicit `registry=` kwarg shipped in P2.9 T16):
```python
    # and update_summary_with_counts writes the detailed dict through, using an
    # explicitly-prepared registry — this test must pass in isolation, with no
    # reliance on the module-global left behind by a previously-run test:
    from sim.agents.failure_modes import FailureModeConfig

    decide, _scenario, _households = _prepare_with_failure(tmp_path, FailureModeConfig())
    (tmp_path / "summary.json").write_text("{}")
    llm_strat.update_summary_with_counts(tmp_path, registry=decide.registry)
    detailed = json.loads((tmp_path / "summary.json").read_text())["llm_call_counts_detailed"]
```
Contingency: if `FailureModeConfig()` requires arguments (check its dataclass defaults), use `FailureModeConfig(defector_fraction=0.0)`.

**Green:** the isolated command above passes, then the full file: `.venv/bin/python -m pytest tests/test_strategy_llm_agent.py -q`.

**Commit:** `test(accuracy): negotiation-counter test passes in isolation (no module-global registry dependence)`

## Task 2 — TZ test: monkeypatch instead of raw `os.environ`

**Current code** (`tests/test_adapters.py:143-161`): manual `old_tz = os.environ.get("TZ")` / try-finally restore (quoted in the audit; read the block before editing).

**Replace the function body** so env restoration is owned by pytest even on hard failure:
```python
def test_nrel_noise_is_timezone_independent(monkeypatch) -> None:
    """The per-(seed, t) noise draw must not depend on the machine's TZ env.

    Pre-2026-07-06 the seed came from naive datetime.timestamp(), which Python
    interprets in the machine's local timezone — same code, same seed, same
    scenario gave different numbers on differently-configured machines.
    """
    import time

    t = datetime(2024, 7, 1, 9, 30)
    try:
        monkeypatch.setenv("TZ", "UTC")
        time.tzset()
        kw_utc = NRELSolar(csv_path=_FIXTURE_NREL, seed=7).get_kw(t)
        monkeypatch.setenv("TZ", "America/Chicago")
        time.tzset()
        kw_chicago = NRELSolar(csv_path=_FIXTURE_NREL, seed=7).get_kw(t)
    finally:
        # monkeypatch restores the TZ env var; tzset() must run afterwards so the
        # process actually re-reads it.
        monkeypatch.undo()
        time.tzset()
    assert kw_utc == kw_chicago
```

**Red first:** temporarily this is a refactor of a passing test — the red step here is running the file and confirming the test still passes AND `python -c "import os; assert 'TZ' not in os.environ"` style leak-checking isn't needed (monkeypatch owns it). Run: `.venv/bin/python -m pytest tests/test_adapters.py -q`.

**Commit:** `test(accuracy): TZ-independence test restores env via monkeypatch`

## Task 3 — Pin the untested LLM-client error paths (3 new tests)

Append to `tests/test_llm_client.py`, matching the file's existing style (see the retry test at lines 142-177 for the fake-client pattern):

```python
def test_anthropic_client_raises_after_retry_exhaustion(tmp_path) -> None:
    import anthropic as anthropic_sdk

    fake_client = MagicMock()
    err = anthropic_sdk.RateLimitError(
        message="slow down", response=MagicMock(status_code=429), body=None
    )
    fake_client.messages.create.side_effect = err  # every attempt fails

    with (
        patch("sim.agents.llm.anthropic.Anthropic", return_value=fake_client),
        patch("sim.agents.llm.time.sleep") as sleeper,
    ):
        adapter = AnthropicLLMClient(
            cache=PromptCache(local_dir=tmp_path),
            api_key="sk-test",
            max_retries=3,
            base_backoff_s=0.1,
        )
        req = LLMRequest(
            model="claude-haiku-4-5-20251001", system="sys", user="hi", max_tokens=64
        )
        with pytest.raises(anthropic_sdk.RateLimitError):
            adapter.call(req)

    assert fake_client.messages.create.call_count == 3  # exactly max_retries attempts
    assert sleeper.call_count == 3


def test_anthropic_client_retries_on_connection_and_server_errors(tmp_path) -> None:
    import anthropic as anthropic_sdk

    fake_msg = MagicMock()
    fake_msg.content = [MagicMock(text="ok")]
    fake_msg.usage = MagicMock(input_tokens=1, output_tokens=1)

    conn_err = anthropic_sdk.APIConnectionError(request=MagicMock())
    server_err = anthropic_sdk.InternalServerError(
        message="boom", response=MagicMock(status_code=500), body=None
    )
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = [conn_err, server_err, fake_msg]

    with (
        patch("sim.agents.llm.anthropic.Anthropic", return_value=fake_client),
        patch("sim.agents.llm.time.sleep"),
    ):
        adapter = AnthropicLLMClient(
            cache=PromptCache(local_dir=tmp_path),
            api_key="sk-test",
            max_retries=5,
            base_backoff_s=0.1,
        )
        req = LLMRequest(
            model="claude-haiku-4-5-20251001", system="sys", user="hi", max_tokens=64
        )
        resp = adapter.call(req)

    assert resp.text == "ok"
    assert fake_client.messages.create.call_count == 3


def test_anthropic_client_oauth_key_routes_to_auth_token(tmp_path) -> None:
    # sk-ant-oat… must construct the SDK client with auth_token= (Bearer header);
    # anything else uses api_key=. Asserted at the constructor, not a wrapper.
    with patch("sim.agents.llm.anthropic.Anthropic") as ctor:
        AnthropicLLMClient(cache=PromptCache(local_dir=tmp_path), api_key="sk-ant-oat01-FAKE")
    kwargs = ctor.call_args.kwargs
    assert kwargs["auth_token"] == "sk-ant-oat01-FAKE"
    assert kwargs["api_key"] == ""
    assert kwargs["max_retries"] == 0

    with patch("sim.agents.llm.anthropic.Anthropic") as ctor2:
        AnthropicLLMClient(cache=PromptCache(local_dir=tmp_path), api_key="sk-ant-api-FAKE")
    kwargs2 = ctor2.call_args.kwargs
    assert kwargs2["api_key"] == "sk-ant-api-FAKE"
    assert "auth_token" not in kwargs2
```

Contingency: if `anthropic.APIConnectionError(request=MagicMock())` rejects the mock, construct with `httpx.Request("POST", "https://api.anthropic.com")` (httpx is a declared dependency).

**Red:** run just the three new tests before implementation-side changes — they should pass immediately against current `sim/agents/llm.py` behavior (they are pinning existing behavior, so "red" here means: deliberately break the code once — e.g. change `raise last_exc` to `return` locally — confirm the exhaustion test fails, revert). Do the mutation check; it is the whole point of pinning.

**Commit:** `test(llm): pin retry exhaustion, connection/server-error retries, and OAuth ctor routing`

## Task 4 — End-to-end reference-cell resume test (zero paid calls on replay)

New test in `tests/test_llm_agent_replay.py`, modeled on `test_two_runs_with_same_mock_are_byte_identical` (lines 61-99 — reuse its run-helper pattern and mock client):

1. Run a small mock-LLM cell into `tmp_path/ref/…` (this writes the run's `llm_cache`).
2. Point resume at it (the same mechanism the live playbook uses: `MICROGRID_REFERENCE_CELL` env var via `monkeypatch.setenv`, or the `--reference-cell`-equivalent kwarg — mirror `tests/test_strategy_llm_agent.py:193-210` for how the path resolves).
3. Second run: wrap the mock client so any **provider-level** call raises `AssertionError("paid call attempted — cache resume failed")`; only cache hits are allowed.
4. Assert the second run completes and its `summary.json` metrics equal the first run's.

Acceptance: the test fails if you disable the reference-cache tier (e.g. temporarily point `_reference_cache_dir` to return `None` — do this mutation check once, revert), and passes on current code.

**Commit:** `test(llm): end-to-end reference-cell resume replays with zero provider calls`

## Task 5 — mypy covers `scripts/` (config + annotation fixes)

1. `pyproject.toml:38`: `files = ["sim"]` → `files = ["sim", "scripts"]`, and add:
```toml
[[tool.mypy.overrides]]
module = ["matplotlib", "matplotlib.*"]
ignore_missing_imports = true
```
2. `.pre-commit-config.yaml` mypy hook scope: `^sim/.*\.py$` → `^(sim|scripts)/.*\.py$`.
3. Run `.venv/bin/python -m mypy` — fix every error in `scripts/` with real annotations (json loads are `dict[str, Any]`; no bare `# type: ignore` without an inline reason; no runtime-behavior changes). If the error count exceeds ~40, stop and report the count before proceeding.
4. Verification gate: full suite + ruff + mypy, **then the clean-install dry-run** (pyproject touched): fresh venv in the scratchpad, `pip install -e ".[dev,data]"`, `python -m pytest -q` — the historical failure mode this rule exists for is packaging, not types.

**Commit:** `chore(types): extend mypy --strict to scripts/ (annotations, matplotlib override, pre-commit scope)`

## Task 6 — Exact pins on the weak e2e assertions

For each site: run the test's scenario once via the suite itself with a temporary `print`/`assert 0` to capture the full-precision value, or add the pin speculatively at 6 dp and correct from the failure diff — then pin with `pytest.approx(value, abs=5e-7)` **keeping** the existing range assertion as a second line of defense. Sites:

1. `tests/test_engine.py:86` (`test_run_smoke_no_coordination`), `:141` (`test_run_resstock_path_end_to_end`), `:192` (`test_run_real_data_path_end_to_end`) — pin `served_load_fraction` exactly; add a comment: `# exact pin derived 2026-07-18; re-derive deliberately on any physics change`.
2. `tests/test_llm_agent_integration.py:93` — pin the mock-pipeline `served_load_fraction` exactly and pin the message count `len(msgs)` exactly (byte-deterministic mock).
3. `tests/test_llm_agent_failure_axes.py:85-87, 99-102, 118-121` — replace each bare `a != b` with exact pins of the treated cell's `served_load_fraction` (and keep the ≠-clean assertion). These runs are seeded and deterministic; the pin freezes the causal effect size, not just its existence.

Stability check: run the full suite **twice** and `pytest tests/test_engine.py tests/test_llm_agent_integration.py tests/test_llm_agent_failure_axes.py -q` once more — identical results all three times (byte-determinism makes exact pins free; that's the project's own golden-pin rationale).

**Commit:** `test(accuracy): exact pins on e2e served-load and failure-axis effects (were range/inequality-only)`

## Task 7 — Pin the scenario-YAML count

New test in `tests/test_scenario.py`, next to the glob loop at line 297:

```python
def test_shipped_scenario_count_is_pinned() -> None:
    # The suite's total test count is data-driven through this glob (each YAML
    # parametrizes the strict-load loop). Pin the count so adding/removing a
    # scenario is a visible, deliberate act rather than silent test-count drift.
    yamls = sorted((Path(__file__).parent.parent / "configs" / "scenarios").glob("*.yaml"))
    assert len(yamls) == 21, [p.name for p in yamls]
```
(Match the import/path style already used at line 297; if the file exposes a module-level `_SCENARIO_DIR`, reuse it.)

**Commit:** `test(accuracy): pin shipped scenario-YAML count (test total no longer drifts silently)`

## Task 8 — Wrap: docs tell the truth about the net

1. README + CLAUDE.md: everywhere "mypy --strict" is claimed, state the real scope "mypy --strict (sim/ + scripts/)". Update the stated test count to the actual post-batch number (`pytest --collect-only -q | tail -1`).
2. Full verify: `ruff check sim tests scripts && mypy && pytest -q`, twice.
3. Security grep per CLAUDE.md rule (`git diff --cached | grep -cE 'sk-ant-(api|oat)[0-9a-zA-Z_-]{15,}'` → 0; note: Task 3's `sk-ant-oat01-FAKE` fixture is deliberately below the 15-char run and must not match — if it does, the fixture string changed; fix the fixture, not the rule).
4. Commit, push, `gh run list --limit 1`.

**Commit:** `docs(tests): sync test count + real mypy scope after accuracy hardening`
