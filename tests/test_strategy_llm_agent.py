"""sim/strategies/llm_agent.py: thin facade exposing prepare() + decide_transfers().

Integration tests with full engine + mock LLM happen in Task 21.
"""

from __future__ import annotations


def test_module_has_prepare_and_decide_transfers() -> None:
    from sim.strategies import llm_agent

    assert callable(llm_agent.prepare)
    assert callable(llm_agent.decide_transfers)


def test_prepare_returns_decide_callable(tmp_path, monkeypatch) -> None:
    """prepare() should instantiate per-household agents and return a callable
    matching the engine's decide_transfers signature."""
    # Minimal hand-built Scenario (3 houses, no outages, llm strategy)
    from datetime import datetime

    from sim.agents.cache import PromptCache
    from sim.agents.llm import LLMResponse, MockLLMClient
    from sim.network import build_overlay_neighborhood
    from sim.scenario import Scenario
    from sim.strategies import llm_agent as llm_strat

    scenario = Scenario(
        scenario_id="t",
        start=datetime(2026, 1, 1, 8, 0),
        end=datetime(2026, 1, 1, 8, 30),
        dt_hours=0.25,
        seed=42,
        rows=1,
        cols=3,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
        strategy="llm_agent",
        data_source="synthetic",
        household_sampling={
            "pv_kw_peak": [4.0, 4.0],
            "battery_kwh": [10.0, 10.0],
            "rt_efficiency": 0.9,
            "dod_floor_frac": 0.1,
        },
    )

    # Build a small Households dict mimicking what engine.sample_households would emit
    from sim.household import Household
    from sim.types import HouseholdProfile

    households = {
        f"r0c{c}": Household(
            id=f"r0c{c}",
            pv_kw_peak=4.0,
            battery_kwh=10.0,
            battery_max_rate_kw=2.0,
            rt_efficiency=0.9,
            dod_floor_frac=0.1,
            grid_max_kw=10.0,
            profile=HouseholdProfile(description="t"),
        )
        for c in range(3)
    }

    nb = build_overlay_neighborhood(
        rows=1, cols=3, affiliations={}, bus_max_kw=50.0, bus_loss_factor=0.05
    )

    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path / "cache"),
        canned={"": LLMResponse(text="", tokens_in=0, tokens_out=0)},
    )
    monkeypatch.setattr(llm_strat, "_make_llm_client", lambda model, run_dir: mock)

    decide = llm_strat.prepare(
        scenario=scenario,
        households=households,
        solar=None,
        loads=None,
        neighborhood=nb,
    )
    assert callable(decide)


def _prepare_with_failure(tmp_path, fm):  # type: ignore[no-untyped-def]
    """Prepare the minimal 3-house llm_agent cell under a FailureModeConfig and
    return (decide, scenario, households). Injects a mock client via the factory
    param (no module-global monkeypatch)."""
    from datetime import datetime

    from sim.agents.cache import PromptCache
    from sim.agents.llm import LLMResponse, MockLLMClient
    from sim.household import Household
    from sim.network import build_overlay_neighborhood
    from sim.scenario import Scenario
    from sim.strategies import llm_agent as llm_strat
    from sim.types import HouseholdProfile

    scenario = Scenario(
        scenario_id="t",
        start=datetime(2026, 1, 1, 8, 0),
        end=datetime(2026, 1, 1, 8, 30),
        dt_hours=0.25,
        seed=42,
        rows=1,
        cols=3,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
        strategy="llm_agent",
        data_source="synthetic",
        household_sampling={
            "pv_kw_peak": [4.0, 4.0],
            "battery_kwh": [10.0, 10.0],
            "rt_efficiency": 0.9,
            "dod_floor_frac": 0.1,
        },
        failure_modes=fm,
    )
    households = {
        f"r0c{c}": Household(
            id=f"r0c{c}",
            pv_kw_peak=4.0,
            battery_kwh=10.0,
            battery_max_rate_kw=2.0,
            rt_efficiency=0.9,
            dod_floor_frac=0.1,
            grid_max_kw=10.0,
            profile=HouseholdProfile(description="t"),
        )
        for c in range(3)
    }
    nb = build_overlay_neighborhood(
        rows=1, cols=3, affiliations={}, bus_max_kw=50.0, bus_loss_factor=0.05
    )
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path / "cache"),
        canned={"": LLMResponse(text="", tokens_in=0, tokens_out=0)},
    )
    decide = llm_strat.prepare(
        scenario=scenario,
        households=households,
        solar=None,
        loads=None,
        neighborhood=nb,
        llm_client_factory=lambda model, run_dir: mock,
    )
    return decide, scenario, households


def test_wrapper_corruption_gated_on_realization(tmp_path) -> None:
    """`prompt` realization must leave the DefectorWrapper inert (empty defector
    set → maybe_corrupt is identity); only `wrapper`/`both` corrupt the channel."""
    from sim.agents.failure_modes import FailureModeConfig, assign_defectors

    for realization, expect_active in (("prompt", False), ("wrapper", True), ("both", True)):
        fm = FailureModeConfig(defector_fraction=0.2, defector_realization=realization)
        decide, scenario, households = _prepare_with_failure(tmp_path, fm)
        wrapped = decide.registry.defector_wrapper.defectors
        if expect_active:
            assert wrapped == assign_defectors(list(households), fm, scenario.seed)
            assert wrapped  # 1 defector of 3 at fraction 0.2 — non-empty
        else:
            assert wrapped == set()


def test_negotiation_counters_reach_summary(tmp_path) -> None:
    import json

    from sim.strategies import llm_agent as llm_strat

    counts = llm_strat.current_call_counts(registry=None)  # zero-dict shape
    for key in (
        "react_unparsed",
        "commitments_made",
        "commitments_expired",
        "react_amount_defaulted",
    ):
        assert key in counts and counts[key] == 0
    # and update_summary_with_counts writes the detailed dict through:
    (tmp_path / "summary.json").write_text("{}")
    llm_strat.update_summary_with_counts(tmp_path)  # module-global registry from last prepare
    detailed = json.loads((tmp_path / "summary.json").read_text())["llm_call_counts_detailed"]
    for key in (
        "react_unparsed",
        "commitments_made",
        "commitments_expired",
        "react_amount_defaulted",
    ):
        assert key in detailed


def test_reference_cache_dir_resolves_for_both_real_layouts(tmp_path, monkeypatch):
    from pathlib import Path

    from sim.strategies.llm_agent import _reference_cache_dir

    cache = tmp_path / "reference_runs" / "scenA" / "llm_agent" / "clean" / "llm_cache"
    cache.mkdir(parents=True)
    assert (
        _reference_cache_dir(tmp_path / "runs" / "scenA" / "llm_agent" / "20260712T120000-42")
        == cache
    )
    assert (
        _reference_cache_dir(tmp_path / "reference_runs" / "scenA" / "llm_agent" / "clean__seed7")
        == cache
    )
    monkeypatch.setenv("MICROGRID_REFERENCE_CELL", "does_not_exist")
    assert _reference_cache_dir(tmp_path / "runs" / "scenA" / "llm_agent" / "x") is None
    assert _reference_cache_dir(Path("/")) is None  # shallow path: no crash, None


def test_opus_price_row_is_current() -> None:
    import pytest

    from sim.strategies import llm_agent

    assert llm_agent._estimate_cost_usd("claude-opus-4-8", 1_000_000, 1_000_000) == pytest.approx(
        30.0
    )
