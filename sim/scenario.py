"""Scenario configuration: dataclasses + YAML loader."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from sim.agents.failure_modes import FailureModeConfig


@dataclass(frozen=True, slots=True)
class OutageWindow:
    """A single contiguous outage affecting some subset of houses."""

    start: datetime
    end: datetime
    affected_houses: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError(f"OutageWindow end before start: {self.start} -> {self.end}")


@dataclass(frozen=True, slots=True)
class Scenario:
    """Full configuration for one simulation run."""

    scenario_id: str
    start: datetime
    end: datetime
    dt_hours: float
    seed: int
    rows: int
    cols: int
    bus_max_kw: float
    bus_loss_factor: float
    strategy: str
    data_source: str
    household_sampling: dict[str, Any]
    outages: tuple[OutageWindow, ...] = field(default_factory=tuple)
    data_paths: dict[str, str] = field(default_factory=dict)
    house_dataids: tuple[int, ...] = field(default_factory=tuple)
    # For data_source=resstock: per-house ResStock filename (e.g. "bldg0000123-up00.parquet")
    # under data_paths["load_dir"]. Strings, not ints, because ResStock IDs are zero-padded.
    house_building_files: tuple[str, ...] = field(default_factory=tuple)
    affiliations: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)
    # Phase 2 additions (purely additive — defaults preserve Phase 1.x behavior):
    failure_modes: FailureModeConfig = field(default_factory=FailureModeConfig)
    llm: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.dt_hours <= 0:
            raise ValueError(f"dt_hours must be positive, got {self.dt_hours}")
        if self.end <= self.start:
            raise ValueError(f"end before start: {self.start} -> {self.end}")
        if self.rows <= 0 or self.cols <= 0:
            raise ValueError(f"rows and cols must be positive: rows={self.rows} cols={self.cols}")

    def timesteps(self) -> Iterator[datetime]:
        t = self.start
        dt = timedelta(hours=self.dt_hours)
        while t < self.end:
            yield t
            t += dt

    def grid_status_at(self, t: datetime, house_id: str) -> bool:
        """True if the house is grid-connected at time t (no active outage covers it)."""
        for w in self.outages:
            if w.start <= t < w.end and house_id in w.affected_houses:
                return False
        return True


def load_scenario(path: Path | str) -> Scenario:
    """Read a scenario YAML file and validate the time bounds."""
    p = Path(path)
    with p.open() as f:
        raw = yaml.safe_load(f)

    start = datetime.fromisoformat(raw["start"])
    end = datetime.fromisoformat(raw["end"])
    if end <= start:
        raise ValueError(f"end before start: {start} -> {end}")

    outages: list[OutageWindow] = []
    for o in raw.get("outages", []) or []:
        outages.append(
            OutageWindow(
                start=datetime.fromisoformat(o["start"]),
                end=datetime.fromisoformat(o["end"]),
                affected_houses=tuple(o.get("affected_houses", [])),
            )
        )

    rows_i = int(raw["rows"])
    cols_i = int(raw["cols"])
    valid_ids = {f"r{r}c{c}" for r in range(rows_i) for c in range(cols_i)}
    affiliations: dict[str, dict[str, tuple[str, ...]]] = {}
    for atype, groups in (raw.get("affiliations", {}) or {}).items():
        parsed_groups: dict[str, tuple[str, ...]] = {}
        for gid, members in (groups or {}).items():
            members_t = tuple(str(m) for m in members)
            for m in members_t:
                if m not in valid_ids:
                    raise ValueError(
                        f"affiliations[{atype!r}][{gid!r}] references unknown house {m!r} "
                        f"(grid is {rows_i}x{cols_i})"
                    )
            parsed_groups[str(gid)] = members_t
        affiliations[str(atype)] = parsed_groups

    return Scenario(
        scenario_id=raw["scenario_id"],
        start=start,
        end=end,
        dt_hours=float(raw["dt_hours"]),
        seed=int(raw["seed"]),
        rows=int(raw["rows"]),
        cols=int(raw["cols"]),
        bus_max_kw=float(raw["bus_max_kw"]),
        bus_loss_factor=float(raw.get("bus_loss_factor", 0.05)),
        strategy=str(raw["strategy"]),
        data_source=str(raw["data_source"]),
        household_sampling=dict(raw["household_sampling"]),
        outages=tuple(outages),
        data_paths=dict(raw.get("data_paths", {}) or {}),
        house_dataids=tuple(int(x) for x in (raw.get("house_dataids", []) or [])),
        house_building_files=tuple(str(x) for x in (raw.get("house_building_files", []) or [])),
        affiliations=affiliations,
        failure_modes=FailureModeConfig.from_dict(raw.get("failure_modes")),
        llm=dict(raw.get("llm", {}) or {}),
    )
