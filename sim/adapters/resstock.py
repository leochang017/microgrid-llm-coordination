"""NREL ResStock residential building load profile adapter.

ResStock (https://resstock.nrel.gov/) ships 15-min electricity consumption time
series for simulated US homes, modeled from real building characteristics
(size, age, climate zone, occupancy, HVAC type). Each file represents ONE
building for ONE year (35,040 rows = 365 * 96).

Format:
  - Native: Parquet, columns include `timestamp` (or `time`) and
    `out.electricity.total.energy_consumption` (kWh per 15-min interval).
  - Also reads CSV with the same column names — useful for fixtures.
  - Data is in **energy per interval (kWh)**, not power (kW). The adapter
    converts using the scenario's `dt_hours` so callers always see kW.

Public, redistributable, no signup. Download files from the OEDI Data Lake:
  https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/
  end-use-load-profiles-for-us-building-stock/resstock_amy2018_release_2/
  timeseries_individual_buildings/by_state/upgrade=0/state={STATE}/

See scripts/fetch_data.py for a helper that downloads a handful of files
for a chosen state.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

_MAX_GAP = timedelta(hours=1)
_ENERGY_COL = "out.electricity.total.energy_consumption"
_TIME_COLS = ("timestamp", "time")


class ResStockLoad:
    """Load-kW lookup against a single ResStock building's 15-min time series.

    Parameters:
        path: A .csv or .parquet file. The path's extension determines the reader.
        dt_hours: The simulator's tick length. Used to convert ResStock's
            per-interval kWh to instantaneous kW. ResStock is natively 15-min
            (dt=0.25), but the adapter doesn't enforce that — caller's
            responsibility to pass the right value.

    `get_kw(t)` returns kW at the most recent sample at or before `t`, forward-
    filling up to 1 h. Longer gaps raise — data must be clean.
    """

    def __init__(self, path: Path | str, *, dt_hours: float) -> None:
        p = Path(path)
        if p.suffix == ".csv":
            df = pd.read_csv(p)
        elif p.suffix == ".parquet":
            df = pd.read_parquet(p)
        else:
            raise ValueError(f"unsupported file extension {p.suffix!r}; want .csv or .parquet")

        # ResStock variants use either "timestamp" or "time" as the index column.
        time_col = next((c for c in _TIME_COLS if c in df.columns), None)
        if time_col is None:
            raise ValueError(
                f"{p}: missing a timestamp column "
                f"(expected one of {_TIME_COLS}; got {list(df.columns)})"
            )
        df[time_col] = pd.to_datetime(df[time_col])
        df = df.sort_values(time_col).reset_index(drop=True)

        if _ENERGY_COL not in df.columns:
            raise ValueError(f"{p}: missing column {_ENERGY_COL!r}; got {list(df.columns)}")

        self.df = df.set_index(time_col)
        self.path = p
        self.dt_hours = dt_hours

    def get_kw(self, t: datetime) -> float:
        idx = self.df.index.searchsorted(t, side="right") - 1
        if idx < 0:
            raise ValueError(f"t={t} before first sample ({self.df.index[0]})")
        last_t = self.df.index[idx]
        if t - last_t > _MAX_GAP:
            raise ValueError(
                f"gap from {last_t} to {t} ({t - last_t}) exceeds max {_MAX_GAP}; "
                "data needs cleaning"
            )
        kwh_in_interval = float(self.df.iloc[idx][_ENERGY_COL])
        # Convert kWh-per-interval to instantaneous kW.
        return kwh_in_interval / self.dt_hours

    def horizon(self) -> tuple[datetime, datetime]:
        return (self.df.index[0].to_pydatetime(), self.df.index[-1].to_pydatetime())
