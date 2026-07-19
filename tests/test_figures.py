"""Phase 3.3 figure data-assembly layer (matplotlib-free — CI has no viz extra)."""

from __future__ import annotations

import dataclasses
import json
import math

import pytest

from scripts.figures import (
    EXPECTED_LIVE,
    LIVE_CELLS,
    METHOD_ORDER,
    _assert_scenario_matches_committed_config,
    _committed_config_path,
    cell_served_gap_closed,
    check_live_numbers,
    collect_cell,
    read_live_summary,
    render_tables,
)
from sim.scenario import load_scenario

CLEAN = "haves_havenots_solar__llm"


def test_read_live_summary_returns_the_committed_number() -> None:
    # Exact committed value for the clean cell, seed 23 — guards against a
    # silently moved/rewritten artifact.
    s = read_live_summary(CLEAN, 23)
    assert s["served_load_fraction"] == 0.6725764138021589
    assert s["scenario_id"] == CLEAN


def test_read_live_summary_missing_run_raises() -> None:
    # The clean cell was never run at seed 42, and `all` has no live run at all.
    with pytest.raises(KeyError):
        read_live_summary(CLEAN, 42)
    with pytest.raises(KeyError):
        read_live_summary("haves_havenots_solar__all", 7)


def test_collect_cell_merges_baselines_and_live() -> None:
    methods = collect_cell(CLEAN, 23)
    assert set(METHOD_ORDER) <= set(methods)
    # The live method is the committed number, not a re-run.
    assert methods["llm_agent"]["served_load_fraction"] == 0.6725764138021589
    for m in METHOD_ORDER:
        served = methods[m]["served_load_fraction"]
        assert 0.0 <= served <= 1.0, f"{m} served out of range: {served}"
    # LP is the ceiling; the control is the mandatory bar.
    assert (
        methods["lp_optimal"]["served_load_fraction"]
        >= methods["llm_agent"]["served_load_fraction"]
    )


def test_gap_closed_is_finite_and_positive_on_clean() -> None:
    # Clean cell: live beats the control, so gap_closed(control->LP) > 0.
    gc = cell_served_gap_closed(collect_cell(CLEAN, 23))
    assert math.isfinite(gc)
    assert gc > 0.0


def test_live_cells_cover_the_four_committed_cells() -> None:
    assert LIVE_CELLS[CLEAN] == {23: "clean__seed23", 1: "clean__seed1", 7: "clean__seed7"}
    assert set(LIVE_CELLS) == {
        "haves_havenots_solar__llm",
        "haves_havenots_solar__comm",
        "haves_havenots_solar__defectors",
        "haves_havenots_solar__noise",
    }


def test_render_tables_populates_explanation_quality_from_committed_evals(tmp_path) -> None:
    # With the Stage-4 judge artifacts committed, --tables renders the per-cell
    # quality table + the rubric-consistency section (not the pending stub).
    out = render_tables(out_path=tmp_path / "tables.md")
    txt = out.read_text()
    assert "Pending Stage 4" not in txt
    assert "## Explanation quality (Sonnet judge)" in txt
    assert "| clean | 23 | 100 |" in txt  # per-cell default-rubric quality row
    assert "## Rubric consistency" in txt
    assert "mean abs deviation" in txt


def test_ablation_cell_reads_committed_sonnet_summary() -> None:
    s = read_live_summary("haves_havenots_solar__llm_sonnet", 23)
    assert s["served_load_fraction"] == 0.6685037752963732
    assert s["scenario_id"] == "haves_havenots_solar__llm_sonnet"


def test_tables_include_capability_ablation_row(tmp_path) -> None:
    out = render_tables(out_path=tmp_path / "tables.md")
    txt = out.read_text()
    assert "clean (Sonnet)" in txt  # negotiation-table row for the ablation
    assert "capability" in txt.lower()  # the ablation is labeled as such


def test_check_passes_against_pinned_values_today() -> None:
    # C6-1: --check must actually assert, not just print. Must pass unchanged
    # against the currently-committed artifacts.
    check_live_numbers()


def test_check_covers_every_live_cell_seed_pair() -> None:
    live_pairs = {(cell, seed) for cell, seeds in LIVE_CELLS.items() for seed in seeds}
    assert set(EXPECTED_LIVE) == live_pairs


def test_check_raises_on_a_perturbed_pinned_value() -> None:
    bad = dict(EXPECTED_LIVE)
    bad[(CLEAN, 23)] = {**bad[(CLEAN, 23)], "served_load_fraction": 0.0}
    with pytest.raises(SystemExit):
        check_live_numbers(expected=bad)


def test_scenario_matches_committed_config_is_a_noop_today() -> None:
    # C6-3: the current scenario YAML has not drifted from the frozen
    # config.json the committed clean@23 cell actually ran under.
    config_path = _committed_config_path(CLEAN, 23)
    assert config_path is not None
    from scripts.figures import scenario_path

    base = dataclasses.replace(load_scenario(scenario_path(CLEAN)), seed=23)
    _assert_scenario_matches_committed_config(base, config_path)  # no raise


def test_scenario_matches_committed_config_raises_on_drift(tmp_path) -> None:
    config_path = _committed_config_path(CLEAN, 23)
    assert config_path is not None
    committed = json.loads(config_path.read_text())
    committed["bus_max_kw"] = committed["bus_max_kw"] + 1.0  # simulate a YAML edit
    drifted = tmp_path / "config.json"
    drifted.write_text(json.dumps(committed))

    from scripts.figures import scenario_path

    base = dataclasses.replace(load_scenario(scenario_path(CLEAN)), seed=23)
    with pytest.raises(ValueError, match="drifted"):
        _assert_scenario_matches_committed_config(base, drifted)


def test_collect_cell_still_works_for_a_cell_with_no_committed_config() -> None:
    # regen_baselines must not choke when the (cell, seed) pair has no
    # committed live run at all (e.g. a hypothetical future cell) — the
    # drift check is a no-op, not a hard requirement of a committed run.
    assert _committed_config_path("haves_havenots_solar__llm", 999) is None


def _judge_row(sender: str, t_sent: str, correlation_id: str, score: int) -> dict:
    return {
        "sender": sender,
        "t_sent": t_sent,
        "correlation_id": correlation_id,
        "state_accuracy": score,
        "actionability": score,
        "consistency": score,
    }


def test_variant_agreement_pairs_matching_rows_normally() -> None:
    from scripts.figures import _variant_agreement

    v1 = {"samples": [_judge_row("r0c0", "T", "aaa", 3)]}
    v2 = {"samples": [_judge_row("r0c0", "T", "aaa", 4)]}
    agree = _variant_agreement([v1, v2])
    for axis in ("state_accuracy", "actionability", "consistency"):
        mad, _exact, paired = agree[axis]
        assert paired == 1
        assert mad == pytest.approx(0.5)


def test_variant_agreement_rejects_synthetic_mismatched_pair() -> None:
    # C6-5: (sender, t_sent) alone collides ~80% of the time on real data (an
    # agent can author several messages in the same tick) — two DIFFERENT
    # messages from the same sender at the same tick must not be silently
    # averaged together just because their (sender, t_sent) happen to match.
    from scripts.figures import _variant_agreement

    v1 = {"samples": [_judge_row("r0c0", "T", "aaa", 5)]}
    v2 = {"samples": [_judge_row("r0c0", "T", "bbb", 1)]}  # different message, same tick
    agree = _variant_agreement([v1, v2])
    for axis in ("state_accuracy", "actionability", "consistency"):
        _mad, _exact, paired = agree[axis]
        assert paired == 0  # rejected, not silently averaged into 0.0/2.0 MAD


def test_variant_agreement_is_a_noop_on_committed_clean_cell_data() -> None:
    # Must not change behavior on the currently-committed artifacts: all three
    # rubric variants for clean@23 have 0 unparseable drops, so tightening the
    # identity check must still pair every row.
    import json as _json

    from scripts.figures import REF, _variant_agreement

    d = REF / "haves_havenots_solar__llm" / "llm_agent" / "clean__seed23"
    variants = [
        _json.loads((d / name).read_text())
        for name in (
            "explanations_eval.json",
            "explanations_eval__terse.json",
            "explanations_eval__roleplay.json",
        )
    ]
    agree = _variant_agreement(variants)
    for axis in ("state_accuracy", "actionability", "consistency"):
        _, _, paired = agree[axis]
        assert paired == min(len(v["samples"]) for v in variants)
