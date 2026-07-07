# Sweep: phase3_grid

scenario: `configs/scenarios/haves_havenots_solar__llm.yaml`  seeds: [23, 1, 7, 42, 99]

## axis: defector_fraction (`failure_modes.defector_fraction`)

| value | round_robin | llm_fallback |
|---|---|---|
| 0.0 | 0.7438 [0.5961,0.8638] g=0.196 | 0.7018 [0.5389,0.8193] g=0.230 |
| 0.1 | 0.7438 [0.5961,0.8638] g=0.196 | 0.7039 [0.5384,0.8302] g=0.229 |
| 0.2 | 0.7438 [0.5961,0.8638] g=0.196 | 0.7145 [0.5371,0.8281] g=0.215 |
| 0.4 | 0.7438 [0.5961,0.8638] g=0.196 | 0.7190 [0.5405,0.8365] g=0.213 |

## axis: noise_soc_std (`failure_modes.obs_noise.soc_std_frac`)

| value | round_robin | llm_fallback |
|---|---|---|
| 0.0 | 0.7438 [0.5961,0.8638] g=0.196 | 0.7018 [0.5389,0.8193] g=0.230 |
| 0.05 | 0.7438 [0.5961,0.8638] g=0.196 | 0.7265 [0.5768,0.8323] g=0.202 |
| 0.1 | 0.7438 [0.5961,0.8638] g=0.196 | 0.7304 [0.5788,0.8396] g=0.200 |
| 0.2 | 0.7438 [0.5961,0.8638] g=0.196 | 0.7293 [0.5769,0.8388] g=0.202 |

## axis: comm_budget (`failure_modes.comm.per_tick_budget`)

| value | round_robin | llm_fallback |
|---|---|---|
| None | 0.7438 [0.5961,0.8638] g=0.196 | 0.7018 [0.5389,0.8193] g=0.230 |
| 4 | 0.7438 [0.5961,0.8638] g=0.196 | 0.6829 [0.5554,0.7602] g=0.257 |
| 2 | 0.7438 [0.5961,0.8638] g=0.196 | 0.5820 [0.4273,0.6653] g=0.376 |
| 1 | 0.7438 [0.5961,0.8638] g=0.196 | 0.4596 [0.3010,0.5316] g=0.504 |


## Reading this matrix (2026-07-07, mock canned-policy floor)

Cells are served-load mean [min,max] over 5 seeds + mean gini. All agents run the
same fixed canned policy (MockLLM) — this is the FLOOR live-LLM runs are judged
against, isolating pure information-flow mechanics from reasoning quality.

- **round_robin is perfectly flat on every axis** — empirical proof that rule-based
  baselines read engine truth and are structurally immune to information-quality
  failures. Only belief-driven strategies can be hurt by (or reason around) them.
- **comm_budget is the devastating axis**: served 0.702 -> 0.460 and gini 0.230 ->
  0.504 as the per-tick message budget drops to 1. Communication scarcity destroys
  both efficiency and equity for message-borne coordination.
- **defector (wrapper) and noise mildly HELP served-load** (0.702 -> ~0.72-0.73):
  symmetric belief corruption makes peers look needier on average, which increases
  sharing in this abundance regime. Two implications, both honest: (1) channel
  corruption alone is not a served-load threat under fixed policies — the
  interesting defector test is prompt-realized selfishness (live, budget-gated);
  (2) a live LLM that reasons about trust/staleness must beat these accidental
  gains, not just the clean-cell number.
- **Cross-seed spread (~27 points)** dwarfs most treatment effects — every paper
  claim needs the paired multi-seed protocol, never single-seed deltas.
