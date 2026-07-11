"""Tests for the zero-LLM control strategy + messaging-off ablation (P2.9 T13)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from sim.engine import run
from sim.logging import JsonlLogger
from sim.overrides import apply_overrides
from sim.scenario import load_scenario
from sim.strategies import llm_agent as llm_strat
from sim.strategies import llm_fallback

_SCENARIO = Path("configs/scenarios/haves_havenots__llm.yaml")


def _run(sc, tmp_path: Path, sub: str):  # type: ignore[no-untyped-def]
    logger = JsonlLogger(tmp_path / sub, scenario_id=sc.scenario_id)
    summary = run(sc, None, logger, prepare=llm_fallback.prepare)
    logger.close()
    return summary


def test_llm_fallback_runs_with_zero_llm_calls(tmp_path: Path) -> None:
    """End-to-end on the showcase LLM scenario: no plan calls, no react calls,
    no cache traffic — but real transfers from the pure-Python executor."""
    sc = load_scenario(_SCENARIO)
    summary = _run(sc, tmp_path, "control")
    counts = llm_strat.current_call_counts()
    assert counts["reflect_plan"] == 0
    assert counts["react_msg"] == 0
    assert counts["cache_hits"] == 0
    assert counts["cache_misses"] == 0
    assert summary["transfer_count"] > 0
    assert 0.0 < summary["served_load_fraction"] < 1.0


def test_llm_fallback_is_deterministic(tmp_path: Path) -> None:
    sc = load_scenario(_SCENARIO)
    a = _run(sc, tmp_path, "a")
    b = _run(sc, tmp_path, "b")
    assert a == b


def test_messaging_off_flag_suppresses_all_bus_traffic(tmp_path: Path) -> None:
    """llm.messaging: off keeps every message off the bus — and since Phase 3
    ALL peer knowledge is message-borne, a communication blackout means no
    beliefs, hence NO transfers. (Pre-Phase-3, messaging-off changed nothing
    about transfers — proof that messages were epiphenomenal. Now the ablation
    is the causal lower anchor: coordination requires communication.)"""
    from sim.agents.protocol import MessageBus
    from sim.network import build_overlay_neighborhood

    sc = load_scenario(_SCENARIO)
    sc = dataclasses.replace(sc, llm={**sc.llm, "messaging": "off"})
    nb = build_overlay_neighborhood(
        rows=sc.rows,
        cols=sc.cols,
        affiliations=sc.affiliations,
        bus_max_kw=sc.bus_max_kw,
        bus_loss_factor=sc.bus_loss_factor,
    )
    bus = MessageBus(neighborhood=nb, seed=sc.seed)
    logger = JsonlLogger(tmp_path / "moff", scenario_id=sc.scenario_id)
    summary = run(sc, None, logger, prepare=llm_fallback.prepare, message_bus=bus)
    logger.close()
    messages = (tmp_path / "moff" / "messages.jsonl").read_text().strip()
    assert messages == ""
    assert summary["transfer_count"] == 0  # no beliefs -> nobody shares blind


def test_prepared_closures_keep_their_own_registries(tmp_path: Path) -> None:
    """Two prepares in one process must not cross-attribute counters — the
    module global is only a convenience for the last run (P2.9 T16)."""
    sc = load_scenario(_SCENARIO)
    decide_a = llm_fallback.prepare(sc, {}, None, None, None, run_dir=tmp_path / "a")
    decide_b = llm_fallback.prepare(sc, {}, None, None, None, run_dir=tmp_path / "b")
    reg_a = decide_a.registry  # type: ignore[attr-defined]
    reg_b = decide_b.registry  # type: ignore[attr-defined]
    assert reg_a is not reg_b
    assert llm_strat._REGISTRY is reg_b  # global tracks the LAST prepare
    counts_a = llm_strat.current_call_counts(reg_a)
    assert counts_a["reflect_plan"] == 0


def test_prompt_realization_defectors_are_inert_for_the_zero_llm_control(tmp_path: Path) -> None:
    """Zero-LLM control, prompt-realization defectors: selfish prompts are inert
    (LLM disabled) and (post-P3.1-T5) the wrapper no longer fires either, so the
    defector cell must be byte-identical to clean."""
    base = load_scenario("configs/scenarios/haves_havenots_solar__llm.yaml")
    treated = apply_overrides(
        base, ["failure_modes.defector_fraction=0.2"]
    )  # realization -> prompt
    clean = _run(base, tmp_path, "clean")
    defector_prompt = _run(treated, tmp_path, "defector_prompt")
    assert clean["served_load_fraction"] == defector_prompt["served_load_fraction"]
    assert clean["transfer_count"] == defector_prompt["transfer_count"]
