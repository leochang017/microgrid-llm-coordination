"""Phase 3.3 figure data-assembly layer (matplotlib-free — CI has no viz extra)."""

from __future__ import annotations

import math

import pytest

from scripts.figures import (
    LIVE_CELLS,
    METHOD_ORDER,
    cell_served_gap_closed,
    collect_cell,
    read_live_summary,
    render_tables,
)

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
