"""Tests for real-data adapters.

These run against in-repo CSV fixtures so we don't need external account
approval. Tasks 22-23 add NREL solar and engine dispatch; Task 24 ships
fetch_data.py for the full real-data path.
"""

from datetime import datetime
from pathlib import Path

import pytest

from sim.adapters.pecan_street import PecanStreetLoad

_FIXTURES = Path(__file__).parent / "fixtures"


def test_pecan_street_load_reads_fixture() -> None:
    lp = PecanStreetLoad(csv_path=_FIXTURES / "pecan_sample.csv", dataid=1234)
    # 'use' at 00:00 is 1.2 kW
    assert lp.get_kw(datetime(2024, 7, 1, 0, 0)) == pytest.approx(1.2, abs=1e-6)


def test_pecan_street_load_forward_fills_short_gap() -> None:
    lp = PecanStreetLoad(csv_path=_FIXTURES / "pecan_sample.csv", dataid=1234)
    # 1 minute past the 00:00 sample -> forward-fill returns 1.2
    assert lp.get_kw(datetime(2024, 7, 1, 0, 1)) == pytest.approx(1.2, abs=1e-6)


def test_pecan_street_load_crashes_on_long_gap() -> None:
    lp = PecanStreetLoad(csv_path=_FIXTURES / "pecan_sample.csv", dataid=1234)
    # 2 hours past the last sample (00:45) -> exceeds 1h max gap
    with pytest.raises(ValueError, match="gap"):
        lp.get_kw(datetime(2024, 7, 1, 3, 0))
