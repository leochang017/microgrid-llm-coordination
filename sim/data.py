"""Data adapters. Phase 1 ships only the synthetic adapter; real adapters land in Task 21+."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Protocol


class LoadProfile(Protocol):
    """Per-household load demand in kW at a point in time."""

    def get_kw(self, t: datetime) -> float: ...

    def horizon(self) -> tuple[datetime, datetime]: ...


class SolarProfile(Protocol):
    """Per-household solar generation in kW at a point in time (pre-PV-size scaling)."""

    def get_kw(self, t: datetime) -> float: ...

    def horizon(self) -> tuple[datetime, datetime]: ...


class SyntheticSolar:
    """Half-sinusoid solar curve, zero outside [sunrise, sunset]."""

    def __init__(self, peak_kw: float, sunrise_hour: int = 6, sunset_hour: int = 18) -> None:
        self.peak_kw = peak_kw
        self.sunrise_hour = sunrise_hour
        self.sunset_hour = sunset_hour

    def get_kw(self, t: datetime) -> float:
        hour = t.hour + t.minute / 60.0
        if hour < self.sunrise_hour or hour > self.sunset_hour:
            return 0.0
        # Half-sine peaking at solar noon
        frac = (hour - self.sunrise_hour) / (self.sunset_hour - self.sunrise_hour)
        return self.peak_kw * math.sin(math.pi * frac)

    def horizon(self) -> tuple[datetime, datetime]:
        return (datetime(2000, 1, 1), datetime(2099, 12, 31))


class SyntheticLoad:
    """Constant load."""

    def __init__(self, base_kw: float) -> None:
        self.base_kw = base_kw

    def get_kw(self, t: datetime) -> float:
        return self.base_kw

    def horizon(self) -> tuple[datetime, datetime]:
        return (datetime(2000, 1, 1), datetime(2099, 12, 31))
