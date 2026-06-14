"""Replay determinism: two runs with the same mock LLM produce byte-identical
state/events/messages. Verifies per-agent RNG, bus RNG, defector RNG, noise RNG
determinism."""

from __future__ import annotations

from pathlib import Path

import yaml

from sim.agents.cache import PromptCache
from sim.agents.llm import LLMResponse, MockLLMClient

ROOT = Path(__file__).resolve().parent.parent
SCEN_DIR = ROOT / "configs" / "scenarios"


def _canned_mock(tmp_path: Path) -> MockLLMClient:
    policy_yaml = yaml.safe_dump(
        {
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
    )
    return MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={
            "You are household": LLMResponse(
                text=f"r\n\n```yaml\n{policy_yaml}\n```", tokens_in=400, tokens_out=160
            ),
            "You are reacting": LLMResponse(
                text="ACCEPT\nrationale: ok", tokens_in=80, tokens_out=20
            ),
        },
    )


def test_two_runs_with_same_mock_are_byte_identical(tmp_path: Path) -> None:
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
        mock = _canned_mock(tmp_path / f"mock_{label}")
        llm_strat._make_llm_client = lambda model, run_dir: mock  # type: ignore[attr-defined]
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
