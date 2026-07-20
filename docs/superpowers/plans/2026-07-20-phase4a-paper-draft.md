# Phase 4a — Paper draft v1 (Markdown, venue-agnostic)

**Spec:** `docs/superpowers/specs/2026-07-20-phase4-paper-demo-design.md` · **Gate:** `phase3.3-complete` (met; all Phase 3.2 playbook stages done) · **Cost:** $0 (no API calls; web search/fetch only, for literature verification).

**Working rules:** smallest-possible diffs; one commit per task (Conventional Commits, NO Claude attribution anywhere); append a Progress-log row to `CLAUDE.md` in the SAME commit as the task's artifacts; flip this plan's task checkbox in the same commit. All tasks are docs-only — no TDD red step (fix-batch-E precedent) — but every commit runs the frozen-pin verify (`python -m scripts.figures --check` green) plus `ruff check sim tests scripts`, and the staged-diff security grep (`git diff --cached | grep -cE 'sk-ant-(api|oat)[0-9a-zA-Z_-]{15,}'` → 0) before any push. Full four-part gate (ruff / `mypy` → 37 files / `pytest` → 407 ✓ / `figures --check`) at Task 0 and Task 11. Interpreter: the repo `.venv` (Python 3.12.12, rebuilt + trusted 2026-07-20).

**Number rule (absolute):** every number in `docs/paper/paper.md` is COPIED from `docs/phase3_results.md`, `docs/phase3_tables.md`, or a committed `reference_runs/**/summary.json` — never computed fresh, never recalled from memory, never invented. If a needed number is not in those sources, the sentence needing it is rewritten to not need it.

**Citation rule (absolute):** no entry enters the References section without its arXiv ID, DOI, or venue+year verified by a web search/fetch IN THIS SESSION. If verification fails, the citation is dropped, not guessed.

**Advisor constraints (verbatim, binding on all prose):**
1. Do NOT claim the system is ready for real deployment. It isn't, nobody's is.
2. Careful with equity framing; Sovacool's energy-justice work is read (Task 2) BEFORE any fairness prose is written (Task 7).
3. Defectors = robustness-to-misreporting. NO threat model, NO "Byzantine", NO "adversarial security" framing, no security-contribution claim.
4. Gini never appears without Jain + min-house + served-critical alongside.
5. Park et al. (arXiv:2304.03442) cited prominently for the memory/reflection lineage.
6. All performance framed as gap-closed between round_robin and the LP ceiling; the zero-LLM control is the mandatory bar; the claimable headline is vs CONTROL, not round_robin.
7. The honest-negative clean-cell finding ("the tuned executor, not the LLM, carries clean-cell performance") is reported as a finding with its own subsection, plus the Sonnet-ablation tie.
8. The efficiency-vs-equity discussion gets its own figure (`phase3_efficiency_equity.png`) + dedicated paragraphs.

**Out of scope (explicitly):** LaTeX/venue conversion (blocked on the advisor's venue decision), submission mechanics, camera-ready, VT/AZ cross-climate cells (dropped from Phase 4; single-dataset caveat stays in Limitations), any new experiment or live API spend, prompt-engineering iterations, closing the settlement-feedback loop (changes cache keys — separate decision), the web demo (separate plan), sending email (Leo sends).

## Task status
- [ ] Task 0 — Baseline gate
- [ ] Task 1 — Scaffold `docs/paper/`
- [ ] Task 2 — Energy-justice reading pass (Sovacool)
- [ ] Task 3 — Related-work literature pass
- [ ] Task 4 — Problem setup, simulator, metrics, experimental setup
- [ ] Task 5 — Agent architecture & information flow
- [ ] Task 6 — Results I: headline + honest negative + ablation
- [ ] Task 7 — Results II: failure axes, fairness, negotiation, explanations
- [ ] Task 8 — Discussion, Limitations, Conclusion
- [ ] Task 9 — Abstract, Introduction, Contributions
- [ ] Task 10 — Number-accuracy audit + claims traceability + prose pass
- [ ] Task 11 — Wrap: status sync + advisor/venue email draft

---

## Task 0 — Baseline gate (no commit)

1. In the repo `.venv`: `ruff check sim tests scripts` → "All checks passed!"; `mypy` → "Success: no issues found in 37 source files"; `pytest` → 407 passed; `python -m scripts.figures --check` → green (every committed cell matches its golden pin).
2. `git status` clean; `git log --oneline -3` to record the base commit in the session notes.
3. Confirm `docs/superpowers/specs/2026-07-20-phase4-paper-demo-design.md` exists (it is this plan's Spec header). If it does not, STOP and tell Leo — the spec must land before drafting starts (standing rule: spec before plan execution).
4. **Verify:** all four gates green. This baseline is what Task 11 must reproduce.

## Task 1 — Scaffold `docs/paper/paper.md` skeleton

1. Create `docs/paper/paper.md` with:
   - Title (working, Leo may rename): `Natural-Language Negotiation for Fair and Robust Energy Sharing During Outages: A Study of LLM Agent Coordination`.
   - A header metadata block: **Draft v1 (Markdown, venue-agnostic)** · date · "Every number traces to a committed artifact; see `docs/phase3_results.md` and regenerate figures/tables with `python -m scripts.figures --all`. Agent model: Claude Haiku (`claude-haiku-4-5`); ablation and judge: `claude-sonnet-5`. Live cells at tag `phase3.2-live-complete`."
   - Section headers exactly: Abstract; 1 Introduction; 2 Related Work; 3 Problem Setup and Simulator (3.1 Microgrid outage model, 3.2 Baselines and the LP ceiling, 3.3 Metrics); 4 LLM Agent Architecture (4.1 Memory, reflection, and the policy executor, 4.2 Information flow: INFORM-only beliefs and binding negotiation); 5 Experimental Setup; 6 Results (6.1 Headline: live coordination beats the zero-LLM control; 6.2 The honest negative: what the LLM does not buy; 6.3 Robustness under degraded information; 6.4 Fairness and the efficiency–equity (non-)tradeoff; 6.5 What actually happened in negotiation; 6.6 Explanation quality); 7 Discussion; 8 Limitations; 9 Conclusion; References.
   - Under each empty section, one HTML comment naming the task that fills it (e.g. `<!-- filled by Task 6 -->`) — these comments are deleted by the filling task.
   - Embed the four figures now, in their target sections, with relative paths and full captions: `../figures/phase3_headline.png` (§6.1), `../figures/phase3_failure_axis.png` (§6.3), `../figures/phase3_fairness.png` and `../figures/phase3_efficiency_equity.png` (§6.4). Captions state cell/seed coverage (clean = 3 seeds mean±spread; failure cells n=1, annotated).
2. Create `docs/paper/claims_audit.md` with the empty table header: `| # | Claim (verbatim) | Paper § | phase3_results.md § | Artifact |` and a preamble saying it is populated by Task 9/10.
3. **Verify:** `python -m scripts.figures --check` green; `ruff check sim tests scripts` clean; the four embedded image paths resolve (`ls docs/figures/phase3_*.png` → 4 files); markdown renders (spot-check with `grep -c '^## ' docs/paper/paper.md` → matches the section count).
4. **Commit:** `docs(paper): scaffold paper draft v1 skeleton under docs/paper/` (+ Progress-log row + checkbox flip).

## Task 2 — Energy-justice reading pass (REQUIRED before Task 7)

1. Web-search and read (abstract + framework at minimum; find an accessible copy or authoritative summaries from ≥2 independent sources if paywalled): **Sovacool & Dworkin 2015, "Energy justice: Conceptual insights and practical applications", Applied Energy 142:435–444** (verify DOI). Also verify the three-tenet framework's correct provenance — **distributional / procedural / recognition** justice is McCauley et al. 2013 ("Advancing energy justice: the triumvirate of tenets") and Jenkins et al. 2016 ("Energy justice: A conceptual review", Energy Research & Social Science) — do NOT attribute the tenets to Sovacool & Dworkin, whose contribution is the decision-making framework of energy-justice principles (availability, affordability, due process, transparency and accountability, sustainability, intra/intergenerational equity, responsibility — verify exact list before citing it).
2. Add the verified entries ([Sovacool2015], [McCauley2013] and/or [Jenkins2016] — at least Sovacool + one tenet source) to the References section of `paper.md`.
3. Write the binding framing constraints as an HTML comment block at the top of §6.4 in `paper.md` (kept through Task 7, deleted in Task 10):
   - Our fairness metrics (Gini, Jain, min-house floor, served-critical) operationalize ONLY the distributional tenet.
   - The natural-language negotiation record and explanation evaluation gesture toward procedural justice / transparency, but no resident or community ever evaluated them — claim "a step toward", never "achieves".
   - Recognition justice is touched only crudely (heterogeneous households, per-house critical-load fractions); say so.
   - FORBIDDEN phrasings: "energy justice is achieved/ensured/guaranteed", "equitable outcomes for communities", any claim about real households or vulnerable populations. The system allocates simulated kWh; the paper says exactly that.
   - Gini never appears in a sentence without at least one companion metric (advisor rule 4).
4. **Verify:** `figures --check` green; `ruff` clean; References section contains ≥2 energy-justice entries each carrying a DOI or verified venue-year.
5. **Commit:** `docs(paper): energy-justice framing constraints + Sovacool/tenet references` (+ Progress-log row + checkbox flip).

## Task 3 — Related-work literature pass + §2 draft

1. Web-search four buckets; verify every candidate's arXiv ID / DOI / venue-year before adding. Targets (verify, don't trust this list's IDs blindly either):
   - **LLM multi-agent coordination & negotiation (5–7 refs):** Park et al. 2023, Generative Agents (arXiv:2304.03442) — the anchor; plus a spread over: CAMEL (arXiv:2303.17760), AutoGen (arXiv:2308.08155), LLM negotiation self-play (Fu et al., arXiv:2305.10142), an LLM-agent cooperation/social-dilemma benchmark (e.g. GovSim, arXiv:2404.16698), and one 2024–2025 survey of LLM-based multi-agent systems. Search queries: "LLM multi-agent systems survey", "large language model negotiation agents", "LLM agents cooperation social dilemma benchmark".
   - **P2P energy sharing / energy markets (2–4 refs, deliberately thin — the contribution axis is CS/ML, not power systems):** one authoritative P2P energy-trading survey (e.g. Tushar et al.) and one high-profile P2P/prosumer market paper (e.g. Morstyn et al., Nature Energy 2018). Purpose: establish the domain exists and that classical mechanisms assume truthful numeric bids — the hook for robustness-to-misreporting.
   - **Energy justice + fairness metrics (3–4 refs):** the Task-2 entries + the original Jain's-index report (Jain, Chiu & Hawe 1984, DEC-TR-301 — verify) so Jain's index is properly attributed.
   - **LLM-as-judge (2–3 refs):** Zheng et al. 2023, "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena" (arXiv:2306.05685) + one judge-bias/reliability paper (e.g. Wang et al., "Large Language Models are not Fair Evaluators", arXiv:2305.17926). These support §6.6's design (judge ≠ author family; paraphrase-variant consistency check; lean on means).
   Stop condition: 18–24 total references across all buckets. This is a workshop draft — breadth over completeness; do not spiral.
2. Write §2 Related Work (~450 words, 4 paragraphs, one per bucket). Positioning sentences the section must land: (a) generative-agent memory/reflection architectures exist, but their coordination is rarely benchmarked against an optimization ceiling with a mandatory zero-LLM control; (b) P2P energy mechanisms optimize allocation but assume truthful structured bids and offer no natural-language explainability; (c) energy-justice scholarship supplies the fairness vocabulary this paper's metrics only partially operationalize; (d) LLM-as-judge is used with its known reliability caveats, mitigated by cross-family judging and rubric-paraphrase consistency checks.
3. Populate the References section with all verified entries, alphabetized by key.
4. **Verify:** `figures --check` green; `ruff` clean; every inline `[Key]` in §2 has a References entry and vice versa (`grep -o '\[[A-Z][A-Za-z]*20[0-9][0-9]\]' docs/paper/paper.md | sort -u` cross-checked against the References list); every entry has an ID/DOI/venue-year.
5. **Commit:** `docs(paper): related work section + verified reference list` (+ Progress-log row + checkbox flip).

## Task 4 — §3 Problem Setup and Simulator + §5 Experimental Setup

Sources: `docs/superpowers/archive/specs/2026-05-14-phase1-simulator-design.md`, `2026-07-07-phase3-benchmark-design.md` (Parts B/D for metrics + machinery), `2026-07-16-phase3.3-analysis-design.md`, `docs/phase3_results.md` header, `configs/scenarios/haves_havenots_solar*.yaml`, `scripts/eval_explanations.py`. Read them; write from them.

1. §3.1 (~250 words): discrete-time islanded-microgrid simulation; heterogeneous households (solar, battery, load, per-house critical-load fractions — the "haves/have-nots" construction); real load/solar traces (NREL/ResStock-derived); deterministic engine; energy is settled by physics (sender/receiver/bus caps), independent of what agents claim.
2. §3.2 (~250 words): the evaluation frame — advisor rule 6 verbatim in structure: performance = gap closed between `round_robin` (best fixed heuristic) and the centralized LP `lp_optimal` ceiling (full information, no communication limits — an upper bound, not a competitor); `no_coordination` floor; and the **zero-LLM control** (`llm_fallback`): the identical executor machinery with the LLM replaced by its deterministic fallback — the mandatory bar any LLM claim must clear. One sentence on why the control exists (the Phase-2 lesson, forward-referencing §6.2).
3. §3.3 (~200 words): served-load fraction (primary); fairness = Gini + Jain + min-house-served (Rawlsian floor) + served-critical-load fraction, always reported together (advisor rule 4); negotiation instrumentation counters (commitments made/expired, message delivery); explanation-quality rubric (forward-ref §5).
4. §5 (~350 words): the experiment grid — clean cell (`haves_havenots_solar__llm`) at seeds {23, 1, 7}; three failure cells at n=1 each with realized doses stated (defectors@7: 33.6% of generation capacity behind selfish-prompted agents; noise@23: SoC 10% + load 15% belief noise; comm@23: 2 messages/tick budget); each failure cell compared to its OWN same-seed control, never across cells. Agent model `claude-haiku-4-5`, temperature 0, prompt-cache determinism, total live spend ≈ $38.47. Explanation judging: `claude-sonnet-5` judge (≠ author family), 100 react rationales per judged cell, 1–5 on state_accuracy / actionability / consistency, three rubric paraphrases for judge-stability measurement. Reproducibility sentence: public MIT repo, per-phase tags, committed `reference_runs/` caches replay every live figure at $0, `python -m scripts.figures --all` regenerates all figures/tables.
5. Delete the filled sections' placeholder comments.
6. **Verify:** `figures --check` green; `ruff` clean; every number in the new prose grep-matches a line in `docs/phase3_results.md` or a committed spec/config (spot-check 33.6%, seeds, $38.47).
7. **Commit:** `docs(paper): problem setup, simulator, metrics, and experimental setup sections` (+ Progress-log row + checkbox flip).

## Task 5 — §4 Agent architecture & information flow

Sources: `docs/superpowers/archive/specs/2026-06-13-phase2-llm-agent-design.md` (§§1–3: component map, per-tick lifecycle, memory stream, reflection, policy schema, message protocol) and `2026-07-07-phase3-benchmark-design.md` Part A (A1–A3).

1. §4.1 (~350 words): per-household agent with a memory stream + periodic reflection, **citing [Park2023] prominently and by name in the first sentence** (advisor rule 5); the LLM plans and negotiates but a deterministic pure-Python policy executor acts every tick (machine-executable policy schema; no LLM in the act loop) — this separation is load-bearing for §6.2, say so; per-agent RNG and prompt-cache determinism in one sentence.
2. §4.2 (~350 words): the Phase-3 information-flow rework, framed as the paper's architectural contribution: (a) **INFORM-only beliefs** — an agent's beliefs about peers come exclusively from messages peers chose to send, never from oracle state reads (this is what makes defection *possible* and its study meaningful — a defector can misreport); (b) agents act on their own noised view (noise degrades the deciding agent, not just logging); (c) **binding negotiation** — ACCEPT creates a tracked commitment the executor serves, with expiry and retraction bookkeeping. Close with one sentence: this rework is what flipped the Phase-2 null into the Phase-3 positive (forward-ref §6.1/§6.2). Wording check: describe misreporting capability neutrally; no "attack", no "adversary" (advisor rule 3).
3. Delete the filled sections' placeholder comments.
4. **Verify:** `figures --check` green; `ruff` clean; `grep -c 'Park' docs/paper/paper.md` ≥ 2 (related work + §4.1).
5. **Commit:** `docs(paper): agent architecture and information-flow section` (+ Progress-log row + checkbox flip).

## Task 6 — §6.1 + §6.2: headline and the honest negative

Source: `docs/phase3_results.md` §1, §5.5, and the Phase-2.8/2.9 history in its §1 third bullet. COPY numbers; never derive.

1. §6.1 (~350 words + the seed table): reproduce the §1 three-seed table verbatim (no-coord / control / round_robin / live / LP / Δcontrol / gap-closed per seed 23/1/7). Claims, exactly these: **+5.8 ± 1.0 pts served vs the zero-LLM control, 3/3 seeds, closing 29.0% ± 2.9 of the control→LP gap**. The vs-round_robin margin (+2.0 ± 1.1) is reported WITH its decay (2.8 → 2.3 → 0.8) and the rr→LP gap-closed spread (13.0% ± 9.2, 5× the control spread), and the paragraph explicitly says the paper therefore claims the CONTROL comparison (advisor rule 6). Reference the headline figure. "First replicated live evidence the LLM layer adds value" is allowed verbatim (it is §1's claim).
2. §6.2 (~350 words), its own subsection, not a caveat paragraph (advisor rule 7): (a) history as finding — Phase 2.8 live Haiku LOST to round_robin (0.513 vs 0.525) and the Phase 2.9 zero-LLM control TIED it: the tuned executor, not the LLM, carried clean-cell throughput; the information-flow rework (§4.2) is what changed the answer; (b) the Sonnet capability ablation — clean@23, agents swapped `claude-haiku-4-5` → `claude-sonnet-5`, nothing else changed: 0.6685 vs 0.6726 served, gap-closed 29.4% vs 32.3% — a tie; a stronger model buys nothing here; the coordination advantage tracks scenario difficulty and information structure, not raw model capability; (c) ablation caveats in one sentence each: n=1; temperature omitted for Sonnet (rejects the parameter) so cache-replayable but not re-derivable from scratch; higher parse noise (plan-parse 5.8% vs 2.7%, react-unparsed 11.1% vs 0%) absorbed without moving any macro metric.
3. Delete placeholder comments; keep figure caption consistent with the table.
4. **Verify:** `figures --check` green; `ruff` clean; diff every number in the seed table against `docs/phase3_results.md` §1 by eye AND by grep (each cell value must appear in phase3_results.md).
5. **Commit:** `docs(paper): results — headline and honest-negative/ablation subsections` (+ Progress-log row + checkbox flip).

## Task 7 — §6.3–§6.6: failure axes, fairness, negotiation, explanations

Sources: `docs/phase3_results.md` §2–§5, `docs/phase3_tables.md`. Task 2's framing-constraint comment block governs §6.4. COPY numbers.

1. §6.3 (~400 words + a 3-row axis table: axis / dose / control / live / Δ): reproduce §2's table values. Required framings: **defectors** — the headline is "retains 89.1% of coordination value under 33.6% withheld generation" (naive proportional predicts 66.4% retained); +2.3 over a control that is structurally immune to prompt-realized defection; re-routing through loyal haves; misreporting-robustness framing ONLY (advisor rule 3 — grep the drafted section for "byzantine", "adversar", "attack", "threat" → 0 hits, case-insensitive). **Noise** — +0.87; ordering holds but margin compresses from clean's +4.6; the pre-registered "tolerates noise but pays for it" outcome; the mock floor shows noise mildly HELPS the fixed control (+1.3), which live must and does beat. **Comm** — −0.86 post-bugfix (originally −4.6; two commitment-integrity bugs C1/C2 accounted for most of the loss — the 202-retraction/202-dropped-reply exact match is worth one sentence as measurement forensics); residual = the hardcoded send-order bandwidth channel (11,194 of 16,954 messages budget-dropped), i.e. "a negotiation protocol costs some bandwidth under scarcity", plumbing not reasoning. All three: n=1, own-same-seed control, stated in-text.
2. §6.4 (~400 words, advisor rule 8): the finding is the tradeoff's ABSENCE — on clean/defectors/noise, Gini and Jain improve alongside served-load (defectors: live Gini 0.200 vs control 0.204, Jain 0.866 vs 0.861 — fairer AND more served); comm is the exception in both dimensions (Gini 0.453 vs 0.441, Jain 0.596 vs 0.608). Degenerate Rawlsian floor (~0.035–0.041 across all strategies) reported and explicitly not leaned on. Energy-justice paragraph per the Task-2 constraint block: metrics operationalize the distributional tenet [Sovacool2015, tenet source]; the negotiation record + explanations are a step toward procedural transparency, unevaluated by residents; forbidden phrasings absent. Reference both fairness figures.
3. §6.5 (~250 words + condensed 4-row table: clean@23, defectors@7, noise@23, comm@23 — commitments made/expired%/messages delivered, from `docs/phase3_tables.md`, pointer to the full table): clean-cell expiry 5.6–27.3% across seeds = honest haves over-promising against depleted batteries, NOT defectors reneging; comm cell delivered 4,224 of 16,954. One-sentence emission-vs-settlement caveat: negotiation counters are promise-side, bookkept at emission; served/Gini/Jain come from settled physics and are unaffected.
4. §6.6 (~350 words + the two-row quality table + one judge-stability sentence): clean 3.03/4.05/4.46, defectors 3.00/3.97/4.52 (state_accuracy/actionability/consistency, n=100 each, Sonnet judge ≠ Haiku authors [LLM-as-judge refs]); state_accuracy is the weakest axis — self-reported numbers drift from logged decision-time state (the 10-rationale hand audit example: judge docks a claimed 0.78 kWh headroom against a logged 1.13 kWh SoC); selfish prompting does not degrade explanation quality (clean ≈ defectors); judge stability: aggregate means stable under three rubric paraphrases (state 2.99–3.16, actionability 3.73–4.05, consistency 4.03–4.46) but per-message exact 3-way agreement only 32–38% (MAD 0.30–0.36) → the paper leans on means, not per-message scores. Close with: explanation quality is secondary to coordination performance (advisor).
5. Delete §6.4's constraint comment block ONLY if all its rules are satisfied; otherwise fix prose first. Delete remaining placeholder comments in §6.
6. **Verify:** `figures --check` green; `ruff` clean; `grep -icE 'byzantine|adversar|attack|threat' docs/paper/paper.md` → 0; every Gini mention has a companion metric in the same sentence or table row; all table values grep-match `phase3_results.md`/`phase3_tables.md`.
7. **Commit:** `docs(paper): results — failure axes, fairness, negotiation, explanations` (+ Progress-log row + checkbox flip).

## Task 8 — §7 Discussion, §8 Limitations, §9 Conclusion

Sources: `docs/phase3_results.md` §6–§7, CLAUDE.md Status block.

1. §7 Discussion (~350 words), three moves: (a) where the LLM earns its keep — degraded-information regimes (defection, noise) and fairness-preserving allocation, not clean-cell throughput, and why that is the right place to look (the control owns what tuned heuristics own); (b) what this suggests for LLM-agent evaluation generally — zero-LLM controls and optimization ceilings should be standard, since without them Phase 2.8's null would have been reported as a win; (c) explainability as the capability classical optimization does not attempt, with its measured accuracy gap (state_accuracy ~3.0) stated, not hidden.
2. §8 Limitations (~350 words, bulleted, condensed from `phase3_results.md` §6 — every advisor-mandated item present): (1) n=1 on every failure cell (clean headline is the only multi-seed claim); (2) single dataset family (`haves_havenots_solar`); (3) degenerate Rawlsian floor; (4) single-LLM-judge caveat, mean-level only; (5) **simulation only — no real-deployment claim** (advisor rule 1, its own bullet, unhedged); (6) the comm result measures negotiation plumbing, not reasoning; (7) one merged bookkeeping bullet — pre-fix frozen artifacts, expiry-counter incomparability pre/post-C2, emission-vs-settlement promise-side counters — with an explicit pointer: "full accounting in `docs/phase3_results.md` §6"; (8) energy-justice scope: only the distributional tenet is measured.
3. §9 Conclusion (~120 words): restate the control-relative headline + the two findings a reader should keep (robustness margin under misreporting; executor-carries-clean-cell honesty), one forward sentence (multi-seed failure cells, richer scenario families, human evaluation of explanations).
4. Delete placeholder comments.
5. **Verify:** `figures --check` green; `ruff` clean; §8 contains the deployment disclaimer (`grep -i 'deployment' docs/paper/paper.md` hits §8); all 8 limitation bullets present.
6. **Commit:** `docs(paper): discussion, limitations, conclusion` (+ Progress-log row + checkbox flip).

## Task 9 — Abstract, Introduction, Contributions (written last, claims-disciplined)

1. §1 Introduction (~600 words): problem (outage-time allocation among heterogeneous households needs fairness + robustness to bad information + explanations residents can read); gap (classical optimization: fairness under strong assumptions, brittle to misreporting, no explanations — cite the P2P energy refs; generative agents: rich coordination, rarely benchmarked against ceilings/controls — cite [Park2023] + bucket-a refs); approach (one LLM agent per household, INFORM-only beliefs, binding negotiation, deterministic executor, LP ceiling + zero-LLM control evaluation frame); findings preview (one sentence per Results subsection).
2. Numbered contributions list (exactly 4):
   C1 — an information-flow architecture (INFORM-only beliefs, binding negotiation) under which LLM coordination measurably beats a zero-LLM control (+5.8 ± 1.0 pts, 29.0% ± 2.9 of the control→LP gap, 3 seeds);
   C2 — a robustness characterization under misreporting, belief noise, and bandwidth scarcity, including the 89.1%-retained defection result;
   C3 — an honest-negative finding: the tuned executor carries clean-cell performance, model capability does not (Sonnet ablation tie), isolating where the LLM does and does not add value;
   C4 — a cross-family LLM-judge evaluation of agent explanations with a rubric-paraphrase stability analysis.
   NOT claimable, verbatim so the executor cannot drift: any security/adversarial contribution; any deployment readiness; any beat-round_robin headline; any energy-justice achievement; any power-systems contribution.
3. Abstract (150–200 words): problem, approach, headline number (vs control, with gap-closed), one robustness number (89.1% @ 33.6%), the honest negative in one clause, explanations in one clause, "simulation study" stated.
4. Populate `docs/paper/claims_audit.md`: one row per quantitative/superlative claim in Abstract + §1 (expect 8–12 rows): claim verbatim → paper § → `phase3_results.md` § → artifact path (e.g. `reference_runs/haves_havenots_solar__llm/.../summary.json` or `docs/phase3_tables.md`). Any claim that cannot be given a source row is rewritten or deleted before commit.
5. Delete remaining placeholder comments (Abstract/§1).
6. **Verify:** `figures --check` green; `ruff` clean; zero `<!-- filled by` comments remain (`grep -c 'filled by Task' docs/paper/paper.md` → 0); claims_audit.md row count ≥ 8; abstract word count 150–200 (`wc -w` on the extracted abstract).
7. **Commit:** `docs(paper): abstract, introduction, contributions + claims audit seed` (+ Progress-log row + checkbox flip).

## Task 10 — Number-accuracy audit + prose pass (the pass that once caught a wrong seed)

1. Mechanically extract every numeral: `grep -nE '[0-9]' docs/paper/paper.md` → for EACH hit, verify against its source (`docs/phase3_results.md`, `docs/phase3_tables.md`, committed `summary.json`s, scenario YAMLs, or a References metadata field). Work line-by-line; keep a session tally: N numerals checked, M discrepancies found. Fix every discrepancy in this task's commit. Typical catch classes from the Phase-3 precedent: transposed seeds, pre-fix vs post-fix comm numbers (−4.6 vs −0.86), expiry percentages compared across the C2 boundary, ± values swapped.
2. Cross-consistency checks: the same number quoted twice in the paper (abstract vs §6) is byte-identical; every figure caption's claims match the figure's section prose; every §-crossref resolves.
3. Append the audit outcome to `claims_audit.md`: date, numerals-checked count, discrepancies found/fixed (listed), "all claims traced" line. Extend the claims table to cover §6–§9 headline claims (expect 6–10 more rows).
4. Prose pass with the humanizer skill over `paper.md`: remove AI-writing tells (inflated symbolism, rule-of-three padding, vague attributions, em-dash overuse) WITHOUT changing any number, claim, or advisor-mandated framing; re-run the Task-7 forbidden-word grep after.
5. **Verify:** `figures --check` green; `ruff` clean; `grep -icE 'byzantine|adversar|attack|threat' docs/paper/paper.md` → 0; `grep -icE 'TBD|TODO|placeholder|XXX' docs/paper/paper.md` → 0; audit tally recorded in claims_audit.md.
6. **Commit:** `docs(paper): number-accuracy audit + claims traceability + prose pass` (+ Progress-log row + checkbox flip).

## Task 11 — Wrap: status sync + advisor/venue email draft

1. Full gate in the repo `.venv`, run twice: `ruff check sim tests scripts` clean; `mypy` → 37 files clean; `pytest` → 407 ✓; `python -m scripts.figures --check` green; `git status` shows only intended `docs/` changes.
2. Docs sync: CLAUDE.md four-phase table Phase-4 row → "in progress — paper draft v1 complete (`docs/paper/paper.md`); web demo + venue conversion pending advisor"; Status section gains one line pointing at `docs/paper/paper.md`; README status line gains the same pointer (one line, no restructure).
3. Draft the advisor email with the `/advisormeeting` skill. Required content: (a) paper draft v1 is complete at `docs/paper/paper.md` (GitHub link), Markdown, venue-agnostic, every number traced to committed artifacts; (b) the one decision needed: **venue — CHI vs ICLR vs WWW, main conference vs workshop** (workshop deadlines run ~3–4 months after mains; deadlines drive the conversion calendar); (c) confirmations embedded: Sovacool read before the fairness section, defectors framed as misreporting-robustness only, no deployment claim, honest negative has its own subsection, Gini never alone; (d) note VT/AZ cells dropped from Phase 4 scope (limitation retained in §8); (e) $0 spent this phase. Print the email in the session output AND save a copy to the scratchpad. Do NOT commit it; do NOT send it — Leo sends.
4. Security grep on the staged diff: `git diff --cached | grep -cE 'sk-ant-(api|oat)[0-9a-zA-Z_-]{15,}'` → 0. Push.
5. No git tag (tags mark phase completions; draft v1 pending advisor review is not one — `paper-v1` comes at submission per the roadmap).
6. **Verify:** full gate green twice; email text printed; CLAUDE.md/README pointers resolve.
7. **Commit:** `docs(paper): phase 4a wrap — draft v1 complete, status sync` (+ Progress-log row + final checkbox flips).

---

**Blocked on advisor reply (tracked, NOT tasks here):** venue choice → LaTeX/template conversion plan; any claim-strength edits the advisor requests; web-demo plan sequencing.
