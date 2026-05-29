"""Tests for the cross-strategy gap-closed comparison."""

from scripts.compare import format_table, gap_closed


def test_gap_closed_fraction() -> None:
    # rr=0.80, lp=1.00 -> overlay=0.90 closes half the gap
    assert gap_closed(served=0.90, rr=0.80, lp=1.00) == 0.5
    assert gap_closed(served=0.80, rr=0.80, lp=1.00) == 0.0
    assert gap_closed(served=1.00, rr=0.80, lp=1.00) == 1.0


def test_gap_closed_handles_zero_gap() -> None:
    assert gap_closed(served=0.95, rr=0.95, lp=0.95) == 0.0


def test_gap_closed_clamps_below_round_robin() -> None:
    # a strategy worse than round_robin reports 0%, not a negative fraction
    assert gap_closed(served=0.70, rr=0.80, lp=1.00) == 0.0


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
