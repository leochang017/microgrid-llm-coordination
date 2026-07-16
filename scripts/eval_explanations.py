"""Rubric-based LLM-judge for agent explanations (Phase 3 Task 8).

  python -m scripts.eval_explanations --run-dir runs/<...>/<ts> [--n 50] [--mock]

Samples LLM-authored messages (templated=false in messages.jsonl) from a run,
pairs each with the sender's logged reality at that tick (state.jsonl), and
asks a judge model to score the rationale 1-5 on three axes:

  state_accuracy : does the explanation match the sender's actual logged state?
  actionability  : could a resident act on it (amounts, direction, reason)?
  consistency    : does it match what the sender actually did that tick?

Output: <run-dir>/explanations_eval.json with per-axis means + per-sample rows.

METHOD NOTE [ADVISOR]: LLM-judge with this rubric is the provisional
instrument (a human-subjects study is not feasible pre-college). Confirm with
the advisor before the paper freezes on it. Judge calls go through the
standard PromptCache, so re-scoring a run is free; --mock uses a fixed-score
stub for tests and costs nothing.

Sampling is deterministic (seeded from the run's config.json seed), so two
invocations score the same messages.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
from pathlib import Path
from typing import Any

from sim.agents.cache import PromptCache
from sim.agents.llm import AnthropicLLMClient, LLMClient, LLMRequest, LLMResponse, MockLLMClient

_AXES = ("state_accuracy", "actionability", "consistency")

# The judge must run a model from a different family than the author (advisor
# requirement); the practical judge is claude-sonnet-5, which runs adaptive
# thinking by default. On the real (state + rubric) prompts it spends 400-640
# output tokens thinking before emitting the ~30-token JSON verdict, so a tight
# budget truncates mid-thought into an empty, unparseable reply (measured 84/100
# failures at 100 tokens; end_turn with a clean parse at 1024). Budget clears the
# thinking with margin; billing is on tokens actually used, not this cap.
_JUDGE_MAX_TOKENS = 2048

_JUDGE_SYSTEM = (
    "You are grading explanations that household energy agents gave their "
    "neighbors during a simulated grid outage. Score STRICTLY on the rubric; "
    "reply with ONLY a JSON object like "
    '{"state_accuracy": 1-5, "actionability": 1-5, "consistency": 1-5}.'
)

_MOCK_JUDGE_RESPONSE = LLMResponse(
    text='{"state_accuracy": 3, "actionability": 3, "consistency": 3}',
    tokens_in=0,
    tokens_out=0,
)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# Paraphrases of ONE rubric, not three different rubrics. The advisor
# (2026-07-15) asked for judge-consistency reporting: if a reworded prompt moves
# the scores, the instrument is measuring its own phrasing rather than the
# explanations, and the Task-8 numbers can't carry the paper's claim. That test
# is only valid if each variant asks the same question — so the axis names and
# the 1-5 scale are fixed, and only the wording around them moves.
_RUBRICS: dict[str, str] = {
    "default": (
        "Rubric (score each 1-5):\n"
        "- state_accuracy: does the explanation's account of the sender's "
        "situation match the logged decision-time state?\n"
        "- actionability: could the recipient act on this (clear amount, "
        "direction, and reason)?\n"
        "- consistency: is the explanation consistent with the action taken "
        "(the performative and payload)?"
    ),
    "terse": (
        "Score each 1-5:\n"
        "- state_accuracy: explanation vs. logged state — truthful?\n"
        "- actionability: enough detail to act on?\n"
        "- consistency: explanation vs. action taken — do they agree?"
    ),
    "roleplay": (
        "You are the neighbour who received this message. Score each 1-5:\n"
        "- state_accuracy: having now seen their real logged state, were they "
        "honest with you about their situation?\n"
        "- actionability: could you have done something concrete with this "
        "message, without asking a follow-up question?\n"
        "- consistency: did what they told you line up with what they actually did?"
    ),
}


def _judge_prompt(
    msg: dict[str, Any], state_row: dict[str, Any] | None, *, variant: str = "default"
) -> str:
    reality = (
        json.dumps(
            {
                k: state_row[k]
                for k in ("soc_kwh", "solar_kw", "load_kw", "grid_status", "unmet_kwh")
                if state_row and k in state_row
            }
        )
        if state_row
        else "(no state row found for sender at this tick)"
    )
    return (
        f"Message from {msg['sender']} to {msg['recipient']} "
        f"({msg['performative']}, payload={json.dumps(msg['payload'])}):\n"
        f"Explanation given: \"{msg['rationale_nl']}\"\n"
        f"Sender's actual logged state at decision time (start of that tick): {reality}\n\n"
        f"{_RUBRICS[variant]}"
    )


def _parse_scores(text: str) -> dict[str, int] | None:
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        raw = json.loads(m.group(0))
        scores = {axis: int(raw[axis]) for axis in _AXES}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    if all(1 <= v <= 5 for v in scores.values()):
        return scores
    return None


def evaluate_run(
    run_dir: Path,
    *,
    n: int = 50,
    client: LLMClient | None = None,
    model: str = "claude-haiku-4-5-20251001",
    rubric_variant: str = "default",
) -> dict[str, Any]:
    if rubric_variant not in _RUBRICS:
        raise ValueError(f"unknown rubric variant {rubric_variant!r}; have {sorted(_RUBRICS)}")
    messages = _load_jsonl(run_dir / "messages.jsonl")
    config = json.loads((run_dir / "config.json").read_text())
    states = _load_jsonl(run_dir / "state.jsonl")
    state_by_key = {(r["t"], r["house_id"]): r for r in states}
    # state.jsonl rows are POST-step; the sender authored its rationale from the
    # START-of-tick state = the previous tick's row. First-tick messages have no
    # logged prior row — exclude rather than grade against a wrong snapshot.
    ticks = sorted({r["t"] for r in states})
    prev_tick = {t: (ticks[i - 1] if i > 0 else None) for i, t in enumerate(ticks)}

    authored = [m for m in messages if not m.get("templated", True)]
    templated_count = len(messages) - len(authored)
    n_first_tick_excluded = sum(1 for m in authored if prev_tick.get(m["t_sent"]) is None)
    authored = [m for m in authored if prev_tick.get(m["t_sent"]) is not None]
    rng = random.Random(int(config.get("seed", 0)))
    sample = authored if len(authored) <= n else rng.sample(authored, n)

    if client is None:
        client = AnthropicLLMClient(
            cache=PromptCache(local_dir=run_dir / "judge_cache", reference_dir=None),
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        )

    rows: list[dict[str, Any]] = []
    unparseable = 0
    for msg in sample:
        prompt = _judge_prompt(
            msg,
            state_by_key.get((prev_tick[msg["t_sent"]], msg["sender"])),
            variant=rubric_variant,
        )
        resp = client.call(
            LLMRequest(model=model, system=_JUDGE_SYSTEM, user=prompt, max_tokens=_JUDGE_MAX_TOKENS)
        )
        scores = _parse_scores(resp.text)
        if scores is None:
            unparseable += 1
            continue
        rows.append({"sender": msg["sender"], "t_sent": msg["t_sent"], **scores})

    means = {axis: (sum(r[axis] for r in rows) / len(rows) if rows else None) for axis in _AXES}
    result: dict[str, Any] = {
        "run_dir": str(run_dir),
        "rubric_variant": rubric_variant,
        "n_messages_total": len(messages),
        "n_llm_authored": len(authored),
        "n_templated": templated_count,
        "n_scored": len(rows),
        "n_first_tick_excluded": n_first_tick_excluded,
        "n_unparseable_judge_replies": unparseable,
        "means": means,
        "samples": rows,
    }
    # Per-variant filename: each of these costs real money, so a second variant
    # must not overwrite the first (pre-live review, 2026-07-12). "default"
    # keeps the original name so existing artifacts stay where the docs say.
    name = (
        "explanations_eval.json"
        if rubric_variant == "default"
        else f"explanations_eval__{rubric_variant}.json"
    )
    (run_dir / name).write_text(json.dumps(result, indent=2))
    return result


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--n", type=int, default=50)
    p.add_argument("--model", type=str, default="claude-haiku-4-5-20251001")
    p.add_argument(
        "--mock",
        action="store_true",
        help="Use a fixed-score stub judge (no API calls; for tests/dry runs).",
    )
    p.add_argument(
        "--rubric-variant",
        type=str,
        default="default",
        choices=sorted(_RUBRICS),
        help=(
            "Paraphrase of the rubric to judge with. Re-judging a run under "
            "each variant measures whether the judge is stable under rewording; "
            "non-default variants write explanations_eval__<variant>.json."
        ),
    )
    args = p.parse_args()
    client = None
    if args.mock:
        client = MockLLMClient(
            cache=PromptCache(local_dir=args.run_dir / "judge_cache", reference_dir=None),
            # Match on the scale line, which every variant shares.
            canned={"1-5": _MOCK_JUDGE_RESPONSE},
        )
    result = evaluate_run(
        args.run_dir,
        n=args.n,
        client=client,
        model=args.model,
        rubric_variant=args.rubric_variant,
    )
    means = ", ".join(
        f"{axis}={result['means'][axis]:.2f}"
        if result["means"][axis] is not None
        else f"{axis}=n/a"
        for axis in _AXES
    )
    print(
        f"scored {result['n_scored']}/{result['n_llm_authored']} LLM-authored messages "
        f"({result['n_templated']} templated excluded) -> {means}"
    )


if __name__ == "__main__":
    main()
