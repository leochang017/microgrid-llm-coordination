# Phase 3 — Results (empirical story, real numbers)

**Status:** Phase 3.3 analysis draft, 2026-07-16. Every number below traces to a
committed `llm_agent` summary (live) or a deterministically-regenerated $0
baseline; regenerate the figures/tables with `python -m scripts.figures --all`.
Model: Claude Haiku (`claude-haiku-4-5`). Live cells at tag `phase3.2-live-complete`.

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
| comm | 23 | msg budget 2/tick | 0.5027 | 0.4565 | **−4.6** | negotiation bandwidth cost |

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
- **Comm (−4.6 vs control):** the one loss. A per-tick message budget starves the
  OFFER/REQUEST traffic that moves energy because ACCEPT/COUNTER/REJECT replies
  emit first (hardcoded send order); the control, sending no negotiation replies,
  gets 60% more energy-moving traffic through. **Scope: "a negotiation protocol
  costs bandwidth that under scarcity can exceed the coordination it buys" — NOT
  "LLM coordination is fragile."** Send order is plumbing the LLM can't control
  (follow-up hardening tracked in CLAUDE.md).

## 3. Fairness and the efficiency–equity (non-)tradeoff

`docs/figures/phase3_fairness.png`, `…_efficiency_equity.png`. Gini is never
shown alone (Gini + Jain + Rawlsian floor + critical-load served).

- **No efficiency–equity tradeoff appears on the clean/defectors/noise cells:**
  Gini and Jain improve *alongside* served-load. The advisor expected this
  tradeoff to be "more interesting than the absolute numbers"; the finding is
  that it does not appear where coordination succeeds. On defectors, live is
  slightly *fairer* than control (Gini 0.200 vs 0.204, Jain 0.866 vs 0.861) while
  also serving more.
- **Comm is the exception in both dimensions:** live Gini 0.480 (control 0.441)
  and Jain 0.566 (control 0.608) — under message scarcity the failed negotiation
  hurts equity too, consistent with the served-load loss.
- **Caveat — the Rawlsian floor is degenerate:** `min_house_served_fraction` is
  near-identical across strategies (~0.035–0.041), so it contributes nothing to
  the comparison and is reported but not leaned on.

## 4. Negotiation instrumentation

`docs/phase3_tables.md`. The "what actually happened in negotiation" table, from
committed summaries. Highlights: clean-cell commitment expiry ranges 5.6–27.3%
across seeds — honest haves over-promising against depleted batteries, **not**
defectors reneging (the engine ships commitments before the discretionary
filter). The comm cell delivered only 4,260 of 17,647 messages (11,887
budget-dropped); every other run had zero comm/budget drops.

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

## 7. What's next

Advisor walkthrough off this outline; venue decision (CHI / ICLR / WWW main or
workshop) with the advisor at Phase 3.3 exit. Stage 4 explanation judging is
**done** (§5). Remaining optional add-ons: the Sonnet capability ablation
(Stage 3) and, if the advisor wants cross-climate robustness, the VT/AZ cells.
