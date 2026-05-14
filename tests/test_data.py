"""Tests for data adapters."""

from datetime import datetime

import pytest

from sim.data import LoadProfile, SolarProfile, SyntheticLoad, SyntheticSolar


def test_synthetic_solar_returns_zero_at_night() -> None:
    sp = SyntheticSolar(peak_kw=10.0, sunrise_hour=6, sunset_hour=18)
    # Midnight
    assert sp.get_kw(datetime(2024, 7, 1, 0, 0)) == 0.0
    # 5 AM
    assert sp.get_kw(datetime(2024, 7, 1, 5, 0)) == 0.0


def test_synthetic_solar_peaks_at_noon() -> None:
    sp = SyntheticSolar(peak_kw=10.0, sunrise_hour=6, sunset_hour=18)
    t = datetime(2024, 7, 1, 12, 0)
    assert sp.get_kw(t) == pytest.approx(10.0, abs=1e-6)


def test_synthetic_solar_symmetric() -> None:
    sp = SyntheticSolar(peak_kw=10.0, sunrise_hour=6, sunset_hour=18)
    # 9 AM and 3 PM are equidistant from solar noon; output should match.
    assert sp.get_kw(datetime(2024, 7, 1, 9, 0)) == pytest.approx(
        sp.get_kw(datetime(2024, 7, 1, 15, 0))
    )


def test_synthetic_load_constant() -> None:
    lp = SyntheticLoad(base_kw=2.0)
    assert lp.get_kw(datetime(2024, 7, 1, 10, 0)) == 2.0
    assert lp.get_kw(datetime(2024, 7, 1, 22, 0)) == 2.0


def test_synthetic_solar_horizon() -> None:
    sp = SyntheticSolar(peak_kw=10.0)
    start, end = sp.horizon()
    # Default synthetic adapter should accept any reasonable date range
    assert start <= datetime(2024, 1, 1)
    assert end >= datetime(2030, 1, 1)


def test_protocols_are_satisfied() -> None:
    """SyntheticLoad satisfies LoadProfile, SyntheticSolar satisfies SolarProfile."""
    lp: LoadProfile = SyntheticLoad(base_kw=2.0)
    sp: SolarProfile = SyntheticSolar(peak_kw=10.0)
    assert callable(lp.get_kw)
    assert callable(sp.get_kw)
