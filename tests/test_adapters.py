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
from sim.adapters.resstock import ResStockLoad

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


def test_nrel_solar_deterministic_under_call_order() -> None:
    """Same (seed, t) -> same noise, regardless of what other timestamps have been
    queried first. This is stronger than streaming-RNG determinism (review fix C2)."""
    sp1 = NRELSolar(csv_path=_FIXTURES / "nrel_sample.csv", seed=42)
    sp2 = NRELSolar(csv_path=_FIXTURES / "nrel_sample.csv", seed=42)
    t = datetime(2024, 7, 1, 9, 0)
    # sp1: query t once.
    val1 = sp1.get_kw(t)
    # sp2: query other timestamps first, then t.
    sp2.get_kw(datetime(2024, 7, 1, 7, 0))
    sp2.get_kw(datetime(2024, 7, 1, 8, 0))
    sp2.get_kw(datetime(2024, 7, 1, 11, 0))
    val2 = sp2.get_kw(t)
    assert val1 == val2


def test_resstock_load_reads_fixture() -> None:
    """ResStock files store energy-per-15-min-interval in kWh; adapter converts to kW."""
    lp = ResStockLoad(path=_FIXTURES / "resstock_sample.csv", dt_hours=0.25)
    # 0.31 kWh per 15-min -> 1.24 kW
    assert lp.get_kw(datetime(2024, 7, 1, 0, 0)) == pytest.approx(1.24, abs=1e-6)
    # Forward-fill within the gap tolerance.
    assert lp.get_kw(datetime(2024, 7, 1, 0, 5)) == pytest.approx(1.24, abs=1e-6)


def test_resstock_load_crashes_on_long_gap() -> None:
    lp = ResStockLoad(path=_FIXTURES / "resstock_sample.csv", dt_hours=0.25)
    # Fixture ends at 01:45; querying 04:00 = 2 h 15 min later, exceeds 1 h max gap.
    with pytest.raises(ValueError, match="gap"):
        lp.get_kw(datetime(2024, 7, 1, 4, 0))


def test_resstock_load_rejects_unknown_file_type(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.txt"
    bogus.write_text("hello")
    with pytest.raises(ValueError, match="unsupported file extension"):
        ResStockLoad(path=bogus, dt_hours=0.25)


_FIXTURE_NREL = Path(__file__).parent / "fixtures" / "nrel_sample.csv"


def _utc_shaped_csv(tmp_path: Path) -> Path:
    """A day of hourly GHI whose peak sits at 18:00 — the shape of NSRDB data
    fetched with utc=true for a US-central site (solar noon ~18:30 UTC)."""
    rows = ["Year,Month,Day,Hour,Minute,GHI"]
    for hour in range(24):
        ghi = max(0, 900 - 120 * abs(hour - 18))
        rows.append(f"2018,7,15,{hour},0,{ghi}")
    p = tmp_path / "utc_shaped.csv"
    p.write_text("\n".join(rows) + "\n")
    return p


def test_nrel_solar_rejects_utc_shaped_data_without_offset(tmp_path: Path) -> None:
    """Peak GHI outside 10:00-16:00 local means the CSV is on the wrong clock
    (the 2026-07-06 bug: UTC data consumed as naive local time shifted every
    real-data scenario's solar by ~+6 h). Must fail loudly, not run wrong."""
    with pytest.raises(ValueError, match=r"UTC"):
        NRELSolar(csv_path=_utc_shaped_csv(tmp_path), seed=1)


def test_nrel_solar_tz_offset_realigns_utc_data(tmp_path: Path) -> None:
    """tz_offset_hours=-6 shifts UTC timestamps to US-central standard time."""
    solar = NRELSolar(csv_path=_utc_shaped_csv(tmp_path), seed=1, tz_offset_hours=-6.0)
    assert solar.get_kw(datetime(2018, 7, 15, 12, 0)) > 0.5
    assert solar.get_kw(datetime(2018, 7, 15, 3, 0)) == 0.0


def test_nrel_noise_is_timezone_independent() -> None:
    """The per-(seed, t) noise draw must not depend on the machine's TZ env.

    Pre-2026-07-06 the seed came from naive datetime.timestamp(), which Python
    interprets in the machine's local timezone — same code, same seed, same
    scenario gave different numbers on differently-configured machines.
    """
    import os
    import time

    t = datetime(2024, 7, 1, 9, 30)
    old_tz = os.environ.get("TZ")
    try:
        os.environ["TZ"] = "UTC"
        time.tzset()
        kw_utc = NRELSolar(csv_path=_FIXTURE_NREL, seed=7).get_kw(t)
        os.environ["TZ"] = "America/Chicago"
        time.tzset()
        kw_chicago = NRELSolar(csv_path=_FIXTURE_NREL, seed=7).get_kw(t)
    finally:
        if old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old_tz
        time.tzset()
    assert kw_utc == kw_chicago


def test_nrel_noise_pinned_cross_platform_constant() -> None:
    """Hardcoded expected value for a fixed (seed, t): any platform- or
    TZ-dependence in the noise seeding fails this in CI on other machines."""
    solar = NRELSolar(csv_path=_FIXTURE_NREL, seed=7)
    assert solar.get_kw(datetime(2024, 7, 1, 9, 30)) == pytest.approx(
        0.45454901928641145, rel=1e-12
    )


def test_resstock_kw_conversion_uses_native_interval_not_scenario_dt() -> None:
    """ResStock kWh-per-interval must be divided by the DATA's interval (15 min),
    not the simulator tick length — pre-2026-07-06 a dt=0.5 scenario silently
    halved every real load."""
    at = datetime(2024, 7, 1, 0, 10)
    kw_at_quarter = ResStockLoad(path=_FIXTURES / "resstock_sample.csv", dt_hours=0.25).get_kw(at)
    kw_at_half = ResStockLoad(path=_FIXTURES / "resstock_sample.csv", dt_hours=0.5).get_kw(at)
    assert kw_at_quarter == pytest.approx(0.31 / 0.25, abs=1e-12)
    assert kw_at_half == kw_at_quarter


def test_resstock_period_ending_timestamps_are_realigned() -> None:
    """Real ResStock files stamp each row with the interval END (first row
    00:15 covering 00:00-00:15). The adapter must shift them back so lookups
    at 00:00 return the first interval instead of crashing/lagging one tick."""
    lp = ResStockLoad(path=_FIXTURES / "resstock_period_ending_sample.csv", dt_hours=0.25)
    assert lp.get_kw(datetime(2024, 7, 1, 0, 0)) == pytest.approx(0.31 / 0.25, abs=1e-12)
    assert lp.horizon()[0] == datetime(2024, 7, 1, 0, 0)
    # And it must agree everywhere with the period-beginning twin fixture.
    twin = ResStockLoad(path=_FIXTURES / "resstock_sample.csv", dt_hours=0.25)
    for minutes in (0, 10, 15, 40):
        t = datetime(2024, 7, 1, 0, minutes)
        assert lp.get_kw(t) == twin.get_kw(t)
