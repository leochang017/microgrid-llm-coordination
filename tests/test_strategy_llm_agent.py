"""sim/strategies/llm_agent.py: thin facade exposing prepare() + decide_transfers().

Integration tests with full engine + mock LLM happen in Task 21.
"""

from __future__ import annotations


def test_module_has_prepare_and_decide_transfers() -> None:
    from sim.strategies import llm_agent

    assert callable(llm_agent.prepare)
    assert callable(llm_agent.decide_transfers)


def test_prepare_returns_decide_callable(tmp_path) -> None:
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
    llm_strat._make_llm_client = lambda model, run_dir: mock  # type: ignore[attr-defined]

    decide = llm_strat.prepare(
        scenario=scenario,
        households=households,
        solar=None,
        loads=None,
        neighborhood=nb,
    )
    assert callable(decide)
