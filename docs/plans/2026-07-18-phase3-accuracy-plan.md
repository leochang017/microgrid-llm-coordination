# Plan B — Phase 3 accuracy completion (2026-07-18)

> **Batch position: 1 of 4** — run FIRST (Plans A/D/C follow). One execution session.
> **Source brief:** `docs/notes/2026-07-18-audit-cleanup-brief.md`, item 6 (+ item 1 for the negotiation path).
> **⚠️ Money task inside (Task 8):** Leo authorized the comm-cell live re-run on 2026-07-18 (planbatch decision "Fix now + re-run comm cell"), estimated $4–7, **hard cap $8**. That authorization covers exactly ONE re-run attempt chain of `haves_havenots_solar__comm` @ seed 23 (identical-command resumes of an interrupted attempt included — they replay cached calls at $0). If projected spend exceeds the cap, or anything forces a different cell/seed, STOP and ask Leo — a bare "continue" after an interruption is not new spend authorization.

## Goal

Close every Phase-3 accuracy gap found by the 2026-07-18 audit: fix the three confirmed follow-up defects (C1 commitment-vs-dropped-reply, C2 below-threshold committed export, C3 missing defector provenance), re-run the one live cell those bugs materially shaped (comm@23), wire the completed Sonnet capability ablation into the results pipeline, and purge every stale "pending/optional" claim from README / results docs.

## Context (audit findings, all verified 2026-07-18)

- **Every published Phase-3 number already recomputes exactly** from committed `reference_runs/` summaries (clean +5.8±1.0 / 29.0%±2.9; defectors +2.3; noise +0.87; comm −4.6; judge 3.03/4.05/4.46 & 3.00/3.97/4.52). No numeric corrections are needed — this plan adds what's missing, it doesn't repair arithmetic.
- **C1:** `sim/strategies/llm_agent.py:298-303` sends react replies AFTER `LLMAgent._react_to_message` registered their commitments (`sim/agents/agent.py:699-712`); under the comm cell's per-tick budget the bus can refuse the reply, yet energy still ships against the unseen promise. Only fires where drops exist (comm cell only).
- **C2:** `sim/agents/agent.py:759-798` — `act()` serves commitments even when believed `soc_frac < policy.share_min_soc_frac` (lines 797-798 return `c_transfers` below threshold). ~15% loss measured in the comm-cell analysis. Fires in ANY cell with below-threshold commitment holders.
- **C3:** `sim/agents/failure_modes.py:96-107` `assign_defectors` returns a set nobody persists; committed defector summaries carry `defector_house_ids: []`. Additive provenance fix.
- **Sonnet ablation not wired:** `scripts/figures.py:45-50` `LIVE_CELLS` pins 4 cells; the committed `reference_runs/haves_havenots_solar__llm_sonnet/llm_agent/clean_sonnet__seed23/summary.json` (served 0.6685037752963732 / gini 0.2692744 / Jain 0.7944080) appears nowhere in figures/tables/results.
- **Stale docs:** `docs/phase3_results.md:3` (dated 2026-07-16), `:150-152` lists Stage 3 as "remaining optional" (done 2026-07-18); `README.md:41` claims the explanation table is "stubbed pending" judging (done 2026-07-17, table populated); `README.md:7` status stops at 3.3; `scripts/figures.py:576-581` docstring still describes the tables stub as pending.
- **Bus topology (verified):** the only `MessageBus.send()` call sites are `llm_agent.py:303/:326/:334`; `send()` (`sim/agents/protocol.py:119-176`) returns `None` with three logged drop paths (`budget_overflow` :123-139, `invalid_recipient` :140-156, `comm_drop` :157-175 which consumes one bus-RNG draw) and queue-append at :176. Cache key = sha256 of `{model, system, user, temperature, max_tokens, tools_schema}` (`sim/agents/cache.py:27-40`).

## Decisions (locked — do not re-litigate in execution)

1. **C1 = register-then-retract, NOT defer-registration.** Deferring registration changes the `open_kwh` line rendered into same-tick subsequent react prompts (`agent.py:631/:643`) even in zero-drop runs → cache-key drift → committed clean/defectors/noise cells stop replaying and would silently re-pay. Register exactly where today; retract when `send()` returns False. In zero-drop runs retraction never executes — a literal no-op. **Do not "simplify" this back.**
2. **C2 = gate the serving step only.** Expiry is hoisted so held promises still age out (counted); above-threshold behavior is arithmetically identical; the below-MEAN discretionary-filter bypass is preserved. The gate reads the NOISED `soc_frac` (Phase-3 "decide on what you see" design) — do not peek at engine truth.
3. **`n_commitments_made` keeps meaning "promise uttered"**; new counter `commitments_retracted` is the C1 observable. Identity: made = retracted + expired + fulfilled + open_at_end.
4. **Committed clean/defectors/noise cells stay as-is** (pre-C2-fix artifacts, annotated). C2 makes them non-re-derivable from cache with current code — that MUST be documented (Task 5) or a future reproduction attempt burns money and gets different numbers.
5. **Sonnet cell enters via a separate `ABLATION_CELLS` mapping**, not `LIVE_CELLS` — figures stay 4-cell; only the tables + results doc gain the ablation. The existing 4-cell pin `tests/test_figures.py:59-66` stays untouched.
6. **Prompt/cache stability is inviolable:** zero edits inside any prompt-building string in `agent.py` (`_PLAN_SYSTEM_PROMPT_*`, `_REACT_SYSTEM_PROMPT_*`, the `plan()` f-string, the `_react_to_message` f-string, `_POLICY_TOOL_SCHEMA`). One changed character re-prices every committed cell. The Task-7 review greps the diff for exactly this.

## Global constraints

- TDD, red first, every task; `pytest && ruff check sim tests scripts && mypy` green at every commit; conventional commits; CLAUDE.md progress row per task in the same commit; no Claude attribution; hooks re-stage.
- **Frozen (any red here = implementation drift, STOP and re-check; never "update the pin"):** all of `tests/test_golden_numbers.py`; `tests/test_figures.py` pins incl. `0.6725764138021589` and the 4-cell `LIVE_CELLS` pin; `tests/test_llm_agent_replay.py` byte-identity (both modes); `tests/test_agent.py` commitment tests at 914-982 and 1242-1282 (fixtures sit at SoC 0.8-0.9, above the 0.30 threshold — the design predicts they ALL stay green untouched); `tests/test_agent.py:1041-1078` react-prompt pin (incl. the literal "3 serviceable ticks"); all of `tests/test_protocol.py`.
- **The single deliberate re-pin:** the Task-1 characterization test, re-pinned ONLY in the Task-4 commit (old → new values in the comment).
- No new RNG consumers anywhere; `send()` drop logging, budget accounting, and RNG-draw sequence byte-identical.

## Traceability

| Brief item | Covered by |
|---|---|
| 6 — "make sure phase 3 ran with the most accuracy possible" | whole plan; number-tracing already verified in planning (see Context) |
| 1 — "review all the code" (negotiation path) | Tasks 1-4, 7 (focused diff review); full-tree review is Plan C |
| 8 — API key never exposed | Task 8 step 6 (pre-push key scan of the new artifacts) |

---

## Task 1 — Characterization pin BEFORE any fix

New `tests/test_commitment_fixes.py` with module docstring ("C1/C2 commitment-integrity fixes (2026-07-18): TDD tests…") plus this test, green immediately on current code (fill `<PIN>`s by running the mock once — reuse the `_canned_mock`/run pattern from `tests/test_llm_agent_failure_axes.py`):

```python
def test_mock_clean_cell_characterization_pin(tmp_path, monkeypatch) -> None:
    """Frozen mock clean-cell outcome. Committed BEFORE the C1 fix; the C1
    commit must keep it green (proof C1 is a no-op without bus drops). The C2
    commit deliberately re-pins it (below-threshold holders stop exporting) —
    update the values IN THAT COMMIT ONLY, with old->new in the comment."""
    summary = _run_mock("haves_havenots__llm.yaml", tmp_path, monkeypatch)
    assert summary["served_load_fraction"] == pytest.approx(<PIN>, abs=5e-7)
    assert summary["transfer_count"] == <PIN>
    assert summary["llm_call_counts_detailed"]["commitments_made"] == <PIN>
```

Also add the shared helpers the later tasks need (`_agent`, `_own`, `_request` builders — full drafts are in the design section of this plan's tasks below; lift them verbatim).

**Commit:** `test: characterize mock clean cell before commitment fixes`

## Task 2 — C3: record realized defector ids in `summary.json` (additive, lowest risk)

**Red tests** (append to `tests/test_run_provenance.py`):

```python
def test_summary_records_realized_defector_house_ids(tmp_path: Path) -> None:
    """C3: random-assignment defectors are invisible in every artifact —
    summary.json must record the realized draw (additive field)."""
    from sim.agents.failure_modes import assign_defectors

    sc = load_scenario(Path("configs/scenarios/haves_havenots__defectors.yaml"))
    logger = JsonlLogger(tmp_path / "d", scenario_id=sc.scenario_id)
    run(sc, None, logger, prepare=llm_fallback.prepare)
    logger.close()
    llm_strat.update_summary_with_counts(tmp_path / "d")
    summary = json.loads((tmp_path / "d" / "summary.json").read_text())
    got = summary["failure_modes_active"]["defector_house_ids"]
    hh = list(llm_strat._REGISTRY.agents)
    expect = sorted(assign_defectors(hh, sc.failure_modes, sc.seed))
    assert got == expect and len(got) > 0
    assert summary["failure_modes_active"]["defector_fraction"] == pytest.approx(0.2)


def test_summary_defector_house_ids_empty_in_clean_cell(tmp_path: Path) -> None:
    sc = load_scenario(_SCENARIO)  # the file's existing clean-cell constant
    logger = JsonlLogger(tmp_path / "c", scenario_id=sc.scenario_id)
    run(sc, None, logger, prepare=llm_fallback.prepare)
    logger.close()
    llm_strat.update_summary_with_counts(tmp_path / "c")
    summary = json.loads((tmp_path / "c" / "summary.json").read_text())
    assert summary["failure_modes_active"]["defector_house_ids"] == []
```

(Match the file's existing imports/helpers; adjust `run(...)` signature to the file's established call shape.)

**Implementation:**
1. `sim/strategies/llm_agent.py:47-63` `_AgentRegistry`: add defaulted field
   ```python
   # C3: the REALIZED defector assignment (random draw included), recorded so
   # summary.json can report who actually defected — config.json only carries
   # the configured tuple, which is () for random assignment.
   defector_house_ids: tuple[str, ...] = ()
   ```
2. In `prepare` after `defectors = assign_defectors(...)` (`:127`), pass `defector_house_ids=tuple(sorted(defectors))` to the `_AgentRegistry(...)` constructor call at `:206-213` (deterministic ordering; never serialize a raw set).
3. In `update_summary_with_counts` (`:417-447`): the function already computes `reg = registry or _REGISTRY` (~`:438`) for the cost estimate — hoist that above and add after the `llm_call_counts_detailed` assignment:
   ```python
   # C3: record the REALIZED defector assignment (additive; the engine-written
   # failure_modes_active block reports the configured tuple, which is []
   # whenever defector_assignment is "random").
   if reg is not None:
       summary.setdefault("failure_modes_active", {})["defector_house_ids"] = list(
           reg.defector_house_ids
       )
   ```
4. `sim/logging.py:88-99` caveat comment: add one line — "`defector_house_ids` present ⇒ realized (written post-run by llm_agent/llm_fallback); absent ⇒ configured-only (round_robin/lp_optimal never realize an assignment)."

Notes: no engine/physics/RNG/message change; the replay byte-identity test compares `state/events/messages.jsonl`, not `summary.json`. Committed pre-fix artifacts are NOT rewritten (Task 5 annotates).

**Commit:** `fix(provenance): record realized defector house ids in summary.json`

## Task 3 — C1: retract commitments whose reply the bus refused

**Red tests:**

(a) Bus return flag — append to `tests/test_protocol.py` (reuse the file's existing bus/message helpers):
```python
def test_send_reports_acceptance_and_refusal() -> None:
    bus = _grid_bus()
    bus.configure_failure_modes(per_tick_budget=2)
    t0 = datetime(2026, 1, 1)
    assert bus.send(_msg(t0, "r0c0", "r0c1")) is True
    assert bus.send(_msg(t0, "r0c0", "r1c0")) is True
    assert bus.send(_msg(t0, "r0c0", "r0c1")) is False   # budget_overflow
    assert bus.send(_msg(t0, "r0c0", "r4c4")) is False   # invalid_recipient
```

(b) Unit retract — in `tests/test_commitment_fixes.py`, using the Task-1 helpers:
```python
def test_retract_commitment_undoes_the_refused_reply(tmp_path) -> None:
    a = _agent(tmp_path)
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(t=t0, own_state=_own(8.0), inbox=[_request("r0c0", "c1", t0)], t_idx=0)
    (reply,) = a.react_to_pending(t=t0)
    assert len(a.commitments) == 1 and a.n_commitments_made == 1
    a.retract_commitment(reply)  # bus said False
    assert a.commitments == []
    assert a.n_commitments_retracted == 1
    assert a.n_commitments_made == 1  # made stays: the promise WAS uttered
    a.retract_commitment(reply)  # idempotent
    assert a.n_commitments_retracted == 1


def test_retract_is_a_noop_for_reject_replies(tmp_path) -> None:
    a = _agent(tmp_path, reply_text="REJECT\nrationale: no")
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(t=t0, own_state=_own(8.0), inbox=[_request("r0c0", "c2", t0)], t_idx=0)
    (reply,) = a.react_to_pending(t=t0)
    a.retract_commitment(reply)
    assert a.commitments == [] and a.n_commitments_retracted == 0
```

(c) Facade level — two tests: `test_budget_dropped_reply_leaves_no_commitment` (1×3 registry via a `_prepare_1x3_with_budget(tmp_path, per_tick_budget=1)` helper modeled on `tests/test_strategy_llm_agent.py::_prepare_with_failure`; seed two REQUESTs to the middle agent through the bus, tick once: assert `n_commitments_made == 2`, `n_commitments_retracted == 1`, `len(agent.commitments) == 1`, and exactly one `outcome=dropped` ACCEPT row in `bus.iter_log()`), and `test_no_drop_run_retracts_nothing` (same with `per_tick_budget=None`: retracted 0, commitments 2).

(d) Extend the Task-1 characterization pin with `assert summary["llm_call_counts_detailed"]["commitments_retracted"] == 0` (zero-drop cell). **The Task-1 pin values themselves must stay green UNTOUCHED through this commit — that is the no-drop no-op proof.**

**Implementation (minimal diff, in this order):**
1. `sim/agents/protocol.py:119` `def send(self, m: Message) -> None:` → `-> bool` with docstring: "Returns True iff the message entered the delivery queue… False iff the bus refused it (budget_overflow, invalid_recipient, comm_drop) — the recipient will never see it. Callers registering state against a message (commitment ledgers) must treat False as 'this message does not exist for the recipient' (C1 fix, 2026-07-18)." Each of the three drop paths' bare `return` (after the `self._log.append` at :139/:156/:175) → `return False`; the queue-append at :176 gains `return True`. **No other logic, no RNG change, no budget-accounting change.**
2. `sim/agents/agent.py` — registration block `:703-711`: capture the `Commitment` in a local `c`, append as today, and add `self._reply_commitments[m.correlation_id] = c` (comment: "C1: provisional until the facade confirms the bus accepted the reply"). New fields beside the other counters/private fields (~`:259-263`):
   ```python
   n_commitments_retracted: int = 0  # C1: reply refused by the bus -> promise undone
   _reply_commitments: dict[str, Commitment] = field(default_factory=dict, init=False, repr=False)
   ```
   `react_to_pending` (`:601`): first statement `self._reply_commitments.clear()` (before the `llm_disabled` early return). New method after it:
   ```python
   def retract_commitment(self, reply: Message) -> None:
       """Undo the provisional commitment behind ``reply`` (C1 fix).

       Called by the strategy facade when the bus REFUSED the ACCEPT/COUNTER
       (budget overflow / comm drop): the requester never saw the promise, so
       no energy may ship against it. No-op for replies with no commitment
       (REJECTs, zero-amount replies, unknown correlation ids).
       """
       c = self._reply_commitments.pop(reply.correlation_id, None)
       if c is None:
           return
       try:
           self.commitments.remove(c)
       except ValueError:  # already consumed — cannot happen mid-tick; be safe
           return
       self.n_commitments_retracted += 1
   ```
3. `sim/strategies/llm_agent.py:298-303` — the reply loop becomes:
   ```python
   # 4. React to pending messages. A reply the bus refuses (budget overflow /
   # comm drop) retracts its provisional commitment — the requester never saw
   # the promise, so the sender must not ship energy against it (C1 fix).
   # In zero-drop cells send() always returns True and this is a no-op.
   # (With messaging off no reply ever reaches the bus — and no REQUEST ever
   # arrived to react to — so retraction is unreachable there by construction.)
   for agent in reg.agents.values():
       replies = agent.react_to_pending(t=t)
       if reg.messaging_enabled:
           for m in replies:
               if not reg.bus.send(reg.defector_wrapper.maybe_corrupt(m)):
                   agent.retract_commitment(m)
   ```
   (`maybe_corrupt` preserves `correlation_id` — `failure_modes.py:169` uses `dataclasses.replace` — so keying retraction on the original `m` is safe.)
4. Counter plumbing: `"commitments_retracted": 0` in the zero-dict (`llm_agent.py:371-384`); aggregation + dict entry in `current_call_counts` (`:385-414`). Flows into `llm_call_counts_detailed` automatically.

**Gate:** full suite green including the untouched Task-1 pin and both replay byte-identity modes.

**Commit:** `fix(negotiation): retract commitments whose reply the bus refused (C1)`

## Task 4 — C2: hold (don't serve) commitments below own `share_min_soc_frac`

**Red tests** (in `tests/test_commitment_fixes.py`):

```python
def test_below_threshold_holds_commitment_then_serves_after_recovery(tmp_path) -> None:
    a = _agent(tmp_path)
    nb = build_grid_neighborhood(rows=1, cols=3, bus_max_kw=50.0)
    t0 = datetime(2026, 1, 1, 8, 0)
    a.observe(t=t0, own_state=_own(2.0), inbox=[], t_idx=0)  # 0.20 < 0.30 threshold
    a.commitments.append(Commitment(recipient="r0c0", kwh_remaining=0.4, expires_t_idx=5))
    transfers, outbox = a.act(t=t0, own_state=_own(2.0), neighborhood=nb, dt_hours=0.25)
    assert transfers == []                       # nothing ships below own threshold
    assert len(a.commitments) == 1               # the promise is HELD, not dropped
    assert a.commitments[0].kwh_remaining == pytest.approx(0.4)
    assert any(m.performative == "REQUEST" for m in outbox)  # still begging
    t1 = t0 + timedelta(minutes=15)
    a.observe(t=t1, own_state=_own(8.0), inbox=[], t_idx=1)  # recovered
    transfers, _ = a.act(t=t1, own_state=_own(8.0), neighborhood=nb, dt_hours=0.25)
    assert [tr.to_id for tr in transfers if tr.kw > 0] == ["r0c0"]
    assert a.commitments == []


def test_below_threshold_commitment_expires_while_held(tmp_path) -> None:
    a = _agent(tmp_path)
    nb = build_grid_neighborhood(rows=1, cols=3, bus_max_kw=50.0)
    a.commitments.append(Commitment(recipient="r0c0", kwh_remaining=0.4, expires_t_idx=1))
    for t_idx in (0, 1, 2):  # stays at 0.20 frac the whole time
        t = datetime(2026, 1, 1, 8, 0) + timedelta(minutes=15 * t_idx)
        a.observe(t=t, own_state=_own(2.0), inbox=[], t_idx=t_idx)
        transfers, _ = a.act(t=t, own_state=_own(2.0), neighborhood=nb, dt_hours=0.25)
        assert transfers == []
    assert a.commitments == []
    assert a.n_commitments_expired == 1  # counted even though never serviceable


def test_above_threshold_commitments_still_bypass_below_mean_filter(tmp_path) -> None:
    # Regression guard for the PRESERVED semantics: copy the body of
    # tests/test_agent.py::test_commitment_produces_transfer_bypassing_belief_filter
    # verbatim (read it first; fixture SoC 0.8 >= 0.30 threshold), adapted only to
    # this file's _agent/_own helpers — asserted here so the C2 commit carries
    # its own proof that above-threshold serving is untouched.
```

**Implementation** — replace `sim/agents/agent.py:759-798` (the commitment-serving region; current code begins `# Serve outstanding commitments FIRST (Phase 3): promised energy ships / regardless of the below-mean filter and threshold…`) with:

1. A hoisted expiry sweep that ALWAYS runs while islanded:
   ```python
   # Expire stale promises first — a counted, visible outcome whether or
   # not the agent is currently allowed to serve (C2: a held promise must
   # still be able to age out on its original TTL).
   live_commitments: list[Commitment] = []
   for c in self.commitments:
       if self.last_t_idx > c.expires_t_idx:
           self.n_commitments_expired += 1
       else:
           live_commitments.append(c)
   self.commitments = live_commitments
   ```
2. The serving loop gated `if self.commitments and soc_frac >= self.policy.share_min_soc_frac:` — body otherwise arithmetically identical to today (same `budget_kw`, same partial-serve math, same OFFER `payload={"kwh": …, "committed": True}` message construction verbatim; the keep-condition simplifies to `if c.kwh_remaining > 1e-9` because expired entries are already gone). Comment: "Serve outstanding commitments FIRST (Phase 3): promised energy bypasses the below-MEAN discretionary filter, but NOT the agent's own share_min_soc_frac safety threshold (C2 fix, 2026-07-18): an agent below its own floor holds the promise — it may serve after recovering, or expire (counted above)."
3. The existing below-threshold return at `:797-798` stays exactly as-is (it now returns empty `c_transfers`).
4. `Commitment` docstring (`agent.py:184-192`): keep "bypassing the below-mean belief filter"; remove any implication it bypasses the agent's own threshold.
5. **Re-pin the Task-1 characterization values in THIS commit** (old → new in the comment). This is the batch's only pin move.

Behavior notes (from the design; verify while implementing): above-threshold ticks byte-identical; `llm_fallback`/goldens untouched (empty ledger no-ops); the gate uses the noised view by design; expiry still only counted while islanded (pre-existing, out of scope — noted in Task 5).

**Gate:** full suite; every frozen test untouched; ruff + mypy.

**Commit:** `fix(negotiation): hold commitments below own share_min_soc_frac instead of exporting (C2)`

## Task 5 — Annotate pre-fix artifacts + metric-semantics changes ($0 docs)

1. `docs/phase3_results.md` limitations section: add — (a) clean/defectors/noise live cells were produced pre-C1/C2 (name the pre-fix commit hash); after C2 they are frozen measurements of the pre-fix protocol and NOT re-derivable from cache with current code (clean seed 23's 914 expiries prove below-threshold committers exist there); (b) `commitments_expired` now also counts promises that die while held below threshold — pre/post-fix expiry percentages are not comparable; (c) commitment expiry is only counted while islanded (pre-existing scope note).
2. Same two notes as a short addendum in `docs/superpowers/plans/2026-07-12-phase3.2-live-runs.md` (append; never rewrite the pre-fix record).
3. `docs/phase3_tables.md` is generated — the caveat text goes into `render_tables`' prose lines in Task 6 instead of hand-editing the output.

**Commit:** `docs(phase3): annotate pre-fix live cells + expiry-metric semantics change`

## Task 6 — Wire the Sonnet ablation + purge stale doc claims ($0)

**Red tests** (append to `tests/test_figures.py`):
```python
def test_ablation_cell_reads_committed_sonnet_summary() -> None:
    s = read_live_summary("haves_havenots_solar__llm_sonnet", 23)
    assert s["served_load_fraction"] == 0.6685037752963732
    assert s["scenario_id"] == "haves_havenots_solar__llm_sonnet"


def test_tables_include_capability_ablation_row(tmp_path) -> None:
    out = render_tables(out_path=tmp_path / "tables.md")
    txt = out.read_text()
    assert "clean (Sonnet)" in txt          # negotiation-table row for the ablation
    assert "capability" in txt.lower()      # the ablation is labeled as such
```

**Implementation:**
1. `scripts/figures.py`: add beside `LIVE_CELLS` (`:45-50`) —
   ```python
   # Stage-3 capability ablation (Sonnet agents, clean cell, seed 23). Kept out
   # of LIVE_CELLS: the four-cell figures tell the failure-axis story; the
   # ablation appears in the tables + results doc as a capability data point.
   ABLATION_CELLS: dict[str, dict[int, str]] = {
       "haves_havenots_solar__llm_sonnet": {23: "clean_sonnet__seed23"},
   }
   ```
   `CELL_LABEL` gains `"haves_havenots_solar__llm_sonnet": "clean (Sonnet)"`. `CELL_ORDER`, `_CELL_MARKER`, `CLEAN` unchanged.
2. `read_live_summary` resolves through `{**LIVE_CELLS, **ABLATION_CELLS}` (keep the KeyError contract for unknown cells/seeds).
3. `render_tables`: `_live_runs()` (or its caller) also yields the ablation rows for the negotiation table, and the prose gains one sentence naming the capability ablation + the Task-5 expiry-semantics caveat. Fix the stale docstring at `:576-581` ("stays a pending Stage 4 stub" → describes the populated behavior; the empty-artifact stub branch at `:623-636` remains as the no-artifact fallback).
4. `docs/phase3_results.md`: new "§ Capability ablation (Stage 3)" block — Sonnet clean@23 served 0.6685 vs Haiku 0.6726 (statistical tie, −0.4 pts), both clear control (+4.2 / +4.6) and round_robin (+2.4 / +2.8), gap-closed 29.4% vs 32.3%; finding: model capability does not move clean-cell coordination — the advantage lives in scenario difficulty (corroborates P2.8 ceiling + advisor's scenario-design-over-model-comparison); caveats: n=1 seed, non-deterministic (temperature omitted for Sonnet — cache-replayable, not re-derivable), higher parse-noise absorbed by the negotiation machinery. Update `:3` (date/status line) and `:150-152` (§7: Stage 3 moves from "remaining" to done; remaining = VT/AZ cells + `all`@7, both deferred).
5. `README.md:7` and `:41`: Stage 4 done 2026-07-17 (judge 3.03/4.05/4.46 clean, 3.00/3.97/4.52 defectors; table populated), Stage 3 done 2026-07-18 (Sonnet ties Haiku). Remove "stubbed pending" claims.
6. Regenerate: `python -m scripts.figures --tables` (tables now include the ablation row); `--check` still green; figures PNGs untouched by this task (`git status` shows only `phase3_tables.md`).

**Commit:** `feat(phase3): wire Sonnet capability ablation into tables/results; purge stale stage-3/4 stubs`

## Task 7 — Review gate + control fix-invariance (NO commit; gates the spend)

1. Focused adversarial review of `git diff <pre-batch-sha>..HEAD -- sim/` (subagent): confirm zero prompt-template edits (grep the diff for `_PLAN_SYSTEM_PROMPT`, `_REACT_SYSTEM_PROMPT`, `rationale`, f-string prompt regions, `_POLICY_TOOL_SCHEMA`), zero new RNG consumers, `send()` log/budget/RNG order unchanged, retract/hold logic matches this plan's Decisions. Any deviation: fix before proceeding.
2. `python -m scripts.figures --check` green (committed artifacts untouched so far).
3. Fix-invariance on the $0 control: `python -m scripts.run --scenario configs/scenarios/haves_havenots_solar__comm.yaml --strategy llm_fallback --seed 23` (fresh out-dir) → served must equal the committed control **0.5027309** (0.502743…, compare at 6 dp). The control has no LLM → no commitments → all three fixes must leave it bit-unmoved. If it moves, a fix leaked into a no-commitment path — STOP, do not spend.
4. Credential check: `ANTHROPIC_API_KEY` present via Keychain export; never echo the key itself.

## Task 8 — Comm-cell live re-run (MONEY — cap $8, authorization recorded in the header)

1. **Run:** `python -m scripts.run --scenario configs/scenarios/haves_havenots_solar__comm.yaml --reference-cell comm --seed 23` → writes into the stable dir `reference_runs/haves_havenots_solar__comm/llm_agent/comm__seed23/` (pre-fix run: served 0.45647965855980976, $4.03). The existing `llm_cache/` replays early ticks at $0 until the first trajectory divergence (first retraction or below-threshold hold), then pays fresh Haiku calls. Interruption/429: rerun the identical command (cached calls replay free). Record wall time + spend from the summary.
2. **Verification block:** the standard Stage-2 checks from `docs/superpowers/plans/2026-07-12-phase3.2-live-runs.md:49-67`, plus: `llm_call_counts_detailed["commitments_retracted"] > 0` (C1 active — this cell HAS drops); `failure_modes_active["defector_house_ids"] == []` (C3 honest in a no-defector cell); sanity `no_coord(0.3340) <= served <= LP(0.7684)`; cross-check retracted ≈ count of `outcome=dropped` ACCEPT/COUNTER rows with `payload.kwh > 0` in `messages.jsonl`.
3. **Pre-registered expectation (honest-reporting rule):** C1+C2 remove misallocation, so served should move UP from 0.4565 toward (possibly past) the control 0.5027 — but the dominant damage channel (reply send-order displacing OFFER/REQUEST bandwidth + INFORM starvation) is untouched by these fixes, so a residual live-vs-control loss is the expected outcome. **Live ≥ control would be a surprise to double-check, not quietly celebrate.** Report whatever comes out, including a worse number; the write-up keeps the "negotiation costs bandwidth" scope framing and n=1 caveat, now phrased "after fixing two commitment-integrity bugs (C1, C2), the delta is X".
4. **Downstream regeneration:** `python -m scripts.figures --all` (headline/fairness/scatter/failure-axis + tables — comm bars and the comm table rows move); hand-update `docs/phase3_results.md` comm numbers + narrative (§2 table comm row, comm bullets, the 4,260/17,647 instrumentation sentence — re-derive from the new summary); append the post-fix result to the 3.2 plan's comm section (do not rewrite the pre-fix record); `figures --check` green afterward.
5. **CLAUDE.md:** progress-log row (same commit): old→new served/gini/Jain, retracted/expired counts, spend, mechanism reading. Update the comm numbers in the Phase-3 status surfaces (or their post-Plan-D condensed location).
6. **Security (public repo):** before push — staged-diff key grep → 0; new artifacts under `reference_runs/.../comm__seed23/` contain no credentials (cache stores prompt/response/model/tokens only); full-tree `git grep -IlE 'sk-ant-(api|oat)[0-9a-zA-Z_-]{15,}'` → 0.
7. Push; `gh run list --limit 1`.

**Commit:** `feat(phase3.3): comm cell re-run post C1/C2/C3 (live Haiku, seed 23)`

---

## Edge flags for the executor (from the design review — read before starting)

- The "simplest" C1 (defer registration) is WRONG here — see Decisions 1. Do not refactor toward it.
- If any `tests/test_agent.py` commitment test goes red at any point, that is implementation drift from this design — stop and re-check; the design predicts zero breakage there.
- A reply accepted on the final tick is flushed as `pending_at_end` with its commitment intact — harmless (no further act() ticks); documented in the `send()` docstring, not special-cased.
- `round_robin`/`lp_optimal` summaries won't carry `defector_house_ids` (they bypass `prepare`) — that absence is itself the "configured-only" marker; don't force it in.
- `n_commitments_made` is never decremented; the identity made = retracted + expired + fulfilled + open_at_end holds in analysis, not as a test assertion.
