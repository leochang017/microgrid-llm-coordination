"""Tests for the explanation-judge harness (Phase 3 Task 8)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from scripts.eval_explanations import _MOCK_JUDGE_RESPONSE, _parse_scores, evaluate_run
from sim.agents.cache import PromptCache
from sim.agents.llm import LLMRequest, LLMResponse, MockLLMClient


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
    # Two ticks: the message at 00:00 is graded against the PRIOR (23:45) row,
    # which is its decision-time state (P3.1 T17).
    prior = {
        "t": "2026-06-30T23:45:00",
        "house_id": "r0c0",
        "soc_kwh": 7.5,
        "solar_kw": 0.0,
        "load_kw": 1.0,
        "grid_status": False,
        "wasted_kwh": 0.0,
        "unmet_kwh": 0.0,
    }
    state = {
        "t": "2026-07-01T00:00:00",
        "house_id": "r0c0",
        "soc_kwh": 7.0,
        "solar_kw": 0.0,
        "load_kw": 1.0,
        "grid_status": False,
        "wasted_kwh": 0.0,
        "unmet_kwh": 0.0,
    }
    (run_dir / "state.jsonl").write_text(json.dumps(prior) + "\n" + json.dumps(state) + "\n")


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


def _mini_run_dir(tmp_path: Path) -> Path:
    (tmp_path / "config.json").write_text(json.dumps({"seed": 0}))
    t0, t1 = "2018-01-01T00:00:00", "2018-01-01T00:15:00"
    (tmp_path / "state.jsonl").write_text(
        json.dumps(
            {
                "t": t0,
                "house_id": "r0c0",
                "soc_kwh": 5.0,
                "solar_kw": 0.0,
                "load_kw": 1.0,
                "grid_status": False,
                "unmet_kwh": 0.0,
            }
        )
        + "\n"
        + json.dumps(
            {
                "t": t1,
                "house_id": "r0c0",
                "soc_kwh": 4.0,
                "solar_kw": 0.0,
                "load_kw": 1.0,
                "grid_status": False,
                "unmet_kwh": 0.0,
            }
        )
        + "\n"
    )
    msg = {
        "sender": "r0c0",
        "recipient": "r0c1",
        "performative": "ACCEPT",
        "payload": {"kwh": 0.4},
        "rationale_nl": "I hold 5 kWh",
        "templated": False,
        "correlation_id": "c1",
        "outcome": "delivered",
    }
    (tmp_path / "messages.jsonl").write_text(
        json.dumps({**msg, "t_sent": t0}) + "\n" + json.dumps({**msg, "t_sent": t1}) + "\n"
    )
    return tmp_path


@dataclass
class _RecordingMock(MockLLMClient):
    last_user: str = ""

    def _call_provider(self, req: LLMRequest) -> LLMResponse:
        self.last_user = req.user
        return super()._call_provider(req)


def test_judge_pairs_with_decision_time_state_and_skips_first_tick(tmp_path: Path) -> None:
    run_dir = _mini_run_dir(tmp_path)
    rec = _RecordingMock(
        cache=PromptCache(local_dir=tmp_path / "jc", reference_dir=None),
        canned={"Rubric": _MOCK_JUDGE_RESPONSE},
    )
    result = evaluate_run(run_dir, client=rec)
    assert result["n_scored"] == 1  # the t1 message only
    assert result["n_first_tick_excluded"] == 1  # the t0 message has no prior row
    assert '"soc_kwh": 5.0' in rec.last_user  # graded against the t0 (start-of-tick) row
    assert "decision time" in rec.last_user


def test_judge_client_uses_env_credential(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-oat01-FAKE")
    (tmp_path / "config.json").write_text(json.dumps({"seed": 0}))
    (tmp_path / "state.jsonl").write_text("")
    (tmp_path / "messages.jsonl").write_text("")
    captured = {}

    class _FakeClient:
        def __init__(self, cache, api_key):
            captured["key"] = api_key

        def call(self, req):
            raise AssertionError("no messages should be judged")

    monkeypatch.setattr("scripts.eval_explanations.AnthropicLLMClient", _FakeClient)
    evaluate_run(tmp_path)
    assert captured["key"] == "sk-ant-oat01-FAKE"  # routes to Authorization: Bearer
