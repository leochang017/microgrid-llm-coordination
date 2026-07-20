# Phase 3 — Results (empirical story, real numbers)

**Status:** Phase 3.3 analysis draft, 2026-07-16; updated 2026-07-19 with the
Stage-3 Sonnet capability ablation (§5.5), the Task-5 commitment-negotiation
fixes' expiry-semantics caveat (§6), and the **comm@23 live re-run** after the
C1/C2/C3 fixes (§2: served 0.4565 → 0.4941, control gap −4.6 → −0.86 pts). Every number below traces to a committed
`llm_agent` summary (live) or a deterministically-regenerated $0 baseline;
regenerate the figures/tables with `python -m scripts.figures --all`. Model:
Claude Haiku (`claude-haiku-4-5`) unless noted; the ablation uses
`claude-sonnet-5`. Live cells at tag `phase3.2-live-complete`.

All performance is framed as **gap-closed between round_robin and the LP
ceiling**, with the **zero-LLM control (`llm_fallback`) as the mandatory bar** —
the Phase 2 lesson (the tuned executor, not the LLM, carries clean-cell
throughput) is reported as a finding, not buried. The LLM's case is made in the
**failure cells** and on **negotiation/fairness behavior**, not clean-cell
throughput alone.

Figures: `docs/figures/phase3_headline.png`, `…_fairness.png`,
`…_efficiency_equity.png`, `…_failure_axis.png`. Tables: `docs/phase3_tables.md`.

---

## 1. Headline: live coordination beats the zero-LLM control, replicated across seeds

Clean cell (`haves_havenots_solar__llm`), three household draws (seeds 23/1/7):

| seed | no-coord | control | round_robin | live-Haiku | LP ceiling | live vs control | gap-closed (ctrl→LP) |
|---|---|---|---|---|---|---|---|
| 23 | 0.3336 | 0.6269 | 0.6444 | **0.6726** | 0.7684 | **+4.6** | 32.3% |
| 1  | 0.4613 | 0.7607 | 0.8023 | **0.8248** | 0.9914 | **+6.4** | 27.8% |
| 7  | 0.4279 | 0.7337 | 0.7885 | **0.7964** | 0.9673 | **+6.3** | 26.8% |

- **vs control: +5.8 ± 1.0 pts (3/3 seeds), closing 29.0% ± 2.9 of the
  control→LP gap.** This is the paper's claimable headline.
- **vs round_robin: +2.0 ± 1.1 pts, but decaying 2.8 → 2.3 → 0.8** across seeds,
  and the rr→LP gap-closed spread is 13.0% ± 9.2 (5× the control spread). The
  control margin reproduces where round_robin itself swings 16 points — so the
  paper claims the **control** comparison; a round_robin claim would be
  seed-dependent and would not survive a reviewer adding seeds.
- **This is the first replicated live evidence the LLM layer adds value.** In
  Phase 2.8 live Haiku *lost* to round_robin (0.513 vs 0.525) and the Phase 2.9
  control *tied* it — a null saying the executor did the work. The Phase 3
  information-flow rework (INFORM-only beliefs, binding negotiation) changed the
  answer.

## 2. Failure axes: where the LLM earns its keep (and where it doesn't)

Each failure cell is compared to its **own same-seed control**, never across
cells (`docs/figures/phase3_failure_axis.png`). n=1 per cell — single-seed
deltas, reported honestly as such.

| axis | seed | realized dose | control | live | live vs control | note |
|---|---|---|---|---|---|---|
| defectors | 7 | 33.6% generation withheld | 0.7337 | 0.7564 | **+2.3** | retains 89.1% of coordination value |
| noise | 23 | SoC 10% + load 15% | 0.6399 | 0.6486 | **+0.9** | robustness holds, margin compressed |
| comm | 23 | msg budget 2/tick | 0.5027 | 0.4941 | **−0.86** | residual bandwidth cost (post C1/C2/C3) |

- **Defectors (+2.3 over control):** beating the control here is strong because
  the control is *structurally immune* to prompt-realized defection (no LLM reads
  the selfish prompt), yet live cleared it while carrying the full handicap. The
  honest headline is **"retains 89.1% of coordination value under 33.6%
  defection"** (naive proportional predicted 66.4%) — the LLM re-routes around
  defectors through the loyal haves. NOT a robustness-to-defection *security*
  claim (advisor warning).
- **Noise (+0.9 over control):** ordering holds (live > rr > control) but the
  edge compresses from clean's +4.6 to +0.9 — dual-channel belief noise costs the
  reasoning arm several times more than the fixed heuristic that barely reads the
  perturbed channel. The pre-registered "tolerates noise but pays for it"
  outcome. (The mock floor shows noise *mildly helps* the fixed control, +1.3;
  live must beat that accidental gain, and does.)
- **Comm (−0.86 vs control, re-run post C1/C2/C3):** originally measured at −4.6,
  but two commitment-integrity bugs accounted for most of that loss. **C1**
  (`d3b5ff14`): the sender shipped energy against ACCEPT/COUNTER replies the
  per-tick message budget had *refused* — the requester never saw the promise
  (this run retracted 202 such commitments, matching exactly the 202
  budget/comm-dropped ACCEPT/COUNTER replies in `messages.jsonl`). **C2**
  (`0fdc9424`): agents exported committed energy while below their own
  `share_min_soc_frac` safety floor. Fixing both lifts served 0.4565 → **0.4941**
  and shrinks the control gap from −4.6 to **−0.86 pts** (gap-closed −17.4% →
  −3.2%); fairness improves too (Gini 0.480 → 0.453, Jain 0.566 → 0.596). A small
  residual loss remains: the per-tick budget still starves OFFER/REQUEST traffic
  because replies emit first (hardcoded send order the LLM can't control —
  11,194 of 16,954 messages budget-dropped this run). **Scope: "a negotiation
  protocol costs *some* bandwidth under scarcity" — much smaller than first
  measured, and most of the original apparent loss was measurement bugs, not
  fundamental LLM fragility.** n=1; send-order hardening still tracked in
  CLAUDE.md.

## 3. Fairness and the efficiency–equity (non-)tradeoff

`docs/figures/phase3_fairness.png`, `…_efficiency_equity.png`. Gini is never
shown alone (Gini + Jain + Rawlsian floor + critical-load served).

- **No efficiency–equity tradeoff appears on the clean/defectors/noise cells:**
  Gini and Jain improve *alongside* served-load. The advisor expected this
  tradeoff to be "more interesting than the absolute numbers"; the finding is
  that it does not appear where coordination succeeds. On defectors, live is
  slightly *fairer* than control (Gini 0.200 vs 0.204, Jain 0.866 vs 0.861) while
  also serving more.
- **Comm is the exception in both dimensions:** live Gini 0.453 (control 0.441)
  and Jain 0.596 (control 0.608) — under message scarcity the residual
  negotiation loss still slightly hurts equity, consistent with the served-load
  loss (both improved from the pre-fix 0.480 / 0.566 after C1/C2).
- **Caveat — the Rawlsian floor is degenerate:** `min_house_served_fraction` is
  near-identical across strategies (~0.035–0.041), so it contributes nothing to
  the comparison and is reported but not leaned on.

## 4. Negotiation instrumentation

`docs/phase3_tables.md`. The "what actually happened in negotiation" table, from
committed summaries. Highlights: clean-cell commitment expiry ranges 5.6–27.3%
across seeds — honest haves over-promising against depleted batteries, **not**
defectors reneging (the engine ships commitments before the discretionary
filter). The comm cell (re-run post C1/C2/C3) delivered only 4,224 of 16,954
messages (11,194 budget-dropped, 1,498 comm-dropped); every other run had zero
comm/budget drops.

## 5. Explanation quality (Stage 4, live Sonnet judge)

Live judging by **`claude-sonnet-5`** (judge ≠ author family, per the advisor;
authors are Haiku), scoring 100 LLM-authored react rationales per cell 1–5 on
three axes. Table + consistency numbers in `docs/phase3_tables.md`.

| cell | seed | n | state_accuracy | actionability | consistency |
|---|---|---|---|---|---|
| clean | 23 | 100 | 3.03 | 4.05 | 4.46 |
| defectors | 7 | 100 | 3.00 | 3.97 | 4.52 |

- **The rationales are actionable and consistent with the action taken
  (~4.0 / ~4.5), but `state_accuracy` is the weakest axis (~3.0):** the LLM's
  self-reported headroom/SoC figures in a rationale sometimes drift from the
  logged decision-time state. A 10-rationale hand audit confirmed the judge
  discriminates sensibly — it docks a rationale claiming 0.78 kWh headroom when
  the sender's logged SoC was 1.13 kWh, and rewards rationales whose numbers
  check out. Clean and defector cells score nearly identically, so selfish
  prompting does not degrade explanation quality.
- **Judge consistency (advisor 2026-07-15):** the clean cell was re-judged under
  three paraphrases of the one rubric (default / terse / roleplay), axis names +
  1–5 scale fixed. **Aggregate means are stable to rephrasing** (state 2.99–3.16,
  actionability 3.73–4.05, consistency 4.03–4.46 — drift within a few tenths),
  but **per-message exact 3-way agreement is only 32–38%** (mean absolute
  deviation 0.30–0.36 on the 1–5 scale). So the instrument is trustworthy in
  aggregate but noisy per message — the paper leans on **means, not per-message
  scores**. The `--rubric-variant` instrument (mock-tested pre-live) produced
  this directly; `explanations_eval*.json` artifacts are committed and
  `python -m scripts.figures --tables` regenerates the table.
- **Explanation quality stays SECONDARY to coordination performance** (advisor).

## 5.5 Capability ablation (Stage 3): model capability doesn't move clean-cell coordination

Same clean scenario (`haves_havenots_solar`, seed 23), agents swapped from
Claude Haiku (`claude-haiku-4-5`) to Claude Sonnet (`claude-sonnet-5`) — nothing
else changed.

| model | served | vs control | vs round_robin | gap-closed (ctrl→LP) |
|---|---|---|---|---|
| Haiku (clean@23) | 0.6726 | +4.6 | +2.8 | 32.3% |
| Sonnet (clean_sonnet@23) | 0.6685 | +4.2 | +2.4 | 29.4% |

- **Sonnet ties Haiku (−0.4 pts, statistically indistinguishable at n=1) —
  a stronger model buys nothing here.** Both clear the control (0.6269) and
  round_robin (0.6444) by comparable margins; Sonnet closes slightly less of
  the control→LP gap (29.4% vs 32.3%), not more.
- **Finding: the LLM's coordination advantage tracks scenario difficulty, not
  raw model capability.** This corroborates the Phase 2.8 architecture-ceiling
  result (adding peer state + LLM-controlled share fraction moved no macro
  metric there either) and gives the advisor's 2026-07-15 "scenario design
  over model comparison" guidance a live data point.
- **Caveats:** n=1 seed, not statistically powered beyond a single comparison;
  **not byte-deterministic** — `temperature` is omitted for Sonnet (it rejects
  the parameter), so the run is cache-replayable but not re-derivable from
  scratch; higher parse-noise than Haiku (plan-parse 5.8% vs 2.7%, react-unparsed
  11.1% vs 0%, only 1 true round-robin fallback) that the negotiation machinery
  absorbed without moving any macro metric.

## 6. Limitations (honest, for the paper)

- **n=1 on every failure cell** — single-seed deltas; the clean headline is the
  only multi-seed claim. Failure cells state their realized dose.
- **Single dataset family** (`haves_havenots_solar`) unless VT/AZ winter/heatwave
  scenarios land (deferred; free NREL data, but live cells would cost money).
- **Degenerate Rawlsian floor** (§3).
- **LLM-judge caveat** (§5): a single LLM judge, trustworthy in aggregate but
  noisy per message (32–38% exact 3-way agreement under rubric paraphrase);
  explanation quality is reported as secondary, mean-level only.
- **No real-deployment claim** — simulation only (advisor warning, verbatim).
- **The comm result measures negotiation plumbing, not reasoning** (§2).
- **The clean/defectors/noise live cells are pre-fix artifacts.** They were
  produced before the C1/C2 commitment-negotiation fixes (`d3b5ff14`,
  `0fdc9424`; pre-batch baseline `cf18b13d`). After C2, they are frozen
  measurements of the pre-fix protocol and are **not re-derivable from cache
  with current code** — a naive replay would silently re-pay every call
  instead of hitting the prompt cache. This is known to matter, not
  hypothetical: the clean seed-23 solar live run logged 914 commitment
  expiries out of 3,343 made, which proves below-threshold committers exist
  in that run, exactly the population C2 changes the handling of.
- **`commitments_expired` is not comparable pre- vs post-C2.** C2 made the
  counter also count promises that die while held below the committer's own
  `share_min_soc_frac` threshold (previously such promises were exported
  anyway, not tracked as expiring-while-held). So a post-fix expiry
  percentage is measuring a different thing than the pre-fix percentages
  quoted above (§2, §4) — do not diff them as if they were the same metric
  before and after.
- **Commitment expiry is only counted while islanded** — a pre-existing scope
  note carried over unchanged by C1/C2.
- **Commitment counters are bookkept at emission, not settlement.** An agent
  decrements a commitment by the kWh it *asks* the engine to move; the engine
  then settles that request against sender caps, receiver caps, and the bus
  limit, and routinely scales it down (committed clean@23: 906
  `sender_dod_floor` clip events against 1,632 executed transfers). No
  settlement result is fed back to the agent — `MemoryKind`'s
  `transfer_outcome` slot is declared but never written — so a commitment the
  instrumentation counts as fulfilled may have been only partly delivered.
  **Every headline number is unaffected:** served-load, Gini, Jain, and the
  gap-closed figures are all computed from settled physics, which is
  authoritative. What this does qualify is the promise-side reading of §4 —
  including the noise-cell aside that agents "committed less and fulfilled more
  reliably", which rests on emission-side counters and is therefore a statement
  about promising behavior, not about delivered energy. Feeding settlement back
  to the agents is a Phase-4 candidate (it changes prompts and cache keys, so it
  would re-pay every committed live cell).
- **The committed `defectors@7` artifact predates the C3 provenance fix.** Its
  `summary.json`'s `failure_modes_active.defector_house_ids` reads `[]` even
  though 6 defector houses (33.6% dose) actually were realized — C3 (wiring
  the realized draw into `summary.json`) landed after this cell was produced,
  and per the no-rewrite rule the committed artifact is not backfilled. The
  33.6% figure and the realized defector ids are not sourced from that stale
  field; they're independently pinned by `scripts/dose_check.py` and
  `tests/test_run_provenance.py`. No number here is wrong — this is a
  provenance caveat on one JSON field of one pre-fix artifact, not a
  correction.

## 7. What's next

Advisor walkthrough off this outline; venue decision (CHI / ICLR / WWW main or
workshop) with the advisor at Phase 3.3 exit. Stage 4 explanation judging is
**done** (§5) and Stage 3, the Sonnet capability ablation, is **done** (§5.5) —
all Phase 3.2 playbook stages (1-5, including optional Stage 3) are now
complete. Remaining deferred, not scheduled: cross-climate VT/AZ cells and the
`all`@7 failure cell (its comm component is confounded with the shipped
`comm`@23 cell — see CLAUDE.md Phase 3.2 status).
