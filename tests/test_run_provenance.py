"""Run-provenance + cost-accounting tests (Phase 2.9 Task 14).

Pre-2026-07-07: the scenario llm-block knobs were silently dead, config.json
omitted the llm/failure_modes blocks, summary.json's failure_modes_active was
hardcoded {} and llm_cost_usd_estimated hardcoded 0.0 (the shipped reference
run claimed $0.00 against ~$11.6 of real spend).
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from scripts.run import main as run_main
from sim.agents.cache import PromptCache
from sim.agents.llm import LLMResponse, MockLLMClient
from sim.engine import run
from sim.logging import JsonlLogger
from sim.scenario import load_scenario
from sim.strategies import llm_agent as llm_strat
from sim.strategies import llm_fallback
from sim.strategies.llm_agent import _estimate_cost_usd

_SCENARIO = Path("configs/scenarios/haves_havenots__llm.yaml")
REPO_ROOT = Path(__file__).resolve().parent.parent


def test_react_max_per_tick_is_wired_from_scenario_llm_block(tmp_path: Path) -> None:
    sc = load_scenario(_SCENARIO)
    sc = dataclasses.replace(sc, llm={**sc.llm, "react_max_per_tick": 1})
    logger = JsonlLogger(tmp_path / "r", scenario_id=sc.scenario_id)
    run(sc, None, logger, prepare=llm_fallback.prepare)
    logger.close()
    assert llm_strat._REGISTRY is not None
    assert all(a.react_max_per_tick == 1 for a in llm_strat._REGISTRY.agents.values())


def test_config_json_records_llm_and_failure_modes(tmp_path: Path) -> None:
    sc = load_scenario(Path("configs/scenarios/haves_havenots__defectors.yaml"))
    logger = JsonlLogger(tmp_path / "c", scenario_id=sc.scenario_id)
    run(sc, None, logger, prepare=llm_fallback.prepare)
    logger.close()
    cfg = json.loads((tmp_path / "c" / "config.json").read_text())
    assert cfg["llm"]["model"].startswith("claude-")
    assert cfg["failure_modes"]["defector_fraction"] == pytest.approx(0.2)
    assert "solar_tz_offset_hours" in cfg


def test_summary_failure_modes_active_is_filled(tmp_path: Path) -> None:
    sc = load_scenario(Path("configs/scenarios/haves_havenots__defectors.yaml"))
    logger = JsonlLogger(tmp_path / "s", scenario_id=sc.scenario_id)
    summary = run(sc, None, logger, prepare=llm_fallback.prepare)
    logger.close()
    assert summary["failure_modes_active"]["defector_fraction"] == pytest.approx(0.2)


def test_fresh_token_counters_skip_cache_hits(tmp_path: Path) -> None:
    client = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path / "cache", reference_dir=None),
        canned={"hello": LLMResponse(text="hi", tokens_in=100, tokens_out=20)},
    )
    from sim.agents.llm import LLMRequest

    req = LLMRequest(model="mock", system="s", user="hello world", max_tokens=64)
    client.call(req)
    client.call(req)  # cache hit — must not double-count
    assert client.n_fresh_tokens_in == 100
    assert client.n_fresh_tokens_out == 20


def test_estimate_cost_usd_by_model_family() -> None:
    assert _estimate_cost_usd("claude-haiku-4-5-20251001", 1_000_000, 200_000) == pytest.approx(
        1.0 + 1.0
    )
    assert _estimate_cost_usd("claude-sonnet-4-6", 1_000_000, 0) == pytest.approx(3.0)
    assert _estimate_cost_usd("mock-model", 1_000_000, 1_000_000) == 0.0


def test_llm_fallback_run_writes_message_log_and_counters(tmp_path, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)  # repo root for configs/
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run",
            "--scenario",
            "configs/scenarios/synthetic_lp_smoke.yaml",
            "--strategy",
            "llm_fallback",
            "--out-dir",
            str(tmp_path),
        ],
    )
    run_main()
    run_dir = next((tmp_path / "synthetic_lp_smoke" / "llm_fallback").iterdir())
    assert (run_dir / "messages.jsonl").exists()
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["message_counts"]["sent"] > 0
    assert "llm_call_counts_detailed" in summary


def test_reference_cell_dir_gains_seed_suffix(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # reference_runs/ is cwd-relative
    shutil.copytree(REPO_ROOT / "configs", tmp_path / "configs")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run",
            "--scenario",
            "configs/scenarios/synthetic_lp_smoke.yaml",
            "--strategy",
            "llm_fallback",
            "--reference-cell",
            "clean",
            "--seed",
            "7",
        ],
    )
    run_main()
    assert (
        tmp_path
        / "reference_runs"
        / "synthetic_lp_smoke"
        / "llm_fallback"
        / "clean__seed7"
        / "summary.json"
    ).exists()


def test_timestamp_run_dirs_carry_pid_suffix(tmp_path, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run",
            "--scenario",
            "configs/scenarios/synthetic_lp_smoke.yaml",
            "--strategy",
            "llm_fallback",
            "--out-dir",
            str(tmp_path),
        ],
    )
    run_main()
    run_dir = next((tmp_path / "synthetic_lp_smoke" / "llm_fallback").iterdir())
    assert run_dir.name.endswith(f"-{os.getpid()}")
