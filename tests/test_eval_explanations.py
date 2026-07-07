"""Tests for the explanation-judge harness (Phase 3 Task 8)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.eval_explanations import _MOCK_JUDGE_RESPONSE, _parse_scores, evaluate_run
from sim.agents.cache import PromptCache
from sim.agents.llm import LLMResponse, MockLLMClient


def _write_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "config.json").write_text(json.dumps({"seed": 23}))
    msgs = [
        {  # LLM-authored ACCEPT — should be scored
            "t_sent": "2026-07-01T00:00:00",
            "sender": "r0c0",
            "recipient": "r0c1",
            "performative": "ACCEPT",
            "payload": {"kwh": 0.4},
            "rationale_nl": "I have surplus after covering tonight's load",
            "correlation_id": "a1",
            "templated": False,
            "outcome": "delivered",
            "reason": "",
        },
        {  # templated OFFER — must be excluded from judging
            "t_sent": "2026-07-01T00:00:00",
            "sender": "r0c1",
            "recipient": "r0c0",
            "performative": "OFFER",
            "payload": {"kwh": 0.2},
            "rationale_nl": "SoC 8.00/10 kWh above 0.30 threshold; sharing",
            "correlation_id": "a2",
            "templated": True,
            "outcome": "delivered",
            "reason": "",
        },
    ]
    (run_dir / "messages.jsonl").write_text("\n".join(json.dumps(m) for m in msgs) + "\n")
    state = {
        "t": "2026-07-01T00:00:00",
        "house_id": "r0c0",
        "soc_kwh": 7.5,
        "solar_kw": 0.0,
        "load_kw": 1.0,
        "grid_status": False,
        "wasted_kwh": 0.0,
        "unmet_kwh": 0.0,
    }
    (run_dir / "state.jsonl").write_text(json.dumps(state) + "\n")


def test_parse_scores_accepts_json_and_rejects_garbage() -> None:
    assert _parse_scores('{"state_accuracy": 4, "actionability": 5, "consistency": 3}') == {
        "state_accuracy": 4,
        "actionability": 5,
        "consistency": 3,
    }
    assert _parse_scores("I refuse to grade this") is None
    assert _parse_scores('{"state_accuracy": 9, "actionability": 5, "consistency": 3}') is None


def test_evaluate_run_scores_only_llm_authored_messages(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_run(run_dir)
    client = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path / "cache", reference_dir=None),
        canned={"Rubric": _MOCK_JUDGE_RESPONSE},
    )
    result = evaluate_run(run_dir, n=10, client=client)
    assert result["n_llm_authored"] == 1
    assert result["n_templated"] == 1
    assert result["n_scored"] == 1
    assert result["means"]["state_accuracy"] == 3.0
    saved = json.loads((run_dir / "explanations_eval.json").read_text())
    assert saved["n_scored"] == 1


def test_evaluate_run_counts_unparseable_judge_replies(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_run(run_dir)
    client = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path / "cache", reference_dir=None),
        canned={"Rubric": LLMResponse(text="not json at all", tokens_in=0, tokens_out=0)},
    )
    result = evaluate_run(run_dir, n=10, client=client)
    assert result["n_scored"] == 0
    assert result["n_unparseable_judge_replies"] == 1
    assert result["means"]["state_accuracy"] is None
