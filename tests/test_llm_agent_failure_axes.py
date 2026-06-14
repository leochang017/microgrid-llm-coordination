"""Each failure-mode axis must produce a measurable change vs the clean cell."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from sim.agents.cache import PromptCache
from sim.agents.llm import LLMResponse, MockLLMClient

ROOT = Path(__file__).resolve().parent.parent
SCEN_DIR = ROOT / "configs" / "scenarios"


def _canned_mock(tmp_path: Path) -> MockLLMClient:
    policy_yaml = yaml.safe_dump(
        {
            "sharing_intent": "generous",
            "share_min_soc_frac": 0.30,
            "max_share_kw_per_tick": 1.5,
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


def _run(scenario_file: str, tmp_path: Path) -> dict:
    from sim.agents.protocol import MessageBus
    from sim.engine import run
    from sim.logging import JsonlLogger
    from sim.network import build_overlay_neighborhood
    from sim.scenario import load_scenario
    from sim.strategies import llm_agent as llm_strat

    s = load_scenario(SCEN_DIR / scenario_file)
    mock = _canned_mock(tmp_path / scenario_file.replace(".yaml", ""))
    llm_strat._make_llm_client = lambda model, run_dir: mock  # type: ignore[attr-defined]
    nb = build_overlay_neighborhood(
        rows=s.rows,
        cols=s.cols,
        affiliations=s.affiliations,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
    )
    bus = MessageBus(neighborhood=nb, seed=s.seed)
    out = tmp_path / scenario_file.replace(".yaml", "")
    out.mkdir()
    run(
        scenario=s,
        decide_transfers=None,
        prepare=llm_strat.prepare,
        logger=JsonlLogger(run_dir=out, scenario_id=s.scenario_id),
        message_bus=bus,
    )
    return json.loads((out / "summary.json").read_text())  # type: ignore[no-any-return]


def test_defectors_scenario_runs_end_to_end(tmp_path: Path) -> None:
    """The defectors scenario completes a full run with measurable message traffic.

    Note: in Phase 2 the `wrapper` defector realization mutates the *payload* of
    outbound OFFER/REQUEST/INFORM messages (their claimed kwh / soc_kwh), but the
    underlying Transfer math used by settle_transfers is unaffected — so settled
    outcomes (served fraction, transfer count) don't necessarily differ from clean.
    The wrapper's per-message mutation is unit-tested in test_failure_modes.py.
    Strict effect-on-outcome from defectors is a Phase 3 concern (requires
    receiver-side reasoning that consumes the message payload as ground truth).
    """
    dirty = _run("haves_havenots__defectors.yaml", tmp_path)
    assert dirty["served_load_fraction"] > 0.0, dirty
    assert dirty["message_counts"]["sent"] > 0, dirty


def test_noise_changes_outcomes(tmp_path: Path) -> None:
    clean = _run("haves_havenots__llm.yaml", tmp_path)
    noisy = _run("haves_havenots__noise.yaml", tmp_path)
    differs = (
        noisy["transfer_count"] != clean["transfer_count"]
        or abs(noisy["served_load_fraction"] - clean["served_load_fraction"]) > 1e-4
    )
    assert differs, f"noise produced no observable difference: {clean=} {noisy=}"


def test_comm_constraint_reduces_message_delivery(tmp_path: Path) -> None:
    clean = _run("haves_havenots__llm.yaml", tmp_path)
    constrained = _run("haves_havenots__comm.yaml", tmp_path)
    clean_ratio = clean["message_counts"]["delivered"] / max(1, clean["message_counts"]["sent"])
    cons_ratio = constrained["message_counts"]["delivered"] / max(
        1, constrained["message_counts"]["sent"]
    )
    assert (
        cons_ratio < clean_ratio
    ), f"clean ratio={clean_ratio:.3f} constrained ratio={cons_ratio:.3f}"
