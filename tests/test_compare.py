"""Tests for the cross-strategy gap-closed comparison."""

import math

import pytest

from scripts.compare import format_aggregate, format_table, gap_closed


def test_gap_closed_fraction() -> None:
    # rr=0.80, lp=1.00 -> overlay=0.90 closes half the gap
    assert gap_closed(served=0.90, rr=0.80, lp=1.00) == 0.5
    assert gap_closed(served=0.80, rr=0.80, lp=1.00) == 0.0
    assert gap_closed(served=1.00, rr=0.80, lp=1.00) == 1.0


def test_gap_closed_zero_gap_is_nan_not_zero() -> None:
    """lp ~= rr means there is no headroom to measure against — reporting 0%
    would read as 'no progress' when the denominator is the problem."""
    assert math.isnan(gap_closed(served=0.95, rr=0.95, lp=0.95))


def test_gap_closed_below_round_robin_is_negative_not_clamped() -> None:
    """Pre-2026-07-06 this clamped to 0.00%, hiding 'worse than baseline'
    (the live LLM cell's raw value was -273% on the old showcase numbers)."""
    assert gap_closed(served=0.70, rr=0.80, lp=1.00) == pytest.approx(-0.5, abs=1e-12)


def test_format_table_prints_negative_and_na_gap_closed() -> None:
    metrics = {
        "round_robin": {"served_load_fraction": 0.80, "unmet_kwh_total": 20.0, "gini_welfare": 0.1},
        "lp_optimal": {"served_load_fraction": 1.00, "unmet_kwh_total": 0.0, "gini_welfare": 0.0},
        "worse_than_rr": {
            "served_load_fraction": 0.70,
            "unmet_kwh_total": 30.0,
            "gini_welfare": 0.2,
        },
    }
    table = format_table(metrics)
    assert "-50.00%" in table
    no_gap = {
        "round_robin": {"served_load_fraction": 0.9, "unmet_kwh_total": 1.0, "gini_welfare": 0.1},
        "lp_optimal": {"served_load_fraction": 0.9, "unmet_kwh_total": 1.0, "gini_welfare": 0.1},
    }
    assert "n/a" in format_table(no_gap)


def test_format_aggregate_means_and_bounds() -> None:
    per_seed = {
        1: {
            "round_robin": {
                "served_load_fraction": 0.80,
                "unmet_kwh_total": 20.0,
                "gini_welfare": 0.10,
            },
            "lp_optimal": {
                "served_load_fraction": 1.00,
                "unmet_kwh_total": 0.0,
                "gini_welfare": 0.00,
            },
        },
        2: {
            "round_robin": {
                "served_load_fraction": 0.60,
                "unmet_kwh_total": 40.0,
                "gini_welfare": 0.30,
            },
            "lp_optimal": {
                "served_load_fraction": 0.90,
                "unmet_kwh_total": 10.0,
                "gini_welfare": 0.10,
            },
        },
    }
    table = format_aggregate(per_seed)
    assert "| round_robin | 0.7000 | 0.6000 | 0.8000 |" in table
    assert "100.00%" in table  # lp closes its own gap fully in every seed


def test_format_table_has_rows_for_each_strategy() -> None:
    metrics = {
        "no_coordination": {
            "served_load_fraction": 0.70,
            "unmet_kwh_total": 30.0,
            "gini_welfare": 0.10,
        },
        "round_robin": {
            "served_load_fraction": 0.80,
            "unmet_kwh_total": 20.0,
            "gini_welfare": 0.06,
        },
        "round_robin_overlay": {
            "served_load_fraction": 0.88,
            "unmet_kwh_total": 12.0,
            "gini_welfare": 0.04,
        },
        "lp_optimal": {"served_load_fraction": 0.96, "unmet_kwh_total": 4.0, "gini_welfare": 0.02},
    }
    table = format_table(metrics)
    for s in metrics:
        assert s in table
    assert "gap_closed" in table
