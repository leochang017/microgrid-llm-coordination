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


def test_defector_wrapper_corruption_changes_outcomes(tmp_path: Path) -> None:
    """Phase 3: the wrapper corrupts defectors' INFORM soc_kwh in transit, and
    receivers now ROUTE ON those corrupted beliefs (below-mean filter), so the
    defector cell must produce a different settled outcome than clean."""
    clean = _run("haves_havenots__llm.yaml", tmp_path)
    dirty = _run("haves_havenots__defectors.yaml", tmp_path)
    assert dirty["message_counts"]["sent"] > 0, dirty
    assert (
        dirty["served_load_fraction"] != clean["served_load_fraction"]
        or dirty["transfer_count"] != clean["transfer_count"]
    ), f"defector corruption had no settled effect: clean={clean['served_load_fraction']:.6f}/{clean['transfer_count']}, dirty={dirty['served_load_fraction']:.6f}/{dirty['transfer_count']}"


def test_noise_changes_outcomes_vs_clean(tmp_path: Path) -> None:
    """Phase 3: observation noise flows into INFORM payloads, hence into every
    receiver's beliefs, hence into routing — the noise cell must differ from
    clean on settled outcomes. (Pre-Phase-3 this test could only assert 'runs
    end-to-end' because act() read engine truth and the assertion was
    impossible by construction.)"""
    clean = _run("haves_havenots__llm.yaml", tmp_path)
    noisy = _run("haves_havenots__noise.yaml", tmp_path)
    assert noisy["served_load_fraction"] > 0.0, noisy
    assert (
        noisy["served_load_fraction"] != clean["served_load_fraction"]
        or noisy["transfer_count"] != clean["transfer_count"]
    ), f"noise had no settled effect: clean={clean['served_load_fraction']:.6f}/{clean['transfer_count']}, noisy={noisy['served_load_fraction']:.6f}/{noisy['transfer_count']}"


def test_comm_constraint_reduces_delivery_AND_changes_outcomes(tmp_path: Path) -> None:
    """Phase 3: dropped/budgeted messages destroy the beliefs sharing depends
    on, so comm constraints must both cut the delivery ratio AND move settled
    outcomes vs clean."""
    clean = _run("haves_havenots__llm.yaml", tmp_path)
    constrained = _run("haves_havenots__comm.yaml", tmp_path)
    clean_ratio = clean["message_counts"]["delivered"] / max(1, clean["message_counts"]["sent"])
    cons_ratio = constrained["message_counts"]["delivered"] / max(
        1, constrained["message_counts"]["sent"]
    )
    assert (
        cons_ratio < clean_ratio
    ), f"clean ratio={clean_ratio:.3f} constrained ratio={cons_ratio:.3f}"
    assert (
        constrained["served_load_fraction"] != clean["served_load_fraction"]
        or constrained["transfer_count"] != clean["transfer_count"]
    ), "comm constraints had no settled effect"
