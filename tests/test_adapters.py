"""Tests for real-data adapters.

These run against in-repo CSV fixtures so we don't need external account
approval. Tasks 22-23 add NREL solar and engine dispatch; Task 24 ships
fetch_data.py for the full real-data path.
"""

from datetime import datetime
from pathlib import Path

import pytest

from sim.adapters.nrel_solar import NRELSolar
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


def test_nrel_solar_returns_zero_at_midnight() -> None:
    sp = NRELSolar(csv_path=_FIXTURES / "nrel_sample.csv", seed=42)
    assert sp.get_kw(datetime(2024, 7, 1, 0, 0)) == pytest.approx(0.0, abs=1e-6)


def test_nrel_solar_peaks_at_noon() -> None:
    sp = NRELSolar(csv_path=_FIXTURES / "nrel_sample.csv", seed=42, derate=1.0)
    # 900 W/m^2 * 1.0 derate / 1000 = 0.9, plus small noise (~2%)
    val = sp.get_kw(datetime(2024, 7, 1, 12, 0))
    assert 0.85 <= val <= 0.95


def test_nrel_solar_interpolates_between_hours() -> None:
    sp = NRELSolar(csv_path=_FIXTURES / "nrel_sample.csv", seed=42, derate=1.0)
    # The fixture has 12:00 -> 900 and 18:00 -> 40. Linear at t=12:30 gives
    # 900 - (900 - 40) * 0.5/6 = 900 - 71.67 = 828.33 W/m^2 -> 0.828 kW. Plus
    # the small noise.
    val = sp.get_kw(datetime(2024, 7, 1, 12, 30))
    assert 0.78 <= val <= 0.88


def test_nrel_solar_deterministic_under_seed() -> None:
    sp1 = NRELSolar(csv_path=_FIXTURES / "nrel_sample.csv", seed=42)
    sp2 = NRELSolar(csv_path=_FIXTURES / "nrel_sample.csv", seed=42)
    t = datetime(2024, 7, 1, 9, 0)
    assert sp1.get_kw(t) == sp2.get_kw(t)
