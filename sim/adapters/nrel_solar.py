"""NREL NSRDB solar irradiance adapter.

NREL's NSRDB provides hourly GHI (global horizontal irradiance, W/m^2) for any
location. This adapter converts GHI to per-kW-peak generation using the simple
approximation:
    kw_per_kw_peak = (GHI / 1000) * derate

with a `derate` factor (default 0.85) accounting for inverter + module +
soiling + wiring losses. Sub-hourly ticks are linearly interpolated between
the two surrounding hourly samples plus a small seeded multiplicative noise
term (default sigma=0.02). Same seed -> byte-identical noise sequence per
get_kw call sequence.

Get an API key at https://developer.nrel.gov/signup/; scripts/fetch_data.py
(Task 24) downloads a year of hourly data for a given lat/lon.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


class NRELSolar:
    """Hourly NSRDB irradiance -> per-kW-peak solar generation at any timestamp.

    Determinism: the noise term is drawn from a per-call RNG seeded by a hash of
    (self.seed, t). Same (seed, t) -> same noise, regardless of call order. This
    is stronger than a streaming RNG, which would couple the noise sequence to
    the order calls happen to arrive in.
    """

    def __init__(
        self,
        csv_path: Path | str,
        *,
        seed: int,
        derate: float = 0.85,
        noise_std: float = 0.02,
        tz_offset_hours: float = 0.0,
    ) -> None:
        """tz_offset_hours shifts the CSV's clock onto the simulation's local
        clock. NSRDB files fetched by scripts/fetch_data.py are in UTC, so a
        US-central site needs tz_offset_hours=-6 (set `solar_tz_offset_hours`
        in the scenario YAML). Loading validates that the resulting daily GHI
        peak falls near local noon and refuses to run otherwise — consuming
        UTC data as local time shifts the whole solar curve ~+6 h and silently
        inverts day and night (the 2026-07-06 bug behind every pre-Phase-2.9
        real-data result).
        """
        df = pd.read_csv(csv_path)
        df["datetime"] = pd.to_datetime(df[["Year", "Month", "Day", "Hour", "Minute"]])
        if tz_offset_hours:
            df["datetime"] = df["datetime"] + pd.Timedelta(hours=tz_offset_hours)
        df = df.sort_values("datetime").reset_index(drop=True)
        self.df = df.set_index("datetime")
        self.derate = derate
        self.noise_std = noise_std
        self.seed = seed
        self._validate_solar_noon(csv_path)

    def _validate_solar_noon(self, csv_path: Path | str) -> None:
        ghi_by_hour = self.df.groupby(self.df.index.hour)["GHI"].mean()
        if float(ghi_by_hour.max()) <= 0.0:
            return  # degenerate all-dark frame; nothing to validate
        peak_hour = int(ghi_by_hour.idxmax())
        if not 10 <= peak_hour <= 16:
            raise ValueError(
                f"{csv_path}: mean GHI peaks at hour {peak_hour:02d}:00, outside "
                "10:00-16:00 — the file is probably on a UTC clock (NSRDB fetched "
                "with utc=true). Set the scenario's solar_tz_offset_hours (e.g. -6 "
                "for US central standard time) so timestamps land on local time."
            )

    def _noise(self, t: datetime) -> float:
        # Seed a fresh Generator from a stable mix of (self.seed, t). The time
        # component is derived from calendar fields, NOT t.timestamp() — a
        # naive datetime's timestamp depends on the machine's TZ setting,
        # which broke byte-identical reproducibility across machines.
        ss = np.random.SeedSequence([self.seed, int(t.strftime("%Y%m%d%H%M"))])
        rng = np.random.default_rng(ss)
        return float(rng.normal(0.0, self.noise_std))

    def get_kw(self, t: datetime) -> float:
        idx = self.df.index.searchsorted(t, side="right") - 1
        if idx < 0:
            return 0.0
        t0 = self.df.index[idx]
        if idx + 1 >= len(self.df):
            ghi = float(self.df.iloc[idx]["GHI"])
        else:
            t1 = self.df.index[idx + 1]
            g0 = float(self.df.iloc[idx]["GHI"])
            g1 = float(self.df.iloc[idx + 1]["GHI"])
            frac = (t - t0).total_seconds() / (t1 - t0).total_seconds()
            ghi = g0 + frac * (g1 - g0)
        kw_per_peak = (ghi / 1000.0) * self.derate
        if kw_per_peak > 0:
            kw_per_peak *= 1.0 + self._noise(t)
        return max(0.0, kw_per_peak)

    def horizon(self) -> tuple[datetime, datetime]:
        return (self.df.index[0].to_pydatetime(), self.df.index[-1].to_pydatetime())
