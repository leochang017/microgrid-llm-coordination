# Sweep: phase3_grid

> **Regenerated 2026-07-12 after Phase 3.1** — the previous defector dose-response was
> an artifact of ungated wrapper corruption (P3.1 T5). With the wrapper now gated on
> `defector_realization` and this grid's defector cells using the `prompt` realization,
> the zero-LLM control's defector rows are FLAT (selfish prompts are inert without an
> LLM). Numbers also reflect T1 (receiver cap), T7–T9 (negotiation), and T19
> (`critical_load_frac` draw).

scenario: `configs/scenarios/haves_havenots_solar__llm.yaml`  seeds: [23, 1, 7, 42, 99]

Strategy label: **llm_fallback** (LLM disabled — agents keep the tuned fallback policy;
MockLLM exists only as a loud-failure sentinel).

## axis: defector_fraction (`failure_modes.defector_fraction`)

| value | round_robin | llm_fallback |
|---|---|---|
| 0.0 | 0.7362 [0.6444,0.8023] g=0.204 | 0.6993 [0.6269,0.7607] g=0.227 |
| 0.1 | 0.7362 [0.6444,0.8023] g=0.204 | 0.6993 [0.6269,0.7607] g=0.227 |
| 0.2 | 0.7362 [0.6444,0.8023] g=0.204 | 0.6993 [0.6269,0.7607] g=0.227 |
| 0.4 | 0.7362 [0.6444,0.8023] g=0.204 | 0.6993 [0.6269,0.7607] g=0.227 |

## axis: noise_soc_std (`failure_modes.obs_noise.soc_std_frac`)

| value | round_robin | llm_fallback |
|---|---|---|
| 0.0 | 0.7362 [0.6444,0.8023] g=0.204 | 0.6993 [0.6269,0.7607] g=0.227 |
| 0.05 | 0.7362 [0.6444,0.8023] g=0.204 | 0.7144 [0.6368,0.7675] g=0.214 |
| 0.1 | 0.7362 [0.6444,0.8023] g=0.204 | 0.7173 [0.6399,0.7716] g=0.213 |
| 0.2 | 0.7362 [0.6444,0.8023] g=0.204 | 0.7171 [0.6376,0.7716] g=0.217 |

## axis: comm_budget (`failure_modes.comm.per_tick_budget`)

| value | round_robin | llm_fallback |
|---|---|---|
| None | 0.7362 [0.6444,0.8023] g=0.204 | 0.6993 [0.6269,0.7607] g=0.227 |
| 4 | 0.7362 [0.6444,0.8023] g=0.204 | 0.6835 [0.5869,0.7559] g=0.249 |
| 2 | 0.7362 [0.6444,0.8023] g=0.204 | 0.5524 [0.4844,0.6083] g=0.405 |
| 1 | 0.7362 [0.6444,0.8023] g=0.204 | 0.4402 [0.3812,0.4994] g=0.524 |


## Reading this matrix (regenerated 2026-07-12, mock canned-policy floor)

Cells are served-load mean [min,max] over 5 seeds + mean gini. All agents run the same
fixed tuned fallback policy with the LLM DISABLED — this is the FLOOR live-LLM runs are
judged against, isolating pure information-flow mechanics from reasoning quality.

- **round_robin is perfectly flat on every axis** — empirical proof that rule-based
  baselines read engine truth and are structurally immune to information-quality
  failures. Only belief-driven strategies can be hurt by (or reason around) them.
- **The defector axis is now FLAT for the control too** (0.6993 across all fractions).
  This is the P3.1 T5 fix landing: defector cells use `prompt` realization, so with no
  LLM the selfish system prompts are inert and the channel wrapper no longer fires. The
  old matrix's moving defector rows were a bug artifact (ungated wrapper corruption) —
  the real defector test is prompt-realized selfishness under a LIVE LLM (budget-gated).
- **comm_budget is the devastating axis**: served 0.699 -> 0.440 and gini 0.227 -> 0.524
  as the per-tick message budget drops to 1. Communication scarcity destroys both
  efficiency and equity for message-borne coordination.
- **noise mildly HELPS served-load** (0.699 -> ~0.717): symmetric belief corruption makes
  peers look needier on average, which increases sharing in this abundance regime. A live
  LLM that reasons about trust/staleness must beat this accidental gain, not just clean.
- **Cross-seed spread (~13-16 points)** still dwarfs most treatment effects — every paper
  claim needs the paired multi-seed protocol, never single-seed deltas.
