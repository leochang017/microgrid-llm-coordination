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
    ) -> None:
        df = pd.read_csv(csv_path)
        df["datetime"] = pd.to_datetime(df[["Year", "Month", "Day", "Hour", "Minute"]])
        df = df.sort_values("datetime").reset_index(drop=True)
        self.df = df.set_index("datetime")
        self.derate = derate
        self.noise_std = noise_std
        self.seed = seed

    def _noise(self, t: datetime) -> float:
        # Seed a fresh Generator from a stable mix of (self.seed, t). Using
        # numpy's SeedSequence so two ints combine into a uniform-quality seed.
        ss = np.random.SeedSequence([self.seed, int(t.timestamp())])
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
