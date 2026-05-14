"""Pecan Street load profile adapter (15-min residential smart-meter data).

Apply for a researcher account at https://www.pecanstreet.org/dataport/. Once
approved, use scripts/fetch_data.py (Task 24) to download a per-house table
into data/pecan_street/, then reference the CSV path + dataid from your
scenario YAML.

This Phase 1 implementation ships against an in-repo CSV fixture; integration
into the engine lands in Task 23.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

_MAX_GAP = timedelta(hours=1)


class PecanStreetLoad:
    """Load-kW lookup against a Pecan Street 15-min CSV table.

    Forward-fills gaps up to 1 hour; raises ValueError on longer gaps so
    bad data fails loud rather than silently fudging.
    """

    def __init__(self, csv_path: Path | str, dataid: int) -> None:
        df = pd.read_csv(csv_path, parse_dates=["local_15min"])
        df = df[df["dataid"] == dataid].sort_values("local_15min").reset_index(drop=True)
        if df.empty:
            raise ValueError(f"no rows for dataid={dataid} in {csv_path}")
        self.df = df.set_index("local_15min")
        self.dataid = dataid

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
        return float(self.df.iloc[idx]["use"])

    def horizon(self) -> tuple[datetime, datetime]:
        return (self.df.index[0].to_pydatetime(), self.df.index[-1].to_pydatetime())
