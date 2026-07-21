/**
 * Advisor-mandated honesty copy for the signed gap-closed figure.
 *
 * `gapClosedControlToLp` is SIGNED and is negative on the comm cell (-0.0325), where
 * the LLM condition did worse than the zero-LLM control. "closes -3% of the gap" is
 * nonsense and `Math.abs`-ing the sign would reframe a loss as a win, so the phrasing
 * branches on the sign instead.
 *
 * This lives in one place on purpose: the overview cards (`routes/+page.svelte`) and
 * the replay page (`routes/run/[cell]/+page.svelte`) both render this sentence, and
 * the two drifting apart is exactly the failure the rule exists to prevent.
 */
export function gapClosedPhrase(gap: number): string {
	const pct = Math.round(Math.abs(gap) * 100);
	return gap >= 0
		? `closes ${pct}% of the control→LP gap`
		: `ends ${pct}% of the control→LP gap BELOW the zero-LLM control`;
}
