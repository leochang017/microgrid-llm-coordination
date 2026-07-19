"""Replay determinism: two runs with the same mock LLM produce byte-identical
state/events/messages. Verifies per-agent RNG, bus RNG, defector RNG, noise RNG
determinism."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from sim.agents.cache import PromptCache
from sim.agents.llm import LLMRequest, LLMResponse, MockLLMClient

ROOT = Path(__file__).resolve().parent.parent
SCEN_DIR = ROOT / "configs" / "scenarios"

_POLICY_DICT = {
    "sharing_intent": "balanced",
    "share_min_soc_frac": 0.40,
    "max_share_kw_per_tick": 1.0,
    "recipient_priority": [
        {"circle": "owner", "weight": 1.0},
        {"circle": "geographic", "weight": 0.5},
    ],
    "distrusted_peers": [],
    "request_urgency": "normal",
    "belief_note": "",
    "ttl_ticks": 4,
}


def _canned_mock(tmp_path: Path, mode: str = "text") -> MockLLMClient:
    """mode="tool" mirrors live runs (Anthropic tool-use returns tool_input);
    mode="text" is the legacy YAML-code-fence path. Pre-2026-07-07 every e2e
    mock test used ONLY the text path, so the branch the paper's live runs
    actually take (agent.py's tool_input parse) had zero replay coverage."""
    if mode == "tool":
        plan_resp = LLMResponse(
            text="",
            tokens_in=400,
            tokens_out=160,
            tool_input={**_POLICY_DICT, "reflection": "r"},
        )
    else:
        policy_yaml = yaml.safe_dump(_POLICY_DICT)
        plan_resp = LLMResponse(
            text=f"r\n\n```yaml\n{policy_yaml}\n```", tokens_in=400, tokens_out=160
        )
    return MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={
            "You are household": plan_resp,
            "You are reacting": LLMResponse(
                text="ACCEPT\nrationale: ok", tokens_in=80, tokens_out=20
            ),
        },
    )


@pytest.mark.parametrize("mode", ["text", "tool"])
def test_two_runs_with_same_mock_are_byte_identical(tmp_path: Path, mode: str, monkeypatch) -> None:
    from sim.agents.protocol import MessageBus
    from sim.engine import run
    from sim.logging import JsonlLogger
    from sim.network import build_overlay_neighborhood
    from sim.scenario import load_scenario
    from sim.strategies import llm_agent as llm_strat

    s = load_scenario(SCEN_DIR / "haves_havenots__llm.yaml")
    nb = build_overlay_neighborhood(
        rows=s.rows,
        cols=s.cols,
        affiliations=s.affiliations,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
    )

    def one_run(label: str) -> Path:
        out = tmp_path / label
        out.mkdir()
        mock = _canned_mock(tmp_path / f"mock_{label}", mode)
        monkeypatch.setattr(llm_strat, "_make_llm_client", lambda model, run_dir: mock)
        bus = MessageBus(neighborhood=nb, seed=s.seed)
        run(
            scenario=s,
            decide_transfers=None,
            prepare=llm_strat.prepare,
            logger=JsonlLogger(run_dir=out, scenario_id=s.scenario_id),
            message_bus=bus,
        )
        return out

    a = one_run("a")
    b = one_run("b")

    assert (a / "state.jsonl").read_bytes() == (b / "state.jsonl").read_bytes()
    assert (a / "events.jsonl").read_bytes() == (b / "events.jsonl").read_bytes()
    assert (a / "messages.jsonl").read_bytes() == (b / "messages.jsonl").read_bytes()


class _TrapLLMClient(MockLLMClient):
    """A MockLLMClient whose ``_call_provider`` must never be reached.

    Used to prove a resumed run never falls through the cache (local miss +
    reference miss) to the "paid" provider path -- every request must be
    served by ``PromptCache.get``'s reference tier."""

    def _call_provider(self, req: LLMRequest) -> LLMResponse:
        raise AssertionError("paid call attempted — cache resume failed")


def test_reference_cell_resume_replays_with_zero_provider_calls(
    tmp_path: Path, monkeypatch
) -> None:
    """A run resumed against a populated reference-cell cache must complete
    with ZERO provider-level calls -- every LLMClient.call() must hit the
    reference tier of PromptCache.get(). This is the property that twice
    saved paid live runs in the field (P3.1 T15, validated live 2026-07-15/16).

    Mirrors the real resume mechanism: ``_reference_cache_dir`` resolves
    ``<repo_root>/reference_runs/<scen>/<strat>/<cell>/llm_cache`` from the
    run dir's path structure (parents[3] = repo root), gated by
    ``MICROGRID_REFERENCE_CELL`` (see sim/strategies/llm_agent.py:84-101 and
    tests/test_strategy_llm_agent.py:197-214 for the path-resolution contract
    this test relies on)."""
    from sim.agents.protocol import MessageBus
    from sim.engine import run
    from sim.logging import JsonlLogger
    from sim.network import build_overlay_neighborhood
    from sim.scenario import load_scenario
    from sim.strategies import llm_agent as llm_strat

    s = load_scenario(SCEN_DIR / "haves_havenots__llm.yaml")
    nb = build_overlay_neighborhood(
        rows=s.rows,
        cols=s.cols,
        affiliations=s.affiliations,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
    )
    monkeypatch.setenv("MICROGRID_REFERENCE_CELL", "clean")

    policy_yaml = yaml.safe_dump(_POLICY_DICT)
    canned = {
        "You are household": LLMResponse(
            text=f"r\n\n```yaml\n{policy_yaml}\n```", tokens_in=400, tokens_out=160
        ),
        "You are reacting": LLMResponse(text="ACCEPT\nrationale: ok", tokens_in=80, tokens_out=20),
    }

    def _normal_factory(model: str, run_dir: Path) -> MockLLMClient:
        # Mirrors the real _make_llm_client: local_dir + reference_dir wired
        # through the SAME path-resolution helper live runs use.
        cache = PromptCache(
            local_dir=run_dir / "llm_cache",
            reference_dir=llm_strat._reference_cache_dir(run_dir),
        )
        return MockLLMClient(cache=cache, canned=dict(canned))

    def _trap_factory(model: str, run_dir: Path) -> _TrapLLMClient:
        cache = PromptCache(
            local_dir=run_dir / "llm_cache",
            reference_dir=llm_strat._reference_cache_dir(run_dir),
        )
        return _TrapLLMClient(cache=cache, canned={})

    # Run 1: populate the reference cell. Its OWN llm_cache dir is exactly the
    # reference cache the second run below will resume from -- no separate
    # copy step, matching how a real live-run reference cell is just a
    # committed run's llm_cache directory.
    ref_run_dir = tmp_path / "reference_runs" / "scenA" / "llm_agent" / "clean"
    monkeypatch.setattr(llm_strat, "_make_llm_client", _normal_factory)
    run(
        scenario=s,
        decide_transfers=None,
        prepare=llm_strat.prepare,
        logger=JsonlLogger(run_dir=ref_run_dir, scenario_id=s.scenario_id),
        message_bus=MessageBus(neighborhood=nb, seed=s.seed),
    )
    summary1 = json.loads((ref_run_dir / "summary.json").read_text())
    assert (ref_run_dir / "llm_cache").exists()

    # Run 2: a fresh run dir laid out exactly like a real runs/<scen>/<strat>/<ts>
    # path (three levels under tmp_path, matching _reference_cache_dir's
    # parents[3]-is-repo-root contract), with a client that raises if it ever
    # has to fall through to the provider.
    resume_run_dir = tmp_path / "runs" / "scenA" / "llm_agent" / "20260719T000000-1"
    monkeypatch.setattr(llm_strat, "_make_llm_client", _trap_factory)
    run(
        scenario=s,
        decide_transfers=None,
        prepare=llm_strat.prepare,
        logger=JsonlLogger(run_dir=resume_run_dir, scenario_id=s.scenario_id),
        message_bus=MessageBus(neighborhood=nb, seed=s.seed),
    )
    summary2 = json.loads((resume_run_dir / "summary.json").read_text())

    # The resumed run's macro/physics metrics must match the populating run's
    # exactly -- same cached policies replayed via the reference tier drive
    # the identical physical outcome.
    for key in (
        "served_load_fraction",
        "gini_welfare",
        "transfer_count",
        "min_house_served_fraction",
        "jains_index",
        "served_critical_load_fraction",
    ):
        assert summary2[key] == summary1[key], key
