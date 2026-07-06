"""Zero-LLM control strategy (Phase 2.9 Task 13).

Runs the EXACT llm_agent machinery — same MessageBus, same failure modes, same
pure-Python ``act()`` executor — but with the LLM permanently disabled: every
agent keeps its initial ``Policy.default_round_robin_fallback()`` forever and
no plan/react call is ever made.

This is the mandatory control for the paper: the served-load difference
between ``llm_agent`` and ``llm_fallback`` on the same scenario bounds the
marginal contribution of LLM-authored policies. If the two land in the same
place, the LLM layer is not doing the work — the hand-tuned executor is.

Costs $0 and needs no API key:
  python -m scripts.run --scenario configs/scenarios/haves_havenots__llm.yaml \\
      --strategy llm_fallback
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sim.agents.cache import PromptCache
from sim.agents.llm import LLMClient, MockLLMClient
from sim.agents.protocol import MessageBus
from sim.household import Household
from sim.network import Neighborhood
from sim.scenario import Scenario
from sim.strategies import llm_agent as _llm

decide_transfers = _llm.decide_transfers


def _never_call_llm(model: str, run_dir: Path) -> LLMClient:
    """A client that must never be reached — llm_disabled short-circuits all calls."""
    del model
    return MockLLMClient(
        cache=PromptCache(local_dir=run_dir / "llm_cache", reference_dir=None),
        canned={},  # any call raises NoMockResponseError -> loud failure
    )


def prepare(
    scenario: Scenario,
    households: dict[str, Household],
    solar: Any,
    loads: Any,
    neighborhood: Neighborhood,
    *,
    message_bus: MessageBus | None = None,
    run_dir: Path | None = None,
    **_: Any,
) -> _llm.DecideFn:
    return _llm.prepare(
        scenario,
        households,
        solar,
        loads,
        neighborhood,
        message_bus=message_bus,
        run_dir=run_dir,
        llm_client_factory=_never_call_llm,
        disable_llm=True,
    )
