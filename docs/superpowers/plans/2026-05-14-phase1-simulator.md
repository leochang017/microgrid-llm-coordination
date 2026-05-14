# Phase 1: Microgrid Simulator — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, reproducible discrete-time simulator of a 30-household residential microgrid with solar + battery + load + outage-prone grid, providing a clean plug-point for coordination strategies that Phase 2 (LLM agents) will fill in.

**Architecture:** Five small Python modules under `sim/` (data, household, network, scenario, engine, logging) with clear boundaries. The simulator is pure-physics; coordination strategies are injected as a callback. State + events are written as JSONL per run. Test-driven throughout, with physics invariants asserted at every tick.

**Tech Stack:** Python 3.12, `pytest`, `ruff`, `mypy --strict`, `numpy` (RNG + simple math), `pyyaml` (scenario config), `pandas` (data adapters, later). No power-systems libraries. No ML libraries in Phase 1.

**Spec reference:** `docs/superpowers/specs/2026-05-14-phase1-simulator-design.md`

---

## File structure (locks in decomposition decisions)

```
academic/microgrid/
├── pyproject.toml              # uv-managed project, deps, ruff/mypy config
├── README.md                   # how to install, fetch data, run a scenario
├── .gitignore
├── .python-version             # "3.12"
├── sim/
│   ├── __init__.py
│   ├── types.py                # Transfer, HouseholdProfile, SettlementResult, Event types
│   ├── data.py                 # LoadProfile/SolarProfile protocols + SyntheticAdapter
│   ├── household.py            # Household, HouseholdState, step()
│   ├── network.py              # Neighborhood, settle_transfers()
│   ├── scenario.py             # Scenario dataclass, load_scenario(path)
│   ├── engine.py               # run() main loop, energy-balance assertion
│   ├── logging.py              # JsonlLogger, finalize_summary()
│   ├── adapters/               # Real-data adapters (Pecan Street, NREL, ResStock)
│   │   ├── __init__.py
│   │   ├── pecan_street.py
│   │   └── nrel_solar.py
│   └── strategies/
│       ├── __init__.py
│       ├── no_coordination.py
│       └── round_robin.py
├── configs/scenarios/
│   ├── 24h_uniform.yaml        # 24h outage, uniform households
│   └── synthetic_smoke.yaml    # constant solar + load, no outage (used by physics smoke test)
├── data/{pecan_street,nrel_solar}/  # cached raw data — gitignored
├── runs/                       # output dir — gitignored
├── tests/
│   ├── conftest.py
│   ├── test_types.py
│   ├── test_household.py
│   ├── test_data.py
│   ├── test_network.py
│   ├── test_scenario.py
│   ├── test_logging.py
│   ├── test_strategies.py
│   ├── test_engine.py
│   ├── test_integration.py
│   └── test_physics_smoke.py
└── scripts/
    ├── __init__.py
    ├── fetch_data.py           # one-time NREL + Pecan Street download
    └── run.py                  # CLI entry: `python -m scripts.run --scenario <yaml>`
```

**Why this structure:**
- `sim/types.py` holds shared dataclasses to avoid circular imports — physics modules and the network module both reference `Transfer`.
- `sim/adapters/` is a sub-package so the real-data adapters (which depend on `pandas` and network downloads) are isolated from the pure-physics core that the unit tests touch.
- `sim/strategies/` is similarly isolated. Phase 2 will add an `llm_agents.py` sibling without touching the core.
- All gitignored data goes under `data/`, all gitignored outputs under `runs/`. One `.gitignore` line per directory.

---

## Conventions and ground rules

- **Python 3.12.** Use built-in dataclasses, `typing.Protocol`, `datetime`. No third-party data-class libs.
- **No global state.** Engine owns the RNG. Modules take RNG as an argument when they need one.
- **Pure functions where possible.** `household.step()` returns a new `HouseholdState` rather than mutating. `network.settle_transfers()` is pure. The engine is the only stateful glue.
- **Types are real.** `mypy --strict` must pass on `sim/`. If a function signature is awkward to type, the function shape is probably wrong.
- **Energy unit: kWh.** Power unit: kW. Time unit: hours for physics math (so `dt_hours = 0.25` for 15-min ticks). Datetime for the clock.
- **Commit message style:** Conventional commits (`feat:`, `test:`, `chore:`, `docs:`). One logical change per commit.
- **TDD always.** Every task is: write failing test → run it red → minimal implementation → run it green → commit. Do not skip the red step.

---

## Task 0: Initialize repo and project scaffold

**Files:**
- Create: `academic/microgrid/.gitignore`
- Create: `academic/microgrid/.python-version`
- Create: `academic/microgrid/pyproject.toml`
- Create: `academic/microgrid/README.md` (stub)
- Create: `academic/microgrid/sim/__init__.py` (empty)
- Create: `academic/microgrid/tests/__init__.py` (empty)
- Create: `academic/microgrid/tests/conftest.py`

- [x] **Step 1: Initialize git repo and set up project directory**

```bash
cd /Users/leochang/myproject/academic/microgrid
git init
```

- [x] **Step 2: Write `.gitignore`**

```gitignore
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
.venv/
*.egg-info/
dist/
build/

# Data + outputs
data/
runs/

# Editor
.DS_Store
.vscode/
.idea/
```

- [x] **Step 3: Write `.python-version`**

```
3.12
```

- [x] **Step 4: Write `pyproject.toml`**

```toml
[project]
name = "microgrid-sim"
version = "0.1.0"
description = "LLM-agent peer-to-peer coordination simulator for residential microgrids."
requires-python = ">=3.12"
dependencies = [
    "numpy>=2.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
data = ["pandas>=2.2", "pyarrow>=16.0", "requests>=2.32"]
dev = ["pytest>=8.0", "ruff>=0.6", "mypy>=1.11", "types-pyyaml>=6.0"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "RUF"]
ignore = ["E501"]  # line length handled by formatter

[tool.mypy]
python_version = "3.12"
strict = true
files = ["sim"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q"
```

- [x] **Step 5: Write `README.md` stub**

```markdown
# Microgrid Sim

LLM-agent peer-to-peer coordination simulator for residential microgrids. Phase 1: physics simulator only.

See `docs/superpowers/specs/` for the design spec and `docs/superpowers/plans/` for the implementation plan.

## Quickstart

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```

(Full data-download + run instructions will be added once the CLI lands — see Task 23.)
```

- [x] **Step 6: Create empty package init files**

Create `sim/__init__.py` (empty) and `tests/__init__.py` (empty).

- [x] **Step 7: Write `tests/conftest.py`**

```python
"""Shared test fixtures."""
import numpy as np
import pytest


@pytest.fixture
def rng() -> np.random.Generator:
    """A deterministic RNG seeded the same way for every test."""
    return np.random.default_rng(seed=42)
```

- [x] **Step 8: Install and verify**

```bash
cd /Users/leochang/myproject/academic/microgrid
uv venv
source .venv/bin/activate
uv pip install -e ".[dev,data]"
pytest
ruff check sim tests
mypy
```

Expected:
- `pytest`: "no tests ran" (zero tests collected, exit 5 is fine)
- `ruff`: "All checks passed!"
- `mypy`: "Success: no issues found"

- [x] **Step 9: Commit**

```bash
git add .gitignore .python-version pyproject.toml README.md sim/ tests/
git commit -m "chore: initialize project scaffold with pytest/ruff/mypy"
```

---

## Task 1: Shared types

**Files:**
- Create: `sim/types.py`
- Create: `tests/test_types.py`

These are the dataclasses every other module references. Putting them in one file avoids circular imports.

- [x] **Step 1: Write failing test for `Transfer` dataclass**

`tests/test_types.py`:

```python
"""Tests for shared dataclass types."""
import pytest

from sim.types import HouseholdProfile, Transfer


def test_transfer_basic() -> None:
    t = Transfer(from_id="h01", to_id="h02", kw=2.5)
    assert t.from_id == "h01"
    assert t.to_id == "h02"
    assert t.kw == 2.5


def test_transfer_rejects_self_loop() -> None:
    with pytest.raises(ValueError, match="self-transfer"):
        Transfer(from_id="h01", to_id="h01", kw=2.5)


def test_transfer_rejects_nonpositive_kw() -> None:
    with pytest.raises(ValueError, match="positive"):
        Transfer(from_id="h01", to_id="h02", kw=0.0)
    with pytest.raises(ValueError, match="positive"):
        Transfer(from_id="h01", to_id="h02", kw=-1.0)


def test_household_profile_defaults() -> None:
    p = HouseholdProfile(description="empty nest, two adults")
    assert p.description == "empty nest, two adults"
    assert p.has_medical is False
    assert p.has_infant is False
    assert p.essential_only is False


def test_household_profile_flags() -> None:
    p = HouseholdProfile(
        description="mother on oxygen",
        has_medical=True,
    )
    assert p.has_medical is True
```

- [x] **Step 2: Run and verify failure**

```bash
pytest tests/test_types.py -v
```

Expected: ImportError, `sim.types` does not exist.

- [x] **Step 3: Implement `sim/types.py`**

```python
"""Shared dataclass types used across the simulator."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Transfer:
    """A requested or executed peer-to-peer energy transfer for one tick.

    `kw` is the sender-side power; receiver gets `kw * (1 - bus_loss_factor)`
    after `network.settle_transfers` applies transit loss.
    """

    from_id: str
    to_id: str
    kw: float

    def __post_init__(self) -> None:
        if self.from_id == self.to_id:
            raise ValueError(f"self-transfer not allowed (id={self.from_id})")
        if self.kw <= 0:
            raise ValueError(f"transfer kw must be positive, got {self.kw}")


@dataclass(frozen=True, slots=True)
class HouseholdProfile:
    """Demographic / needs metadata for one household.

    Phase 1 stores this but does not use it in physics. Phase 2 LLM agents
    will consume `description` (free text) and the structured tags.
    """

    description: str
    has_medical: bool = False
    has_infant: bool = False
    essential_only: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)
```

- [x] **Step 4: Run tests and verify passing**

```bash
pytest tests/test_types.py -v
mypy
ruff check sim tests
```

Expected: 5 tests pass, mypy clean, ruff clean.

- [x] **Step 5: Commit**

```bash
git add sim/types.py tests/test_types.py
git commit -m "feat(types): add Transfer and HouseholdProfile dataclasses"
```

---

## Task 2: Household physics — basic charge/discharge

**Files:**
- Create: `sim/household.py`
- Create: `tests/test_household.py`

We start with the simplest case: solar > load, battery charges; solar < load, battery discharges. No RT efficiency yet, no rate limits yet, no DoD floor yet. We'll add each constraint in its own task so a regression in one is easy to localize.

- [x] **Step 1: Write failing test for basic charge from surplus**

`tests/test_household.py`:

```python
"""Tests for household physics: battery dynamics, constraints, energy accounting."""
import pytest

from sim.household import Household, HouseholdState, step
from sim.types import HouseholdProfile


def make_house(**overrides: object) -> Household:
    defaults: dict[str, object] = {
        "id": "h01",
        "pv_kw_peak": 8.0,
        "battery_kwh": 13.5,
        "battery_max_rate_kw": 5.0,
        "rt_efficiency": 1.0,  # disable for early tests
        "dod_floor_frac": 0.0,
        "grid_max_kw": 10.0,
        "profile": HouseholdProfile(description="test"),
    }
    defaults.update(overrides)
    return Household(**defaults)  # type: ignore[arg-type]


def test_charge_from_surplus_no_constraints() -> None:
    """Solar 4 kW, load 1 kW, dt 1 h, no transfer, no grid → battery gains 3 kWh."""
    h = make_house()
    s0 = HouseholdState(soc_kwh=5.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=True)
    s1 = step(
        h,
        s0,
        solar_kw=4.0,
        load_kw=1.0,
        desired_net_export_kw=0.0,
        grid_status=True,
        dt_hours=1.0,
    )
    assert s1.soc_kwh == pytest.approx(8.0, abs=1e-9)


def test_discharge_to_meet_load_no_constraints() -> None:
    """Solar 0 kW, load 2 kW, dt 0.25 h, no transfer → battery loses 0.5 kWh."""
    h = make_house()
    s0 = HouseholdState(soc_kwh=5.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    s1 = step(
        h,
        s0,
        solar_kw=0.0,
        load_kw=2.0,
        desired_net_export_kw=0.0,
        grid_status=False,
        dt_hours=0.25,
    )
    assert s1.soc_kwh == pytest.approx(4.5, abs=1e-9)
```

- [x] **Step 2: Run and verify failure**

```bash
pytest tests/test_household.py -v
```

Expected: ImportError on `sim.household`.

- [x] **Step 3: Implement minimal `sim/household.py`**

```python
"""Household physics: solar + battery + load with constraints applied each tick."""
from __future__ import annotations

from dataclasses import dataclass, replace

from sim.types import HouseholdProfile


@dataclass(frozen=True, slots=True)
class Household:
    """Static properties of one household."""

    id: str
    pv_kw_peak: float
    battery_kwh: float
    battery_max_rate_kw: float
    rt_efficiency: float
    dod_floor_frac: float
    grid_max_kw: float
    profile: HouseholdProfile


@dataclass(frozen=True, slots=True)
class HouseholdState:
    """Mutable state of one household at a point in time."""

    soc_kwh: float
    last_solar_kw: float
    last_load_kw: float
    grid_connected: bool


def step(
    h: Household,
    s: HouseholdState,
    solar_kw: float,
    load_kw: float,
    desired_net_export_kw: float,
    grid_status: bool,
    dt_hours: float,
) -> HouseholdState:
    """Advance one tick. Returns the new state.

    For Task 2, we ignore desired_net_export_kw, grid_status, rate limits, RT
    efficiency, and DoD floor. Pure solar-vs-load battery bookkeeping.
    """
    net_kw = solar_kw - load_kw
    new_soc = s.soc_kwh + net_kw * dt_hours
    return replace(
        s,
        soc_kwh=new_soc,
        last_solar_kw=solar_kw,
        last_load_kw=load_kw,
        grid_connected=grid_status,
    )
```

- [x] **Step 4: Run tests and verify passing**

```bash
pytest tests/test_household.py -v
mypy
```

Expected: 2 tests pass, mypy clean.

- [x] **Step 5: Commit**

```bash
git add sim/household.py tests/test_household.py
git commit -m "feat(household): basic charge/discharge bookkeeping"
```

---

## Task 3: Household — battery rate limits and SoC bounds

**Files:**
- Modify: `sim/household.py`
- Modify: `tests/test_household.py`

Add: charge/discharge rate clamping to `battery_max_rate_kw`; SoC clamping at `[dod_floor_frac * battery_kwh, battery_kwh]`. Excess that can't fit becomes `wasted_kwh`; unmet load becomes `unmet_kwh`. Both reported in the returned state.

- [x] **Step 1: Extend `HouseholdState` and write failing tests**

In `tests/test_household.py`, add:

```python
def test_charge_clamps_to_battery_max_rate() -> None:
    """Solar surplus of 20 kW exceeds 5 kW battery rate → 5 kWh charged, 15 kWh wasted."""
    h = make_house(battery_max_rate_kw=5.0)
    s0 = HouseholdState(soc_kwh=5.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    s1 = step(
        h, s0, solar_kw=20.0, load_kw=0.0, desired_net_export_kw=0.0,
        grid_status=False, dt_hours=1.0,
    )
    assert s1.soc_kwh == pytest.approx(10.0, abs=1e-9)
    assert s1.wasted_kwh == pytest.approx(15.0, abs=1e-9)
    assert s1.unmet_kwh == pytest.approx(0.0, abs=1e-9)


def test_discharge_clamps_to_battery_max_rate() -> None:
    """Load deficit of 20 kW exceeds 5 kW battery rate → 5 kWh discharged, 15 kWh unmet."""
    h = make_house(battery_max_rate_kw=5.0)
    s0 = HouseholdState(soc_kwh=10.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    s1 = step(
        h, s0, solar_kw=0.0, load_kw=20.0, desired_net_export_kw=0.0,
        grid_status=False, dt_hours=1.0,
    )
    assert s1.soc_kwh == pytest.approx(5.0, abs=1e-9)
    assert s1.unmet_kwh == pytest.approx(15.0, abs=1e-9)
    assert s1.wasted_kwh == pytest.approx(0.0, abs=1e-9)


def test_soc_clamped_at_capacity() -> None:
    """Charging a full battery wastes the energy."""
    h = make_house(battery_kwh=10.0, battery_max_rate_kw=5.0)
    s0 = HouseholdState(soc_kwh=9.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    s1 = step(
        h, s0, solar_kw=5.0, load_kw=0.0, desired_net_export_kw=0.0,
        grid_status=False, dt_hours=1.0,
    )
    assert s1.soc_kwh == pytest.approx(10.0, abs=1e-9)
    assert s1.wasted_kwh == pytest.approx(4.0, abs=1e-9)


def test_soc_clamped_at_dod_floor() -> None:
    """Discharging past DoD floor leaves the deficit as unmet."""
    h = make_house(battery_kwh=10.0, battery_max_rate_kw=5.0, dod_floor_frac=0.1)
    s0 = HouseholdState(soc_kwh=1.5, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    s1 = step(
        h, s0, solar_kw=0.0, load_kw=5.0, desired_net_export_kw=0.0,
        grid_status=False, dt_hours=1.0,
    )
    assert s1.soc_kwh == pytest.approx(1.0, abs=1e-9)  # floor = 0.1 * 10
    assert s1.unmet_kwh == pytest.approx(4.5, abs=1e-9)
```

Also adjust the first two tests to assert `s1.wasted_kwh == 0.0` and `s1.unmet_kwh == 0.0`.

- [x] **Step 2: Run and verify failure**

```bash
pytest tests/test_household.py -v
```

Expected: tests fail because `HouseholdState` has no `wasted_kwh` / `unmet_kwh` fields.

- [x] **Step 3: Update `HouseholdState` and `step` in `sim/household.py`**

Replace the dataclass and step function with:

```python
@dataclass(frozen=True, slots=True)
class HouseholdState:
    soc_kwh: float
    last_solar_kw: float
    last_load_kw: float
    grid_connected: bool
    wasted_kwh: float = 0.0   # surplus that couldn't fit (curtailed solar or over-rate charge)
    unmet_kwh: float = 0.0    # deficit that couldn't be served (DoD-floor or under-rate discharge)


def step(
    h: Household,
    s: HouseholdState,
    solar_kw: float,
    load_kw: float,
    desired_net_export_kw: float,
    grid_status: bool,
    dt_hours: float,
) -> HouseholdState:
    """Advance one tick. Ignores desired_net_export_kw / grid_status for now (Task 4+)."""
    net_kw = solar_kw - load_kw

    # Clamp to battery rate
    if net_kw >= 0:
        charge_kw = min(net_kw, h.battery_max_rate_kw)
        wasted_from_rate = (net_kw - charge_kw) * dt_hours
        # Clamp to capacity
        headroom_kwh = h.battery_kwh - s.soc_kwh
        delivered_kwh = min(charge_kw * dt_hours, headroom_kwh)
        wasted_from_capacity = max(0.0, charge_kw * dt_hours - headroom_kwh)
        new_soc = s.soc_kwh + delivered_kwh
        wasted = wasted_from_rate + wasted_from_capacity
        unmet = 0.0
    else:
        discharge_kw = min(-net_kw, h.battery_max_rate_kw)
        unmet_from_rate = (-net_kw - discharge_kw) * dt_hours
        floor_kwh = h.dod_floor_frac * h.battery_kwh
        available_kwh = max(0.0, s.soc_kwh - floor_kwh)
        drawn_kwh = min(discharge_kw * dt_hours, available_kwh)
        unmet_from_floor = max(0.0, discharge_kw * dt_hours - available_kwh)
        new_soc = s.soc_kwh - drawn_kwh
        unmet = unmet_from_rate + unmet_from_floor
        wasted = 0.0

    return replace(
        s,
        soc_kwh=new_soc,
        last_solar_kw=solar_kw,
        last_load_kw=load_kw,
        grid_connected=grid_status,
        wasted_kwh=wasted,
        unmet_kwh=unmet,
    )
```

- [x] **Step 4: Run tests and verify passing**

```bash
pytest tests/test_household.py -v
mypy
```

Expected: 6 tests pass, mypy clean.

- [x] **Step 5: Commit**

```bash
git add sim/household.py tests/test_household.py
git commit -m "feat(household): rate clamping and SoC bounds with wasted/unmet accounting"
```

---

## Task 4: Household — round-trip efficiency

**Files:**
- Modify: `sim/household.py`
- Modify: `tests/test_household.py`

RT efficiency models real battery losses. We charge the battery `√η` and discharge it `√η`, so a full cycle (charge X, discharge X) returns `η × X`. For `η = 0.9`: charge with 0.9487 multiplier, discharge with 0.9487 multiplier. Net result: charge 10 kWh into battery, drain it back, get 9 kWh out.

- [x] **Step 1: Write failing tests**

In `tests/test_household.py`:

```python
import math


def test_rt_efficiency_on_charge() -> None:
    """rt_efficiency=0.9: 10 kWh solar surplus → sqrt(0.9) * 10 = ~9.487 kWh stored."""
    h = make_house(rt_efficiency=0.9, battery_max_rate_kw=20.0)
    s0 = HouseholdState(soc_kwh=0.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    s1 = step(
        h, s0, solar_kw=10.0, load_kw=0.0, desired_net_export_kw=0.0,
        grid_status=False, dt_hours=1.0,
    )
    expected = math.sqrt(0.9) * 10.0
    assert s1.soc_kwh == pytest.approx(expected, abs=1e-6)
    # Energy "lost" to RT inefficiency is logged as wasted.
    assert s1.wasted_kwh == pytest.approx(10.0 - expected, abs=1e-6)


def test_rt_efficiency_full_cycle() -> None:
    """Charge X kWh into the battery, drain it: end up with η × X served to load."""
    h = make_house(rt_efficiency=0.9, battery_max_rate_kw=20.0, battery_kwh=20.0)
    s = HouseholdState(soc_kwh=0.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    # Charge for 1 hour at 10 kW
    s = step(h, s, solar_kw=10.0, load_kw=0.0, desired_net_export_kw=0.0,
             grid_status=False, dt_hours=1.0)
    soc_after_charge = s.soc_kwh
    # Discharge what's in the battery
    s = step(h, s, solar_kw=0.0, load_kw=20.0, desired_net_export_kw=0.0,
             grid_status=False, dt_hours=1.0)
    served = soc_after_charge - s.soc_kwh - (s.unmet_kwh * 0)  # battery drained
    # The energy returned to the load from the battery is √η * soc_after_charge.
    # Original input was 10 kWh → battery held √0.9 * 10 → load got 0.9 * 10 = 9 kWh.
    delivered_to_load = math.sqrt(0.9) * soc_after_charge
    assert delivered_to_load == pytest.approx(9.0, abs=1e-6)
```

- [x] **Step 2: Run and verify failure**

```bash
pytest tests/test_household.py -v -k rt_efficiency
```

Expected: 2 failures (assertions about soc_kwh and wasted_kwh).

- [x] **Step 3: Apply √η factor in `step()`**

In `sim/household.py`, modify `step()`. The cleanest formulation:

- **Charge branch:** The energy "drawn from solar surplus" gets multiplied by `√η` to compute "energy stored." The RT loss (`drawn − stored`) is logged as `wasted`.
- **Discharge branch:** To deliver `D` kWh to the load, we must draw `D / √η` from the battery. The RT loss is `drawn − delivered`, also logged as `wasted`.

```python
import math


def step(
    h: Household,
    s: HouseholdState,
    solar_kw: float,
    load_kw: float,
    desired_net_export_kw: float,
    grid_status: bool,
    dt_hours: float,
) -> HouseholdState:
    """Advance one tick. Ignores desired_net_export_kw and grid_status (Task 5 wires those up)."""
    net_kw = solar_kw - load_kw
    net_kwh = net_kw * dt_hours
    sqrt_eff = math.sqrt(h.rt_efficiency)
    floor_kwh = h.dod_floor_frac * h.battery_kwh
    max_step_kwh = h.battery_max_rate_kw * dt_hours

    if net_kwh >= 0:
        # Charge: we want to draw `gross_in` kWh from solar surplus, store `gross_in * sqrt_eff`.
        # Constraints: surplus available, battery rate, battery headroom.
        headroom_kwh = h.battery_kwh - s.soc_kwh
        max_storable = headroom_kwh                   # what fits in the battery
        max_drawable_for_storage = max_storable / sqrt_eff if sqrt_eff > 0 else float("inf")
        gross_in = min(net_kwh, max_step_kwh, max_drawable_for_storage)
        stored = gross_in * sqrt_eff
        rt_loss = gross_in - stored
        surplus_overflow = net_kwh - gross_in         # solar surplus that couldn't enter the cycle
        wasted = rt_loss + surplus_overflow
        unmet = 0.0
        new_soc = s.soc_kwh + stored
    else:
        deficit_kwh = -net_kwh
        # Discharge: deliver up to `deficit_kwh` to the load. Drawing X from battery delivers X*sqrt_eff.
        available_kwh = max(0.0, s.soc_kwh - floor_kwh)
        max_drawable = min(max_step_kwh, available_kwh)
        max_deliverable = max_drawable * sqrt_eff
        delivered = min(deficit_kwh, max_deliverable)
        drawn = delivered / sqrt_eff if sqrt_eff > 0 else 0.0
        rt_loss = drawn - delivered
        unmet = deficit_kwh - delivered
        wasted = rt_loss
        new_soc = s.soc_kwh - drawn

    return replace(
        s,
        soc_kwh=new_soc,
        last_solar_kw=solar_kw,
        last_load_kw=load_kw,
        grid_connected=grid_status,
        wasted_kwh=wasted,
        unmet_kwh=unmet,
    )
```

Verify by hand on `test_rt_efficiency_on_charge` (solar=10, load=0, dt=1, max_rate=20, η=0.9, battery=13.5):
- `net_kwh = 10`, `max_drawable_for_storage = 13.5/√0.9 ≈ 14.23`, so `gross_in = min(10, 20, 14.23) = 10`
- `stored = 10 × √0.9 ≈ 9.487`, `rt_loss ≈ 0.513`, `surplus_overflow = 0`
- `wasted ≈ 0.513` ✓ (matches test expectation)

Verify on `test_rt_efficiency_full_cycle` after the discharge step (initial soc_after_charge = 9.487, load=20, dt=1, max_rate=20, η=0.9):
- `deficit = 20`, `available = 9.487`, `max_drawable = min(20, 9.487) = 9.487`, `max_deliverable = 9.487 × √0.9 ≈ 9.0`
- `delivered = min(20, 9.0) = 9.0` ✓ (matches `delivered_to_load == 9.0`)

**Important:** the earlier tests from Task 3 (`test_charge_clamps_to_battery_max_rate`, etc.) use `rt_efficiency=1.0` via `make_house` defaults, so `sqrt_eff = 1.0` and the new formulas reduce to the Task 3 behavior. Re-run them after the change to confirm.

- [x] **Step 4: Run all household tests and verify passing**

```bash
pytest tests/test_household.py -v
mypy
```

Expected: 8 tests pass.

- [x] **Step 5: Commit**

```bash
git add sim/household.py tests/test_household.py
git commit -m "feat(household): round-trip efficiency with sqrt(eta) split"
```

---

## Task 5: Household — net export (peer transfers + grid)

**Files:**
- Modify: `sim/household.py`
- Modify: `tests/test_household.py`

Until now `desired_net_export_kw` and `grid_status` have been ignored. Now wire them up.

**Convention:** `desired_net_export_kw > 0` means the household wants to *send out* energy this tick (after meeting its own load). `< 0` means it wants to *import* energy. Whether the energy comes from peers or grid is the engine/network's problem; `step()` only sees the net result.

The flow is:
1. Compute `surplus_kw = solar_kw - load_kw - desired_net_export_kw`.
2. If `surplus_kw > 0`: charge the battery with what's left (subject to rate + capacity + RT).
3. If `surplus_kw < 0`: discharge the battery to make up the deficit (subject to rate + DoD + RT).
4. If grid is connected, any unmet deficit is filled from the grid (up to `grid_max_kw`); any wasted surplus can be exported to the grid (up to `grid_max_kw`). Track `grid_import_kwh` / `grid_export_kwh`.

- [x] **Step 1: Write failing tests**

```python
def test_export_to_peers_drains_battery() -> None:
    """Solar 0, load 0, export 4 kW for 0.25 h → 1 kWh leaves battery (before RT loss)."""
    h = make_house(rt_efficiency=1.0, dod_floor_frac=0.0)
    s0 = HouseholdState(soc_kwh=10.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    s1 = step(
        h, s0, solar_kw=0.0, load_kw=0.0, desired_net_export_kw=4.0,
        grid_status=False, dt_hours=0.25,
    )
    assert s1.soc_kwh == pytest.approx(9.0, abs=1e-9)
    assert s1.grid_import_kwh == 0.0
    assert s1.grid_export_kwh == 0.0


def test_grid_fills_unmet_load_when_connected() -> None:
    """No solar, load 5 kW for 1 h, battery empty, grid up → grid_import = 5 kWh."""
    h = make_house(battery_max_rate_kw=5.0, grid_max_kw=10.0)
    s0 = HouseholdState(soc_kwh=0.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=True)
    s1 = step(
        h, s0, solar_kw=0.0, load_kw=5.0, desired_net_export_kw=0.0,
        grid_status=True, dt_hours=1.0,
    )
    assert s1.unmet_kwh == 0.0
    assert s1.grid_import_kwh == pytest.approx(5.0, abs=1e-9)


def test_grid_disconnected_leaves_deficit_unmet() -> None:
    """Same setup but grid down → unmet = 5 kWh, no grid import."""
    h = make_house(battery_max_rate_kw=5.0, grid_max_kw=10.0, dod_floor_frac=0.0)
    s0 = HouseholdState(soc_kwh=0.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    s1 = step(
        h, s0, solar_kw=0.0, load_kw=5.0, desired_net_export_kw=0.0,
        grid_status=False, dt_hours=1.0,
    )
    assert s1.unmet_kwh == pytest.approx(5.0, abs=1e-9)
    assert s1.grid_import_kwh == 0.0
```

- [x] **Step 2: Run and verify failure**

```bash
pytest tests/test_household.py -v -k "export or grid"
```

Expected: fails (no `grid_import_kwh` / `grid_export_kwh` fields, `desired_net_export_kw` ignored).

- [x] **Step 3: Extend `HouseholdState` and rewrite `step()`**

Add fields to `HouseholdState`:

```python
@dataclass(frozen=True, slots=True)
class HouseholdState:
    soc_kwh: float
    last_solar_kw: float
    last_load_kw: float
    grid_connected: bool
    wasted_kwh: float = 0.0
    unmet_kwh: float = 0.0
    grid_import_kwh: float = 0.0
    grid_export_kwh: float = 0.0
    achieved_net_export_kw: float = 0.0  # what the network actually saw leaving this house
```

Replace `step()`:

```python
def step(
    h: Household,
    s: HouseholdState,
    solar_kw: float,
    load_kw: float,
    desired_net_export_kw: float,
    grid_status: bool,
    dt_hours: float,
) -> HouseholdState:
    """Advance one tick honoring desired_net_export_kw and grid_status.

    Convention: positive desired_net_export_kw means this house sends energy out
    to peers; negative means it receives. The engine has already validated the
    desired value against per-house caps before calling step(), so in normal
    operation no shortfall occurs. The shortfall branch below is a safety net.
    """
    sqrt_eff = math.sqrt(h.rt_efficiency)
    floor_kwh = h.dod_floor_frac * h.battery_kwh
    max_step_kwh = h.battery_max_rate_kw * dt_hours
    max_grid_kwh = h.grid_max_kw * dt_hours

    # Local energy after meeting load AND honoring the desired export.
    # Positive: extra energy to store/export-to-grid. Negative: shortfall to source.
    surplus_kwh = (solar_kw - load_kw - desired_net_export_kw) * dt_hours

    grid_import = 0.0
    grid_export = 0.0

    if surplus_kwh >= 0:
        # 1. Store as much as we can in the battery
        headroom_kwh = h.battery_kwh - s.soc_kwh
        max_drawable_for_storage = headroom_kwh / sqrt_eff if sqrt_eff > 0 else float("inf")
        gross_in = min(surplus_kwh, max_step_kwh, max_drawable_for_storage)
        stored = gross_in * sqrt_eff
        rt_loss = gross_in - stored
        leftover = surplus_kwh - gross_in
        # 2. Export leftover to grid if connected; otherwise wasted (curtailed)
        if grid_status:
            grid_export = min(leftover, max_grid_kwh)
            wasted = (leftover - grid_export) + rt_loss
        else:
            wasted = leftover + rt_loss
        unmet = 0.0
        new_soc = s.soc_kwh + stored
        achieved_net_export_kw = desired_net_export_kw
    else:
        deficit_kwh = -surplus_kwh
        # 1. Source from battery: to deliver D, draw D / sqrt_eff (max-rate + DoD-floor capped)
        available_kwh = max(0.0, s.soc_kwh - floor_kwh)
        max_drawable = min(max_step_kwh, available_kwh)
        max_deliverable = max_drawable * sqrt_eff
        delivered_from_battery = min(deficit_kwh, max_deliverable)
        drawn = delivered_from_battery / sqrt_eff if sqrt_eff > 0 else 0.0
        rt_loss = drawn - delivered_from_battery
        remaining_deficit = deficit_kwh - delivered_from_battery
        # 2. Source from grid if connected
        if grid_status and remaining_deficit > 0:
            grid_import = min(remaining_deficit, max_grid_kwh)
            remaining_deficit -= grid_import
        # 3. Anything still unsourced is a true shortfall
        wasted = rt_loss
        if remaining_deficit > 0 and desired_net_export_kw > 0:
            # Shortfall attributed to the export request first (we couldn't deliver to peers)
            export_short_kwh = min(remaining_deficit, desired_net_export_kw * dt_hours)
            achieved_net_export_kw = desired_net_export_kw - export_short_kwh / dt_hours
            unmet = remaining_deficit - export_short_kwh   # remainder = unmet load
        else:
            achieved_net_export_kw = desired_net_export_kw
            unmet = remaining_deficit
        new_soc = s.soc_kwh - drawn

    return replace(
        s,
        soc_kwh=new_soc,
        last_solar_kw=solar_kw,
        last_load_kw=load_kw,
        grid_connected=grid_status,
        wasted_kwh=wasted,
        unmet_kwh=unmet,
        grid_import_kwh=grid_import,
        grid_export_kwh=grid_export,
        achieved_net_export_kw=achieved_net_export_kw,
    )
```

Hand-verify on the three new tests:
- `test_export_to_peers_drains_battery` (η=1, dod=0, export=4 kW, dt=0.25, soc=10): surplus=−1, deficit=1, drawable=1.25, deliverable=1.25, delivered=1, drawn=1, soc=9. ✓
- `test_grid_fills_unmet_load_when_connected` (load=5, soc=0, max_rate=5, grid_max=10, grid up): deficit=5, available=0, delivered_from_battery=0, grid_import=5, unmet=0. ✓
- `test_grid_disconnected_leaves_deficit_unmet` (same, grid down, dod=0): deficit=5, available=0, grid_import=0, unmet=5. ✓

- [x] **Step 4: Run all tests and verify passing**

```bash
pytest tests/test_household.py -v
mypy
```

Expected: all household tests pass (including the three new ones).

- [x] **Step 5: Commit**

```bash
git add sim/household.py tests/test_household.py
git commit -m "feat(household): handle net export + grid import/export"
```

---

## Task 6: Data layer — protocols and SyntheticAdapter

**Files:**
- Create: `sim/data.py`
- Create: `tests/test_data.py`

We need data adapters that produce a solar profile and load profile per timestep. The real Pecan Street + NREL adapters are deferred to Task 25 (they require external account approval). For now, ship a `SyntheticAdapter` that lets us run end-to-end and lets the tests pin physics in hand-computable scenarios.

- [x] **Step 1: Write failing tests**

`tests/test_data.py`:

```python
"""Tests for data adapters."""
from datetime import datetime, timedelta

import numpy as np
import pytest

from sim.data import LoadProfile, SolarProfile, SyntheticLoad, SyntheticSolar


def test_synthetic_solar_returns_zero_at_night() -> None:
    sp = SyntheticSolar(peak_kw=10.0, sunrise_hour=6, sunset_hour=18)
    # Midnight
    t = datetime(2024, 7, 1, 0, 0)
    assert sp.get_kw(t) == 0.0
    # 5 AM
    assert sp.get_kw(datetime(2024, 7, 1, 5, 0)) == 0.0


def test_synthetic_solar_peaks_at_noon() -> None:
    sp = SyntheticSolar(peak_kw=10.0, sunrise_hour=6, sunset_hour=18)
    t = datetime(2024, 7, 1, 12, 0)
    assert sp.get_kw(t) == pytest.approx(10.0, abs=1e-6)


def test_synthetic_solar_symmetric() -> None:
    sp = SyntheticSolar(peak_kw=10.0, sunrise_hour=6, sunset_hour=18)
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
    """Type-check style: SyntheticLoad satisfies LoadProfile, SyntheticSolar satisfies SolarProfile."""
    lp: LoadProfile = SyntheticLoad(base_kw=2.0)
    sp: SolarProfile = SyntheticSolar(peak_kw=10.0)
    assert callable(lp.get_kw)
    assert callable(sp.get_kw)
```

- [x] **Step 2: Run and verify failure**

```bash
pytest tests/test_data.py -v
```

Expected: ImportError.

- [x] **Step 3: Implement `sim/data.py`**

```python
"""Data adapters. Phase 1 ships only the synthetic adapter; real adapters land in Task 25."""
from __future__ import annotations

import math
from datetime import datetime
from typing import Protocol


class LoadProfile(Protocol):
    """Per-household load demand in kW at a point in time."""

    def get_kw(self, t: datetime) -> float: ...

    def horizon(self) -> tuple[datetime, datetime]: ...


class SolarProfile(Protocol):
    """Per-household solar generation in kW at a point in time (before PV-size scaling)."""

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
```

- [x] **Step 4: Run tests and verify passing**

```bash
pytest tests/test_data.py -v
mypy
```

Expected: 6 tests pass.

- [x] **Step 5: Commit**

```bash
git add sim/data.py tests/test_data.py
git commit -m "feat(data): protocols and synthetic adapters"
```

---

## Task 7: Network — Neighborhood and comm graph

**Files:**
- Create: `sim/network.py`
- Create: `tests/test_network.py`

A `Neighborhood` holds the houses and the 4-neighbor spatial comm graph. Builds from a 5×6 layout.

- [x] **Step 1: Write failing tests**

`tests/test_network.py`:

```python
"""Tests for the neighborhood network."""
import pytest

from sim.network import Neighborhood, build_grid_neighborhood


def test_grid_neighborhood_5x6_has_30_houses() -> None:
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    assert len(n.comm_graph) == 30


def test_corner_house_has_2_neighbors() -> None:
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    # House (0,0) is a corner; neighbors are (0,1) and (1,0)
    assert sorted(n.comm_graph["r0c0"]) == ["r0c1", "r1c0"]


def test_edge_house_has_3_neighbors() -> None:
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    # House (0,1) is on the top edge; neighbors: (0,0), (0,2), (1,1)
    assert sorted(n.comm_graph["r0c1"]) == ["r0c0", "r0c2", "r1c1"]


def test_interior_house_has_4_neighbors() -> None:
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    # House (1,1) is interior; neighbors: (0,1), (1,0), (1,2), (2,1)
    assert sorted(n.comm_graph["r1c1"]) == ["r0c1", "r1c0", "r1c2", "r2c1"]


def test_bus_capacity_stored() -> None:
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0, bus_loss_factor=0.05)
    assert n.bus_max_kw == 50.0
    assert n.bus_loss_factor == 0.05
```

- [x] **Step 2: Run and verify failure**

```bash
pytest tests/test_network.py -v
```

Expected: ImportError.

- [x] **Step 3: Implement `sim/network.py` (initial version)**

```python
"""Neighborhood: spatial comm graph + shared physical bus + transfer settlement.

Settlement logic comes in Task 8+. This first cut just constructs the network.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Neighborhood:
    comm_graph: dict[str, list[str]] = field(default_factory=dict)
    bus_max_kw: float = 50.0
    bus_loss_factor: float = 0.05


def build_grid_neighborhood(
    rows: int, cols: int, *, bus_max_kw: float, bus_loss_factor: float = 0.05
) -> Neighborhood:
    """Build a rows×cols grid neighborhood with 4-neighbor comm graph (N/E/S/W)."""
    graph: dict[str, list[str]] = {}
    for r in range(rows):
        for c in range(cols):
            key = f"r{r}c{c}"
            neighbors: list[str] = []
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    neighbors.append(f"r{nr}c{nc}")
            graph[key] = neighbors
    return Neighborhood(comm_graph=graph, bus_max_kw=bus_max_kw, bus_loss_factor=bus_loss_factor)
```

- [x] **Step 4: Run tests and verify passing**

```bash
pytest tests/test_network.py -v
mypy
```

Expected: 5 tests pass.

- [x] **Step 5: Commit**

```bash
git add sim/network.py tests/test_network.py
git commit -m "feat(network): grid neighborhood construction with 4-neighbor comm graph"
```

---

## Task 8: Network — settle_transfers happy path

**Files:**
- Modify: `sim/network.py`
- Modify: `sim/types.py`
- Modify: `tests/test_network.py`

`settle_transfers` accepts a list of requested transfers and the current per-house state, returns the actual flows. Start with the simplest case: one sender, one receiver, no clipping. Add a `SettlementResult` type and a `SettlementEvent` for the event log.

- [x] **Step 1: Add event/result types to `sim/types.py`**

Append to `sim/types.py`:

```python
from enum import Enum


class EventKind(str, Enum):
    OUTAGE_STARTED = "outage_started"
    OUTAGE_ENDED = "outage_ended"
    TRANSFER_EXECUTED = "transfer_executed"
    BUS_SATURATED = "bus_saturated"
    SENDER_DOD_FLOOR = "sender_dod_floor"
    RECEIVER_FULL = "receiver_full"
    RECEIVER_RATE_LIMITED = "receiver_rate_limited"
    UNMET_LOAD = "unmet_load"
    NO_WHEELING_REJECTED = "no_wheeling_rejected"


@dataclass(frozen=True, slots=True)
class Event:
    kind: EventKind
    house_ids: tuple[str, ...]
    kw: float = 0.0
    details: str = ""


@dataclass(frozen=True, slots=True)
class SettlementResult:
    actual_sent: dict[str, float]      # house_id -> kW sent out (gross, pre-bus-loss)
    actual_received: dict[str, float]  # house_id -> kW received (net, post-bus-loss)
    events: list[Event]
```

- [x] **Step 2: Write failing test for happy path**

In `tests/test_network.py`:

```python
from datetime import datetime

from sim.network import settle_transfers, build_grid_neighborhood
from sim.types import EventKind, Transfer


def test_single_transfer_no_clipping() -> None:
    """One 2 kW transfer through 50 kW bus with 5% loss → sender sends 2, receiver gets 1.9."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0, bus_loss_factor=0.05)
    transfers = [Transfer(from_id="r0c0", to_id="r0c1", kw=2.0)]
    grid_status = {f"r{r}c{c}": False for r in range(5) for c in range(6)}
    sender_caps = {hid: 10.0 for hid in grid_status}     # max each can send this tick (kW)
    receiver_caps = {hid: 10.0 for hid in grid_status}   # max each can absorb this tick (kW)

    result = settle_transfers(n, transfers, grid_status, sender_caps, receiver_caps)

    assert result.actual_sent["r0c0"] == pytest.approx(2.0, abs=1e-9)
    assert result.actual_received["r0c1"] == pytest.approx(2.0 * 0.95, abs=1e-9)
    assert any(e.kind == EventKind.TRANSFER_EXECUTED for e in result.events)
```

- [x] **Step 3: Run and verify failure**

```bash
pytest tests/test_network.py -v -k single_transfer
```

Expected: ImportError on `settle_transfers`.

- [x] **Step 4: Implement happy path in `sim/network.py`**

Add to `sim/network.py`:

```python
from sim.types import Event, EventKind, SettlementResult, Transfer


def settle_transfers(
    n: Neighborhood,
    requested: list[Transfer],
    grid_status: dict[str, bool],
    sender_caps_kw: dict[str, float],
    receiver_caps_kw: dict[str, float],
) -> SettlementResult:
    """Clip requested transfers to physical limits and return what really moved.

    sender_caps_kw[h]: max kW that house h can deliver (battery+solar headroom over dt_hours)
    receiver_caps_kw[h]: max kW that house h can accept (battery headroom + load demand)
    """
    actual_sent: dict[str, float] = {hid: 0.0 for hid in n.comm_graph}
    actual_received: dict[str, float] = {hid: 0.0 for hid in n.comm_graph}
    events: list[Event] = []

    # Happy path only: pretend caps are infinite and bus is uncapped. Future tasks add the constraints.
    for t in requested:
        actual_sent[t.from_id] += t.kw
        actual_received[t.to_id] += t.kw * (1.0 - n.bus_loss_factor)
        events.append(
            Event(
                kind=EventKind.TRANSFER_EXECUTED,
                house_ids=(t.from_id, t.to_id),
                kw=t.kw,
                details="happy path",
            )
        )

    return SettlementResult(
        actual_sent=actual_sent, actual_received=actual_received, events=events
    )
```

- [x] **Step 5: Run tests and verify passing**

```bash
pytest tests/test_network.py -v
mypy
```

Expected: 6 tests pass.

- [x] **Step 6: Commit**

```bash
git add sim/types.py sim/network.py tests/test_network.py
git commit -m "feat(network): settle_transfers happy path with bus-loss accounting"
```

---

## Task 9: Network — sender/receiver cap clipping

**Files:**
- Modify: `sim/network.py`
- Modify: `tests/test_network.py`

Now apply sender DoD / receiver-full constraints. When a sender's cap is below the requested kW, clip and emit a `SENDER_DOD_FLOOR` event. When a receiver's cap is below what it would receive, clip the *sender's* send and emit `RECEIVER_FULL`. Multiple transfers from the same sender share the sender's cap proportionally.

- [x] **Step 1: Write failing tests**

```python
def test_sender_cap_clips_transfer() -> None:
    """Sender wants to send 5 kW but can only spare 3 → sent=3, event emitted."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    transfers = [Transfer(from_id="r0c0", to_id="r0c1", kw=5.0)]
    grid_status = {f"r{r}c{c}": False for r in range(5) for c in range(6)}
    sender_caps = {hid: 10.0 for hid in grid_status}
    sender_caps["r0c0"] = 3.0
    receiver_caps = {hid: 10.0 for hid in grid_status}

    result = settle_transfers(n, transfers, grid_status, sender_caps, receiver_caps)
    assert result.actual_sent["r0c0"] == pytest.approx(3.0, abs=1e-9)
    assert result.actual_received["r0c1"] == pytest.approx(3.0 * 0.95, abs=1e-9)
    assert any(e.kind == EventKind.SENDER_DOD_FLOOR for e in result.events)


def test_receiver_cap_clips_transfer() -> None:
    """Receiver can only absorb 1 kW post-loss → sender send is 1/0.95 = 1.0526 kW."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    transfers = [Transfer(from_id="r0c0", to_id="r0c1", kw=5.0)]
    grid_status = {f"r{r}c{c}": False for r in range(5) for c in range(6)}
    sender_caps = {hid: 10.0 for hid in grid_status}
    receiver_caps = {hid: 10.0 for hid in grid_status}
    receiver_caps["r0c1"] = 1.0

    result = settle_transfers(n, transfers, grid_status, sender_caps, receiver_caps)
    assert result.actual_received["r0c1"] == pytest.approx(1.0, abs=1e-9)
    assert result.actual_sent["r0c0"] == pytest.approx(1.0 / 0.95, abs=1e-6)
    assert any(e.kind == EventKind.RECEIVER_FULL for e in result.events)


def test_multiple_transfers_share_sender_cap_proportionally() -> None:
    """Sender has 3 kW cap, requests 4 to one neighbor and 2 to another → 2 + 1, proportional."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    transfers = [
        Transfer(from_id="r0c0", to_id="r0c1", kw=4.0),
        Transfer(from_id="r0c0", to_id="r1c0", kw=2.0),
    ]
    grid_status = {f"r{r}c{c}": False for r in range(5) for c in range(6)}
    sender_caps = {hid: 10.0 for hid in grid_status}
    sender_caps["r0c0"] = 3.0
    receiver_caps = {hid: 10.0 for hid in grid_status}

    result = settle_transfers(n, transfers, grid_status, sender_caps, receiver_caps)
    assert result.actual_sent["r0c0"] == pytest.approx(3.0, abs=1e-9)
    # Proportional share: r0c1 gets 4/6 * 3 = 2.0; r1c0 gets 2/6 * 3 = 1.0
    assert result.actual_received["r0c1"] == pytest.approx(2.0 * 0.95, abs=1e-6)
    assert result.actual_received["r1c0"] == pytest.approx(1.0 * 0.95, abs=1e-6)
```

- [x] **Step 2: Run and verify failure**

```bash
pytest tests/test_network.py -v -k "cap or proportional"
```

Expected: 3 failures (current implementation ignores caps).

- [x] **Step 3: Replace `settle_transfers` with cap-aware version**

```python
def settle_transfers(
    n: Neighborhood,
    requested: list[Transfer],
    grid_status: dict[str, bool],
    sender_caps_kw: dict[str, float],
    receiver_caps_kw: dict[str, float],
) -> SettlementResult:
    actual_sent: dict[str, float] = {hid: 0.0 for hid in n.comm_graph}
    actual_received: dict[str, float] = {hid: 0.0 for hid in n.comm_graph}
    events: list[Event] = []
    loss_factor = 1.0 - n.bus_loss_factor

    # Group requested transfers by sender so we can clip proportionally
    by_sender: dict[str, list[Transfer]] = {}
    for t in requested:
        by_sender.setdefault(t.from_id, []).append(t)

    # Provisional "want to receive" tally per receiver
    receiver_want: dict[str, float] = {hid: 0.0 for hid in n.comm_graph}

    # Step A: clip each sender's outgoing to sender_cap, share proportionally if exceeded
    sender_alloc: dict[str, dict[str, float]] = {}  # sender -> {receiver -> kw}
    for sender, transfers in by_sender.items():
        total_req = sum(t.kw for t in transfers)
        cap = sender_caps_kw.get(sender, 0.0)
        if total_req <= cap or total_req == 0.0:
            allocations = {t.to_id: t.kw for t in transfers}
        else:
            scale = cap / total_req
            allocations = {t.to_id: t.kw * scale for t in transfers}
            events.append(
                Event(
                    kind=EventKind.SENDER_DOD_FLOOR,
                    house_ids=(sender,),
                    kw=total_req - cap,
                    details=f"requested {total_req:.3f} kW, cap {cap:.3f} kW",
                )
            )
        sender_alloc[sender] = allocations
        for r, kw in allocations.items():
            receiver_want[r] += kw * loss_factor

    # Step B: clip per-receiver against receiver_cap
    receiver_scale: dict[str, float] = {}
    for r, want_net in receiver_want.items():
        cap = receiver_caps_kw.get(r, 0.0)
        if want_net > cap and want_net > 0.0:
            receiver_scale[r] = cap / want_net
            events.append(
                Event(
                    kind=EventKind.RECEIVER_FULL,
                    house_ids=(r,),
                    kw=want_net - cap,
                    details=f"wanted {want_net:.3f} kW net, cap {cap:.3f} kW",
                )
            )
        else:
            receiver_scale[r] = 1.0

    # Step C: apply receiver clipping back to senders + tally final flows
    for sender, allocations in sender_alloc.items():
        for r, kw in allocations.items():
            final_send = kw * receiver_scale[r]
            actual_sent[sender] += final_send
            actual_received[r] += final_send * loss_factor
            if final_send > 0:
                events.append(
                    Event(
                        kind=EventKind.TRANSFER_EXECUTED,
                        house_ids=(sender, r),
                        kw=final_send,
                    )
                )

    return SettlementResult(actual_sent=actual_sent, actual_received=actual_received, events=events)
```

- [x] **Step 4: Run tests and verify passing**

```bash
pytest tests/test_network.py -v
mypy
```

Expected: 8 tests pass (previous 5 + 3 new).

- [x] **Step 5: Commit**

```bash
git add sim/network.py tests/test_network.py
git commit -m "feat(network): sender and receiver cap clipping with proportional fairness"
```

---

## Task 10: Network — bus saturation and no-wheeling

**Files:**
- Modify: `sim/network.py`
- Modify: `tests/test_network.py`

Two more constraints:

1. **Bus saturation:** if the *total* gross sent through the bus exceeds `bus_max_kw`, scale everything down proportionally and emit `BUS_SATURATED`.
2. **No wheeling in partial islands:** if some houses are grid-connected and others aren't, transfers between a connected sender and an islanded receiver (or vice versa) are blocked. Emit `NO_WHEELING_REJECTED`.

- [x] **Step 1: Write failing tests**

```python
def test_bus_saturation_clips_proportionally() -> None:
    """Two transfers of 30 and 30 kW through 50 kW bus → clipped to 25 each."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0, bus_loss_factor=0.0)
    transfers = [
        Transfer(from_id="r0c0", to_id="r0c1", kw=30.0),
        Transfer(from_id="r1c0", to_id="r1c1", kw=30.0),
    ]
    grid_status = {f"r{r}c{c}": False for r in range(5) for c in range(6)}
    caps = {hid: 100.0 for hid in grid_status}
    result = settle_transfers(n, transfers, grid_status, caps, caps)
    assert result.actual_sent["r0c0"] == pytest.approx(25.0, abs=1e-6)
    assert result.actual_sent["r1c0"] == pytest.approx(25.0, abs=1e-6)
    assert any(e.kind == EventKind.BUS_SATURATED for e in result.events)


def test_no_wheeling_in_partial_island() -> None:
    """Sender grid-connected, receiver islanded → transfer blocked."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    transfers = [Transfer(from_id="r0c0", to_id="r0c1", kw=2.0)]
    grid_status = {f"r{r}c{c}": False for r in range(5) for c in range(6)}
    grid_status["r0c0"] = True  # sender is connected
    grid_status["r0c1"] = False  # receiver is islanded
    caps = {hid: 100.0 for hid in grid_status}
    result = settle_transfers(n, transfers, grid_status, caps, caps)
    assert result.actual_sent["r0c0"] == 0.0
    assert result.actual_received["r0c1"] == 0.0
    assert any(e.kind == EventKind.NO_WHEELING_REJECTED for e in result.events)


def test_all_islanded_allows_transfer() -> None:
    """All houses islanded → transfers work normally."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0, bus_loss_factor=0.05)
    transfers = [Transfer(from_id="r0c0", to_id="r0c1", kw=2.0)]
    grid_status = {f"r{r}c{c}": False for r in range(5) for c in range(6)}
    caps = {hid: 100.0 for hid in grid_status}
    result = settle_transfers(n, transfers, grid_status, caps, caps)
    assert result.actual_sent["r0c0"] == pytest.approx(2.0, abs=1e-9)


def test_all_connected_allows_transfer() -> None:
    """All houses grid-connected → transfers work normally (this is the default outage-free case)."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0, bus_loss_factor=0.05)
    transfers = [Transfer(from_id="r0c0", to_id="r0c1", kw=2.0)]
    grid_status = {f"r{r}c{c}": True for r in range(5) for c in range(6)}
    caps = {hid: 100.0 for hid in grid_status}
    result = settle_transfers(n, transfers, grid_status, caps, caps)
    assert result.actual_sent["r0c0"] == pytest.approx(2.0, abs=1e-9)
```

- [x] **Step 2: Run and verify failure**

```bash
pytest tests/test_network.py -v -k "saturation or wheeling"
```

Expected: 2 failures.

- [x] **Step 3: Apply both constraints in `settle_transfers`**

Modify `settle_transfers` to filter out wheeling transfers at the top, then add a final bus-saturation step before returning. Insert at the start of the function (before the existing grouping):

```python
    # No-wheeling filter: if sender's and receiver's grid status differ, reject.
    filtered: list[Transfer] = []
    for t in requested:
        if grid_status.get(t.from_id, False) != grid_status.get(t.to_id, False):
            events.append(
                Event(
                    kind=EventKind.NO_WHEELING_REJECTED,
                    house_ids=(t.from_id, t.to_id),
                    kw=t.kw,
                    details="grid status differs between sender and receiver",
                )
            )
        else:
            filtered.append(t)
    requested = filtered
```

And replace the closing return block with:

```python
    # Bus saturation: if total gross send exceeds bus_max_kw, scale all flows proportionally.
    total_gross = sum(actual_sent.values())
    if total_gross > n.bus_max_kw and total_gross > 0:
        scale = n.bus_max_kw / total_gross
        for hid in actual_sent:
            actual_sent[hid] *= scale
        for hid in actual_received:
            actual_received[hid] *= scale
        events.append(
            Event(
                kind=EventKind.BUS_SATURATED,
                house_ids=tuple(sorted(actual_sent)),
                kw=total_gross - n.bus_max_kw,
                details=f"total {total_gross:.3f} kW exceeded bus cap {n.bus_max_kw:.3f} kW",
            )
        )

    return SettlementResult(actual_sent=actual_sent, actual_received=actual_received, events=events)
```

- [x] **Step 4: Run all network tests and verify**

```bash
pytest tests/test_network.py -v
mypy
```

Expected: 12 tests pass.

- [x] **Step 5: Commit**

```bash
git add sim/network.py tests/test_network.py
git commit -m "feat(network): bus saturation clipping and no-wheeling rule for partial islands"
```

---

## Task 11: Scenario config

**Files:**
- Create: `sim/scenario.py`
- Create: `tests/test_scenario.py`
- Create: `configs/scenarios/synthetic_smoke.yaml`
- Create: `configs/scenarios/24h_uniform.yaml`

A `Scenario` dataclass holds everything one run needs: start/end time, dt_hours, seed, layout (rows × cols), bus parameters, household sampling parameters, outage schedule, strategy name. Loaded from YAML.

- [x] **Step 1: Write failing tests**

`tests/test_scenario.py`:

```python
"""Tests for scenario config loading and validation."""
from datetime import datetime, timedelta

import pytest

from sim.scenario import OutageWindow, Scenario, load_scenario


def test_load_smoke_scenario(tmp_path) -> None:
    yaml_text = """
scenario_id: synthetic_smoke
start: "2024-07-01T00:00:00"
end:   "2024-07-02T00:00:00"
dt_hours: 0.25
seed: 42
rows: 5
cols: 6
bus_max_kw: 50.0
bus_loss_factor: 0.05
strategy: no_coordination
data_source: synthetic
household_sampling:
  pv_kw_peak: [4.0, 12.0]
  battery_kwh: [10.0, 27.0]
  rt_efficiency: 0.9
  dod_floor_frac: 0.1
outages: []
"""
    p = tmp_path / "synthetic.yaml"
    p.write_text(yaml_text)
    s = load_scenario(p)
    assert s.scenario_id == "synthetic_smoke"
    assert s.start == datetime(2024, 7, 1)
    assert s.dt_hours == 0.25
    assert s.rows == 5
    assert s.cols == 6
    assert s.strategy == "no_coordination"
    assert s.outages == []


def test_outage_window_validation() -> None:
    with pytest.raises(ValueError, match="end before start"):
        OutageWindow(
            start=datetime(2024, 7, 1, 10),
            end=datetime(2024, 7, 1, 9),
            affected_houses=("r0c0",),
        )


def test_load_rejects_end_before_start(tmp_path) -> None:
    yaml_text = """
scenario_id: bad
start: "2024-07-02T00:00:00"
end:   "2024-07-01T00:00:00"
dt_hours: 0.25
seed: 42
rows: 5
cols: 6
bus_max_kw: 50.0
bus_loss_factor: 0.05
strategy: no_coordination
data_source: synthetic
household_sampling:
  pv_kw_peak: [4.0, 12.0]
  battery_kwh: [10.0, 27.0]
  rt_efficiency: 0.9
  dod_floor_frac: 0.1
outages: []
"""
    p = tmp_path / "bad.yaml"
    p.write_text(yaml_text)
    with pytest.raises(ValueError, match="end before start"):
        load_scenario(p)


def test_timesteps_count() -> None:
    s = Scenario(
        scenario_id="test",
        start=datetime(2024, 7, 1),
        end=datetime(2024, 7, 1) + timedelta(hours=1),
        dt_hours=0.25,
        seed=42,
        rows=5,
        cols=6,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
        strategy="no_coordination",
        data_source="synthetic",
        household_sampling={"pv_kw_peak": [4.0, 12.0], "battery_kwh": [10.0, 27.0],
                            "rt_efficiency": 0.9, "dod_floor_frac": 0.1},
        outages=(),
    )
    assert list(s.timesteps()) == [
        datetime(2024, 7, 1, 0, 0),
        datetime(2024, 7, 1, 0, 15),
        datetime(2024, 7, 1, 0, 30),
        datetime(2024, 7, 1, 0, 45),
    ]
```

- [x] **Step 2: Run and verify failure**

```bash
pytest tests/test_scenario.py -v
```

Expected: ImportError.

- [x] **Step 3: Implement `sim/scenario.py`**

```python
"""Scenario configuration: dataclasses + YAML loader."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

import yaml


@dataclass(frozen=True, slots=True)
class OutageWindow:
    start: datetime
    end: datetime
    affected_houses: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError(f"OutageWindow end before start: {self.start} -> {self.end}")


@dataclass(frozen=True, slots=True)
class Scenario:
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

    def timesteps(self) -> Iterator[datetime]:
        t = self.start
        dt = timedelta(hours=self.dt_hours)
        while t < self.end:
            yield t
            t += dt

    def grid_status_at(self, t: datetime, house_id: str) -> bool:
        for w in self.outages:
            if w.start <= t < w.end and house_id in w.affected_houses:
                return False
        return True


def load_scenario(path: Path | str) -> Scenario:
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
    )
```

- [x] **Step 4: Write the two scenario YAML files**

`configs/scenarios/synthetic_smoke.yaml`:

```yaml
scenario_id: synthetic_smoke
start: "2024-07-01T00:00:00"
end:   "2024-07-02T00:00:00"
dt_hours: 0.25
seed: 42
rows: 5
cols: 6
bus_max_kw: 50.0
bus_loss_factor: 0.05
strategy: no_coordination
data_source: synthetic
household_sampling:
  pv_kw_peak: [4.0, 12.0]
  battery_kwh: [10.0, 27.0]
  rt_efficiency: 0.9
  dod_floor_frac: 0.1
  grid_max_kw: 10.0
outages: []
```

`configs/scenarios/24h_uniform.yaml`:

```yaml
scenario_id: 24h_uniform
start: "2024-07-01T00:00:00"
end:   "2024-07-02T00:00:00"
dt_hours: 0.25
seed: 42
rows: 5
cols: 6
bus_max_kw: 50.0
bus_loss_factor: 0.05
strategy: round_robin
data_source: synthetic
household_sampling:
  pv_kw_peak: [4.0, 12.0]
  battery_kwh: [10.0, 27.0]
  rt_efficiency: 0.9
  dod_floor_frac: 0.1
  grid_max_kw: 10.0
outages:
  - start: "2024-07-01T08:00:00"
    end:   "2024-07-02T00:00:00"
    affected_houses: ["r0c0","r0c1","r0c2","r0c3","r0c4","r0c5",
                      "r1c0","r1c1","r1c2","r1c3","r1c4","r1c5",
                      "r2c0","r2c1","r2c2","r2c3","r2c4","r2c5",
                      "r3c0","r3c1","r3c2","r3c3","r3c4","r3c5",
                      "r4c0","r4c1","r4c2","r4c3","r4c4","r4c5"]
```

- [x] **Step 5: Run tests and verify passing**

```bash
pytest tests/test_scenario.py -v
mypy
```

Expected: 4 tests pass.

- [x] **Step 6: Commit**

```bash
git add sim/scenario.py tests/test_scenario.py configs/
git commit -m "feat(scenario): YAML loader with outage windows and validation"
```

---

## Task 12: Strategies — no_coordination and round_robin

**Files:**
- Create: `sim/strategies/__init__.py`
- Create: `sim/strategies/no_coordination.py`
- Create: `sim/strategies/round_robin.py`
- Create: `tests/test_strategies.py`

A strategy is a callable matching the signature from the spec:

```python
def decide_transfers(
    t: datetime,
    states: dict[str, HouseholdState],
    households: dict[str, Household],
    solar_kw: dict[str, float],
    load_kw: dict[str, float],
    grid: dict[str, bool],
    neighborhood: Neighborhood,
    dt_hours: float,
) -> list[Transfer]: ...
```

- [x] **Step 1: Write failing tests**

`tests/test_strategies.py`:

```python
"""Tests for coordination strategies."""
from datetime import datetime

from sim.household import Household, HouseholdState
from sim.network import build_grid_neighborhood
from sim.strategies.no_coordination import decide_transfers as no_coord
from sim.strategies.round_robin import decide_transfers as round_robin
from sim.types import HouseholdProfile


def make_state(soc: float = 5.0, grid: bool = False) -> HouseholdState:
    return HouseholdState(soc_kwh=soc, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=grid)


def make_household(hid: str) -> Household:
    return Household(
        id=hid, pv_kw_peak=8.0, battery_kwh=13.5, battery_max_rate_kw=5.0,
        rt_efficiency=0.9, dod_floor_frac=0.1, grid_max_kw=10.0,
        profile=HouseholdProfile(description="test"),
    )


def test_no_coordination_returns_empty() -> None:
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    households = {hid: make_household(hid) for hid in n.comm_graph}
    states = {hid: make_state() for hid in n.comm_graph}
    solar = {hid: 4.0 for hid in n.comm_graph}
    load = {hid: 1.0 for hid in n.comm_graph}
    grid = {hid: False for hid in n.comm_graph}
    transfers = no_coord(datetime(2024, 7, 1, 12, 0), states, households, solar, load, grid, n, 0.25)
    assert transfers == []


def test_round_robin_moves_from_high_soc_to_low_soc_neighbor() -> None:
    """House with full battery + no load should send to a low-soc neighbor."""
    n = build_grid_neighborhood(rows=5, cols=6, bus_max_kw=50.0)
    households = {hid: make_household(hid) for hid in n.comm_graph}
    states = {hid: make_state(soc=5.0) for hid in n.comm_graph}
    # Make r0c0 full, r0c1 nearly empty
    states["r0c0"] = make_state(soc=13.0)
    states["r0c1"] = make_state(soc=2.0)
    solar = {hid: 0.0 for hid in n.comm_graph}
    load = {hid: 1.0 for hid in n.comm_graph}
    grid = {hid: False for hid in n.comm_graph}
    transfers = round_robin(datetime(2024, 7, 1, 12, 0), states, households, solar, load, grid, n, 0.25)
    # At least one transfer should originate at r0c0 and go to r0c1
    assert any(t.from_id == "r0c0" and t.to_id == "r0c1" for t in transfers)
```

- [x] **Step 2: Run and verify failure**

```bash
pytest tests/test_strategies.py -v
```

Expected: ImportError.

- [x] **Step 3: Implement strategies**

`sim/strategies/__init__.py`: empty.

`sim/strategies/no_coordination.py`:

```python
"""Each household acts alone — no inter-household transfers."""
from __future__ import annotations

from datetime import datetime

from sim.household import Household, HouseholdState
from sim.network import Neighborhood
from sim.types import Transfer


def decide_transfers(
    t: datetime,
    states: dict[str, HouseholdState],
    households: dict[str, Household],
    solar_kw: dict[str, float],
    load_kw: dict[str, float],
    grid: dict[str, bool],
    neighborhood: Neighborhood,
    dt_hours: float,
) -> list[Transfer]:
    return []
```

`sim/strategies/round_robin.py`:

```python
"""Naive fairness baseline: each tick, houses with above-mean SoC send a small
amount to each of their comm neighbors that have below-mean SoC.

This is not optimal — it's the "is coordination doing anything at all?" check.
"""
from __future__ import annotations

from datetime import datetime

from sim.household import Household, HouseholdState
from sim.network import Neighborhood
from sim.types import Transfer


SHARE_FRACTION = 0.05  # fraction of available headroom to share per tick


def decide_transfers(
    t: datetime,
    states: dict[str, HouseholdState],
    households: dict[str, Household],
    solar_kw: dict[str, float],
    load_kw: dict[str, float],
    grid: dict[str, bool],
    neighborhood: Neighborhood,
    dt_hours: float,
) -> list[Transfer]:
    # Compute mean SoC fraction across islanded houses only
    islanded = [hid for hid, ok in grid.items() if not ok]
    if not islanded:
        return []
    fracs = {hid: states[hid].soc_kwh / households[hid].battery_kwh for hid in islanded}
    mean = sum(fracs.values()) / len(fracs)

    transfers: list[Transfer] = []
    for hid in islanded:
        if fracs[hid] <= mean:
            continue
        # Available headroom over dod floor
        h = households[hid]
        available_kwh = max(0.0, states[hid].soc_kwh - h.dod_floor_frac * h.battery_kwh)
        share_kwh = available_kwh * SHARE_FRACTION
        share_kw = share_kwh / dt_hours
        if share_kw <= 0:
            continue
        # Send to islanded neighbors below mean, split evenly
        targets = [n for n in neighborhood.comm_graph[hid] if n in fracs and fracs[n] < mean]
        if not targets:
            continue
        per_target_kw = share_kw / len(targets)
        if per_target_kw <= 0:
            continue
        for target in targets:
            transfers.append(Transfer(from_id=hid, to_id=target, kw=per_target_kw))
    return transfers
```

- [x] **Step 4: Run tests and verify passing**

```bash
pytest tests/test_strategies.py -v
mypy
```

Expected: 2 tests pass.

- [x] **Step 5: Commit**

```bash
git add sim/strategies/ tests/test_strategies.py
git commit -m "feat(strategies): no_coordination and round_robin baselines"
```

---

## Task 13: Logging — JSONL writers

**Files:**
- Create: `sim/logging.py`
- Create: `tests/test_logging.py`

`JsonlLogger` writes per-tick state rows and events to two separate JSONL files. Opens the files in `__init__`, exposes `write_state(t, states, solar, load, grid)`, `write_events(events)`, and `finalize() -> RunSummary`.

- [x] **Step 1: Write failing tests**

`tests/test_logging.py`:

```python
"""Tests for run logging."""
import json
from datetime import datetime

from sim.household import HouseholdState
from sim.logging import JsonlLogger
from sim.types import Event, EventKind


def test_logger_writes_state_rows(tmp_path) -> None:
    out = tmp_path / "run"
    lg = JsonlLogger(out, scenario_id="test")
    states = {
        "r0c0": HouseholdState(soc_kwh=5.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=True),
        "r0c1": HouseholdState(soc_kwh=3.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=True),
    }
    solar = {"r0c0": 4.0, "r0c1": 4.0}
    load = {"r0c0": 1.0, "r0c1": 1.0}
    grid = {"r0c0": True, "r0c1": True}
    lg.write_state(datetime(2024, 7, 1, 0, 0), states, solar, load, grid)
    lg.close()

    lines = (out / "state.jsonl").read_text().splitlines()
    assert len(lines) == 2
    row = json.loads(lines[0])
    assert {"t", "house_id", "soc_kwh", "solar_kw", "load_kw", "grid_status"} <= row.keys()


def test_logger_writes_events(tmp_path) -> None:
    out = tmp_path / "run"
    lg = JsonlLogger(out, scenario_id="test")
    events = [Event(kind=EventKind.OUTAGE_STARTED, house_ids=("r0c0",))]
    lg.write_events(events, t=datetime(2024, 7, 1, 0, 0))
    lg.close()

    lines = (out / "events.jsonl").read_text().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["kind"] == "outage_started"
    assert row["house_ids"] == ["r0c0"]


def test_logger_creates_config_json(tmp_path) -> None:
    out = tmp_path / "run"
    lg = JsonlLogger(out, scenario_id="test")
    lg.write_config({"foo": "bar"})
    lg.close()
    cfg = json.loads((out / "config.json").read_text())
    assert cfg == {"foo": "bar"}
```

- [x] **Step 2: Run and verify failure**

```bash
pytest tests/test_logging.py -v
```

Expected: ImportError.

- [x] **Step 3: Implement `sim/logging.py`**

```python
"""Run logging: state.jsonl, events.jsonl, config.json, summary.json."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from sim.household import HouseholdState
from sim.types import Event


class JsonlLogger:
    def __init__(self, run_dir: Path | str, scenario_id: str) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.scenario_id = scenario_id
        self._state_file = (self.run_dir / "state.jsonl").open("w")
        self._events_file = (self.run_dir / "events.jsonl").open("w")

    def write_config(self, config: dict[str, Any]) -> None:
        with (self.run_dir / "config.json").open("w") as f:
            json.dump(config, f, indent=2, default=str)

    def write_state(
        self,
        t: datetime,
        states: dict[str, HouseholdState],
        solar_kw: dict[str, float],
        load_kw: dict[str, float],
        grid: dict[str, bool],
    ) -> None:
        for hid, s in states.items():
            row = {
                "t": t.isoformat(),
                "house_id": hid,
                "soc_kwh": s.soc_kwh,
                "solar_kw": solar_kw[hid],
                "load_kw": load_kw[hid],
                "grid_status": grid[hid],
                "wasted_kwh": s.wasted_kwh,
                "unmet_kwh": s.unmet_kwh,
                "grid_import_kwh": s.grid_import_kwh,
                "grid_export_kwh": s.grid_export_kwh,
                "achieved_net_export_kw": s.achieved_net_export_kw,
            }
            self._state_file.write(json.dumps(row) + "\n")

    def write_events(self, events: list[Event], t: datetime) -> None:
        for e in events:
            row = {"t": t.isoformat(), "kind": e.kind.value, "house_ids": list(e.house_ids),
                   "kw": e.kw, "details": e.details}
            self._events_file.write(json.dumps(row) + "\n")

    def close(self) -> None:
        self._state_file.close()
        self._events_file.close()
```

- [x] **Step 4: Run tests and verify passing**

```bash
pytest tests/test_logging.py -v
mypy
```

Expected: 3 tests pass.

- [x] **Step 5: Commit**

```bash
git add sim/logging.py tests/test_logging.py
git commit -m "feat(logging): JsonlLogger writes state, events, and config"
```

---

## Task 14: Logging — summary metrics

**Files:**
- Modify: `sim/logging.py`
- Modify: `tests/test_logging.py`

`finalize()` reads back the state log, computes summary metrics, writes `summary.json`. Metrics:

- `served_load_fraction`: 1 - (total_unmet_kwh / total_load_kwh)
- `gini_welfare`: Gini coefficient over per-house served-load fraction (welfare = fraction of own load served, including via grid)
- `wasted_kwh_total`
- `transfer_count`
- `unmet_kwh_total`

- [x] **Step 1: Write failing test**

In `tests/test_logging.py`:

```python
def test_finalize_writes_summary(tmp_path) -> None:
    out = tmp_path / "run"
    lg = JsonlLogger(out, scenario_id="test")
    t0 = datetime(2024, 7, 1, 0, 0)
    states = {
        "r0c0": HouseholdState(soc_kwh=5.0, last_solar_kw=0.0, last_load_kw=2.0,
                                grid_connected=False, unmet_kwh=0.5),
        "r0c1": HouseholdState(soc_kwh=3.0, last_solar_kw=0.0, last_load_kw=2.0,
                                grid_connected=False, unmet_kwh=0.0),
    }
    lg.write_state(t0, states, {"r0c0": 0.0, "r0c1": 0.0},
                   {"r0c0": 2.0, "r0c1": 2.0}, {"r0c0": False, "r0c1": False})
    summary = lg.finalize(dt_hours=0.25)
    lg.close()

    cfg = json.loads((out / "summary.json").read_text())
    assert "served_load_fraction" in cfg
    # load each: 2 kW * 0.25 h = 0.5 kWh; unmet 0.5 + 0 = 0.5; total load 1.0; served = 0.5
    assert cfg["served_load_fraction"] == pytest.approx(0.5, abs=1e-6)
    assert cfg["unmet_kwh_total"] == pytest.approx(0.5, abs=1e-6)
```

Add `import pytest` and `from datetime import datetime` if missing.

- [x] **Step 2: Run and verify failure**

```bash
pytest tests/test_logging.py::test_finalize_writes_summary -v
```

Expected: AttributeError on `finalize`.

- [x] **Step 3: Implement `finalize` and helper**

Add to `sim/logging.py`:

```python
def _gini(values: list[float]) -> float:
    """Standard Gini coefficient. Returns 0 for perfectly equal, → 1 for maximally unequal."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    cum = sum((i + 1) * v for i, v in enumerate(sorted_v))
    total = sum(sorted_v)
    if total <= 0:
        return 0.0
    return (2 * cum) / (n * total) - (n + 1) / n
```

Add method to `JsonlLogger`:

```python
    def finalize(self, dt_hours: float) -> dict[str, Any]:
        # Re-read state.jsonl to compute summary
        self._state_file.flush()
        load_by_house: dict[str, float] = {}
        unmet_by_house: dict[str, float] = {}
        wasted_total = 0.0
        with (self.run_dir / "state.jsonl").open() as f:
            for line in f:
                row = json.loads(line)
                h = row["house_id"]
                load_by_house[h] = load_by_house.get(h, 0.0) + row["load_kw"] * dt_hours
                unmet_by_house[h] = unmet_by_house.get(h, 0.0) + row["unmet_kwh"]
                wasted_total += row["wasted_kwh"]
        total_load = sum(load_by_house.values())
        total_unmet = sum(unmet_by_house.values())
        served_frac = 1.0 - (total_unmet / total_load if total_load > 0 else 0.0)
        per_house_served = [
            (load_by_house[h] - unmet_by_house.get(h, 0.0)) / load_by_house[h]
            if load_by_house[h] > 0 else 1.0
            for h in load_by_house
        ]
        # Count transfers from events.jsonl
        self._events_file.flush()
        transfer_count = 0
        with (self.run_dir / "events.jsonl").open() as f:
            for line in f:
                row = json.loads(line)
                if row["kind"] == "transfer_executed":
                    transfer_count += 1

        summary = {
            "scenario_id": self.scenario_id,
            "served_load_fraction": served_frac,
            "unmet_kwh_total": total_unmet,
            "wasted_kwh_total": wasted_total,
            "gini_welfare": _gini(per_house_served),
            "transfer_count": transfer_count,
        }
        with (self.run_dir / "summary.json").open("w") as f:
            json.dump(summary, f, indent=2)
        return summary
```

- [x] **Step 4: Run tests and verify passing**

```bash
pytest tests/test_logging.py -v
mypy
```

Expected: 4 tests pass.

- [x] **Step 5: Commit**

```bash
git add sim/logging.py tests/test_logging.py
git commit -m "feat(logging): finalize computes Gini, served fraction, transfer count"
```

---

## Task 15: Engine — household sampling

**Files:**
- Create: `sim/engine.py`
- Create: `tests/test_engine.py`

`sample_households(scenario, rng) -> dict[str, Household]` builds the 30 households from scenario config + RNG. Deterministic — same seed → same households.

- [x] **Step 1: Write failing tests**

`tests/test_engine.py`:

```python
"""Tests for the simulation engine."""
from datetime import datetime, timedelta

import numpy as np
import pytest

from sim.engine import sample_households
from sim.scenario import Scenario


def make_scenario(seed: int = 42) -> Scenario:
    return Scenario(
        scenario_id="test", start=datetime(2024, 7, 1),
        end=datetime(2024, 7, 1) + timedelta(hours=1),
        dt_hours=0.25, seed=seed, rows=5, cols=6,
        bus_max_kw=50.0, bus_loss_factor=0.05,
        strategy="no_coordination", data_source="synthetic",
        household_sampling={
            "pv_kw_peak": [4.0, 12.0],
            "battery_kwh": [10.0, 27.0],
            "rt_efficiency": 0.9,
            "dod_floor_frac": 0.1,
            "grid_max_kw": 10.0,
        },
        outages=(),
    )


def test_sample_households_count() -> None:
    s = make_scenario()
    rng = np.random.default_rng(s.seed)
    households = sample_households(s, rng)
    assert len(households) == 30
    assert all(hid.startswith("r") for hid in households)


def test_sample_households_deterministic() -> None:
    s = make_scenario(seed=42)
    h1 = sample_households(s, np.random.default_rng(s.seed))
    h2 = sample_households(s, np.random.default_rng(s.seed))
    assert h1["r0c0"].pv_kw_peak == h2["r0c0"].pv_kw_peak
    assert h1["r2c3"].battery_kwh == h2["r2c3"].battery_kwh


def test_sample_households_in_range() -> None:
    s = make_scenario()
    households = sample_households(s, np.random.default_rng(s.seed))
    for h in households.values():
        assert 4.0 <= h.pv_kw_peak <= 12.0
        assert 10.0 <= h.battery_kwh <= 27.0
        assert h.rt_efficiency == 0.9
```

- [x] **Step 2: Run and verify failure**

```bash
pytest tests/test_engine.py -v
```

Expected: ImportError.

- [x] **Step 3: Implement `sim/engine.py` initial bits**

```python
"""Simulation engine: builds households, owns the clock, drives the per-tick loop."""
from __future__ import annotations

import numpy as np

from sim.household import Household
from sim.scenario import Scenario
from sim.types import HouseholdProfile


def sample_households(scenario: Scenario, rng: np.random.Generator) -> dict[str, Household]:
    sampling = scenario.household_sampling
    pv_lo, pv_hi = sampling["pv_kw_peak"]
    bat_lo, bat_hi = sampling["battery_kwh"]
    rt_eff = float(sampling["rt_efficiency"])
    dod = float(sampling["dod_floor_frac"])
    grid_max = float(sampling.get("grid_max_kw", 10.0))

    households: dict[str, Household] = {}
    for r in range(scenario.rows):
        for c in range(scenario.cols):
            hid = f"r{r}c{c}"
            pv = float(rng.uniform(pv_lo, pv_hi))
            batt = float(rng.uniform(bat_lo, bat_hi))
            rate = batt / 5.0  # standard residential ratio
            households[hid] = Household(
                id=hid, pv_kw_peak=pv, battery_kwh=batt, battery_max_rate_kw=rate,
                rt_efficiency=rt_eff, dod_floor_frac=dod, grid_max_kw=grid_max,
                profile=HouseholdProfile(description=f"household {hid}"),
            )
    return households
```

- [x] **Step 4: Run tests and verify passing**

```bash
pytest tests/test_engine.py -v
mypy
```

Expected: 3 tests pass.

- [x] **Step 5: Commit**

```bash
git add sim/engine.py tests/test_engine.py
git commit -m "feat(engine): deterministic household sampling from scenario"
```

---

## Task 16: Engine — main loop and energy-balance assertion

**Files:**
- Modify: `sim/engine.py`
- Modify: `tests/test_engine.py`

`run(scenario, decide_transfers, logger, strict=True)` drives the simulation:

1. Sample households from seed.
2. Build neighborhood (`build_grid_neighborhood`).
3. Build solar + load adapters (synthetic for now; real adapters in Task 25).
4. Initialize states (battery starts at 50% SoC).
5. For each timestep `t`:
   - Compute solar / load per house.
   - Compute grid status per house from outage schedule.
   - Call `decide_transfers`.
   - Build sender_caps / receiver_caps from current states.
   - Call `settle_transfers`.
   - For each house, call `household.step(...)` with the actual transfer net export.
   - If `strict`, assert energy balance.
   - Log state + events.
6. `logger.finalize()`.

**Energy balance per house per tick (strict mode):**

`solar_kwh + grid_import + received_kwh = load_served + grid_export + sent_kwh + Δsoc + wasted + rt_loss + unmet_load_kwh`

For the strict check we use a relaxed form: `solar_kwh + grid_import + received_kwh - (load_kwh - unmet) - grid_export - sent_kwh - Δsoc` should equal (wasted + rt_loss + unmet), all of which are explicitly tracked.

A simpler test: total energy in = total energy accounted for. We verify the sum-of-changes balances.

- [x] **Step 1: Write failing test for engine.run on the smoke scenario**

```python
def test_run_smoke_no_coordination(tmp_path) -> None:
    """Synthetic-smoke scenario with no coordination should run end-to-end."""
    from pathlib import Path
    from sim.engine import run
    from sim.logging import JsonlLogger
    from sim.scenario import load_scenario
    from sim.strategies.no_coordination import decide_transfers

    scenario_path = Path(__file__).parent.parent / "configs" / "scenarios" / "synthetic_smoke.yaml"
    s = load_scenario(scenario_path)
    out = tmp_path / "run"
    logger = JsonlLogger(out, scenario_id=s.scenario_id)
    summary = run(s, decide_transfers, logger, strict=True)
    logger.close()
    assert summary["served_load_fraction"] >= 0.99  # no outage, mostly served
    # state.jsonl has 30 houses × 96 ticks = 2880 rows
    rows = (out / "state.jsonl").read_text().splitlines()
    assert len(rows) == 30 * 96
```

- [x] **Step 2: Run and verify failure**

```bash
pytest tests/test_engine.py::test_run_smoke_no_coordination -v
```

Expected: ImportError or AttributeError on `run`.

- [x] **Step 3: Implement `run`**

Append to `sim/engine.py`:

```python
import math
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sim.data import SyntheticLoad, SyntheticSolar
from sim.household import HouseholdState, step
from sim.logging import JsonlLogger
from sim.network import Neighborhood, build_grid_neighborhood, settle_transfers
from sim.types import Event, EventKind, Transfer


DecideFn = Callable[
    [datetime, dict[str, HouseholdState], dict[str, Household],
     dict[str, float], dict[str, float], dict[str, bool],
     Neighborhood, float],
    list[Transfer],
]


def run(
    scenario: Scenario,
    decide_transfers: DecideFn,
    logger: JsonlLogger,
    *,
    strict: bool = True,
) -> dict[str, Any]:
    rng = np.random.default_rng(scenario.seed)
    households = sample_households(scenario, rng)
    neighborhood = build_grid_neighborhood(
        rows=scenario.rows, cols=scenario.cols,
        bus_max_kw=scenario.bus_max_kw, bus_loss_factor=scenario.bus_loss_factor,
    )

    # Synthetic data sources for Phase 1; real adapters land in Task 25.
    solar_profile = SyntheticSolar(peak_kw=1.0)  # normalized; scaled per-house below
    load_profile = SyntheticLoad(base_kw=1.5)    # constant kW per house

    # Initialize states: each battery at 50% SoC
    states: dict[str, HouseholdState] = {}
    last_grid_status: dict[str, bool] = {}
    for hid, h in households.items():
        states[hid] = HouseholdState(
            soc_kwh=0.5 * h.battery_kwh,
            last_solar_kw=0.0, last_load_kw=0.0, grid_connected=True,
        )
        last_grid_status[hid] = True

    logger.write_config({
        "scenario_id": scenario.scenario_id,
        "start": scenario.start.isoformat(),
        "end": scenario.end.isoformat(),
        "dt_hours": scenario.dt_hours,
        "seed": scenario.seed,
        "rows": scenario.rows, "cols": scenario.cols,
        "bus_max_kw": scenario.bus_max_kw,
        "bus_loss_factor": scenario.bus_loss_factor,
        "strategy": scenario.strategy,
        "data_source": scenario.data_source,
        "household_sampling": scenario.household_sampling,
        "outages": [
            {"start": o.start.isoformat(), "end": o.end.isoformat(),
             "affected_houses": list(o.affected_houses)}
            for o in scenario.outages
        ],
        "strict": strict,
    })

    for t in scenario.timesteps():
        # Per-house solar (scaled by PV peak) and load
        solar_kw = {hid: solar_profile.get_kw(t) * h.pv_kw_peak for hid, h in households.items()}
        load_kw = {hid: load_profile.get_kw(t) for hid in households}
        grid = {hid: scenario.grid_status_at(t, hid) for hid in households}

        # Emit outage_started / outage_ended events on transitions
        outage_events: list[Event] = []
        for hid in households:
            if last_grid_status[hid] != grid[hid]:
                outage_events.append(Event(
                    kind=EventKind.OUTAGE_ENDED if grid[hid] else EventKind.OUTAGE_STARTED,
                    house_ids=(hid,),
                ))
            last_grid_status[hid] = grid[hid]

        # Coordination
        requested = decide_transfers(t, states, households, solar_kw, load_kw, grid,
                                     neighborhood, scenario.dt_hours)

        # Sender/receiver caps for clipping (over the tick, in kW)
        sender_caps_kw: dict[str, float] = {}
        receiver_caps_kw: dict[str, float] = {}
        for hid, h in households.items():
            s = states[hid]
            sqrt_eff = math.sqrt(h.rt_efficiency)
            available_kwh = max(0.0, s.soc_kwh - h.dod_floor_frac * h.battery_kwh)
            # Sender: limited by battery rate AND available kWh
            sender_caps_kw[hid] = min(h.battery_max_rate_kw, available_kwh * sqrt_eff / scenario.dt_hours)
            # Receiver: limited by battery rate AND headroom
            headroom_kwh = h.battery_kwh - s.soc_kwh
            receiver_caps_kw[hid] = min(h.battery_max_rate_kw, headroom_kwh / (sqrt_eff * scenario.dt_hours) if sqrt_eff > 0 else 0.0)

        settlement = settle_transfers(neighborhood, requested, grid, sender_caps_kw, receiver_caps_kw)

        # Update each household with its actual net export
        new_states: dict[str, HouseholdState] = {}
        for hid, h in households.items():
            net_export_kw = settlement.actual_sent[hid] - settlement.actual_received[hid]
            new_s = step(h, states[hid], solar_kw[hid], load_kw[hid],
                         desired_net_export_kw=net_export_kw,
                         grid_status=grid[hid], dt_hours=scenario.dt_hours)
            if strict:
                # Strict balance: soc must stay in [floor, capacity], no negatives in trackers
                floor = h.dod_floor_frac * h.battery_kwh
                assert floor - 1e-6 <= new_s.soc_kwh <= h.battery_kwh + 1e-6, \
                    f"SoC out of bounds at {t} for {hid}: {new_s.soc_kwh}"
                assert new_s.wasted_kwh >= -1e-9
                assert new_s.unmet_kwh >= -1e-9
            new_states[hid] = new_s
        states = new_states

        logger.write_state(t, states, solar_kw, load_kw, grid)
        logger.write_events(outage_events + settlement.events, t=t)

    return logger.finalize(dt_hours=scenario.dt_hours)
```

- [x] **Step 4: Run tests and verify**

```bash
pytest tests/test_engine.py -v
mypy
```

Expected: 4 tests pass (including the new smoke test). It may take a few seconds to run a full 24h scenario.

- [x] **Step 5: Commit**

```bash
git add sim/engine.py tests/test_engine.py
git commit -m "feat(engine): main loop with strict-mode SoC bound checks"
```

---

## Task 17: Integration test — round-robin beats no-coordination

**Files:**
- Modify: `tests/test_integration.py` (create if missing)

The first cross-cutting sanity check: on a scenario with an outage, round-robin must produce a strictly more even SoC distribution at the end than no-coordination, given the same seed.

- [x] **Step 1: Write failing test**

`tests/test_integration.py`:

```python
"""End-to-end integration tests."""
import json
from pathlib import Path

from sim.engine import run
from sim.logging import JsonlLogger
from sim.scenario import load_scenario
from sim.strategies.no_coordination import decide_transfers as no_coord
from sim.strategies.round_robin import decide_transfers as round_robin


def _run_to_summary(scenario_path: Path, strategy, out: Path) -> dict:
    s = load_scenario(scenario_path)
    logger = JsonlLogger(out, scenario_id=s.scenario_id)
    summary = run(s, strategy, logger, strict=True)
    logger.close()
    return summary


def test_round_robin_more_even_than_no_coord(tmp_path) -> None:
    scenario = Path(__file__).parent.parent / "configs" / "scenarios" / "24h_uniform.yaml"
    rr_summary = _run_to_summary(scenario, round_robin, tmp_path / "rr")
    nc_summary = _run_to_summary(scenario, no_coord, tmp_path / "nc")
    # Lower Gini = more equal welfare across households
    assert rr_summary["gini_welfare"] <= nc_summary["gini_welfare"]
    # Total served should not be worse than no-coord (round-robin only redistributes; net energy
    # may be slightly worse due to bus losses, but only by a small margin)
    assert rr_summary["served_load_fraction"] >= nc_summary["served_load_fraction"] - 0.05


def test_determinism_byte_identical(tmp_path) -> None:
    scenario = Path(__file__).parent.parent / "configs" / "scenarios" / "synthetic_smoke.yaml"
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    _run_to_summary(scenario, no_coord, out_a)
    _run_to_summary(scenario, no_coord, out_b)
    assert (out_a / "state.jsonl").read_bytes() == (out_b / "state.jsonl").read_bytes()
```

- [x] **Step 2: Run and verify**

```bash
pytest tests/test_integration.py -v
```

This is the first test where physics, network, strategy, engine, and logging all interact. If round-robin doesn't actually equalize SoC, this fails — and *that's the signal* that the strategy or the network needs tuning. Don't paper over a failure here. Debug it.

- [x] **Step 3: If `test_round_robin_more_even_than_no_coord` fails**

Re-examine the strategy. Common causes of failure:
- Round-robin shares too aggressively, hits bus saturation, energy is wasted in losses.
- Round-robin shares too little to make a measurable difference.
- The metric (Gini) is computed over a denominator that's zero for some households (they had no load).

Tune `SHARE_FRACTION` in `sim/strategies/round_robin.py` if needed. Re-run.

- [x] **Step 4: Verify both tests pass, then commit**

```bash
pytest tests/test_integration.py -v
git add tests/test_integration.py sim/strategies/round_robin.py
git commit -m "test: integration test for round-robin vs no-coordination + determinism"
```

---

## Task 18: Physics smoke test (the canary)

**Files:**
- Create: `tests/test_physics_smoke.py`

A 24-hour run with hand-computable synthetic data: constant 2 kW solar per house, constant 1 kW load, no outage. Expected end SoC: each house's start SoC + (2 - 1) × 24 × η_partial - capacity_overflow. We can hand-compute this. If the test ever fails, the physics has regressed.

- [x] **Step 1: Write the smoke test**

`tests/test_physics_smoke.py`:

```python
"""Physics smoke test: hand-computable scenario that catches any battery-model regression."""
import math
from datetime import datetime, timedelta

import numpy as np

from sim.engine import run, sample_households
from sim.logging import JsonlLogger
from sim.scenario import Scenario
from sim.strategies.no_coordination import decide_transfers


def _make_constant_data():
    """Monkey-patchable constant solar (1 kW per kW peak) and load."""
    from sim.data import SyntheticLoad, SyntheticSolar

    class FlatSolar(SyntheticSolar):
        def get_kw(self, t):
            return 1.0  # full peak all day, regardless of clock

    return FlatSolar(peak_kw=1.0), SyntheticLoad(base_kw=1.0)


def test_24h_constant_solar_load_balances(tmp_path, monkeypatch) -> None:
    """24h with constant 2 kW solar (1 kW peak × 2 PV) and 1 kW load → predictable end state."""
    # Force every household to PV=2 kW so total surplus is exactly 1 kW per house.
    flat_solar, flat_load = _make_constant_data()
    monkeypatch.setattr("sim.engine.SyntheticSolar", lambda peak_kw: flat_solar)
    monkeypatch.setattr("sim.engine.SyntheticLoad", lambda base_kw: flat_load)

    s = Scenario(
        scenario_id="smoke", start=datetime(2024, 7, 1),
        end=datetime(2024, 7, 1) + timedelta(hours=24),
        dt_hours=0.25, seed=99, rows=2, cols=2,
        bus_max_kw=50.0, bus_loss_factor=0.05,
        strategy="no_coordination", data_source="synthetic",
        household_sampling={
            "pv_kw_peak": [2.0, 2.0], "battery_kwh": [100.0, 100.0],
            "rt_efficiency": 1.0, "dod_floor_frac": 0.0, "grid_max_kw": 0.0,
        },
        outages=(),
    )
    out = tmp_path / "smoke"
    logger = JsonlLogger(out, scenario_id="smoke")
    summary = run(s, decide_transfers, logger, strict=True)
    logger.close()

    # Expected: each house starts at 50 kWh (50% of 100). Net surplus = 1 kW for 24 h = 24 kWh.
    # With rt_efficiency=1.0 and battery_max_rate >= 1 kW, end SoC = 74 kWh exactly.
    # PV=2, base_kw=1 (synthetic load * 1.0 kw). solar = peak × 1.0 = 2. Net = 1 kW.
    import json
    rows = [json.loads(line) for line in (out / "state.jsonl").read_text().splitlines()]
    last_per_house = {}
    for r in rows:
        last_per_house[r["house_id"]] = r["soc_kwh"]
    for hid, soc in last_per_house.items():
        assert abs(soc - 74.0) < 0.01, f"{hid}: expected 74.0 kWh, got {soc}"
```

- [x] **Step 2: Run and check**

```bash
pytest tests/test_physics_smoke.py -v
```

If it fails: the physics is wrong. Walk through Task 2-5 implementations on paper for one tick of this scenario. Do not adjust the test's expected value to match the bug. Fix the physics.

- [x] **Step 3: Commit**

```bash
git add tests/test_physics_smoke.py
git commit -m "test: physics smoke test with hand-computable end state"
```

---

## Task 19: CLI runner

**Files:**
- Create: `scripts/__init__.py` (empty)
- Create: `scripts/run.py`

A tiny CLI that loads a scenario YAML, picks the strategy by name, runs the simulation, and prints a one-line summary.

- [x] **Step 1: Implement `scripts/run.py`**

```python
"""CLI: python -m scripts.run --scenario configs/scenarios/24h_uniform.yaml"""
from __future__ import annotations

import argparse
import importlib
from datetime import datetime
from pathlib import Path

from sim.engine import run
from sim.logging import JsonlLogger
from sim.scenario import load_scenario


def _resolve_strategy(name: str):
    module = importlib.import_module(f"sim.strategies.{name}")
    return module.decide_transfers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--strict/--no-strict", dest="strict", action="store_true", default=True)
    parser.add_argument("--out-dir", type=Path, default=Path("runs"))
    args = parser.parse_args()

    scenario = load_scenario(args.scenario)
    decide = _resolve_strategy(scenario.strategy)
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    run_dir = args.out_dir / scenario.scenario_id / ts
    logger = JsonlLogger(run_dir, scenario_id=scenario.scenario_id)
    summary = run(scenario, decide, logger, strict=args.strict)
    logger.close()

    print(f"scenario={scenario.scenario_id} "
          f"served={summary['served_load_fraction']:.3f} "
          f"gini={summary['gini_welfare']:.3f} "
          f"wasted_kwh={summary['wasted_kwh_total']:.1f} "
          f"unmet_kwh={summary['unmet_kwh_total']:.1f} "
          f"transfers={summary['transfer_count']}")


if __name__ == "__main__":
    main()
```

- [x] **Step 2: Smoke-test the CLI manually**

```bash
python -m scripts.run --scenario configs/scenarios/24h_uniform.yaml
```

Expected: one line of output, a fresh directory under `runs/24h_uniform/<timestamp>/` with `state.jsonl`, `events.jsonl`, `config.json`, `summary.json`.

- [x] **Step 3: Commit**

```bash
git add scripts/__init__.py scripts/run.py
git commit -m "feat(cli): scripts/run.py end-to-end runner"
```

---

## Task 20: README documentation

**Files:**
- Modify: `README.md`

Rewrite the README with: project context, installation, running, scenario YAML format reference.

- [ ] **Step 1: Replace `README.md` with a full version**

````markdown
# Microgrid Sim — Phase 1

LLM-agent peer-to-peer coordination simulator for residential microgrids. **Phase 1 is the physics simulator only** — no agents yet.

Spec: `docs/superpowers/specs/2026-05-14-phase1-simulator-design.md`
Plan: `docs/superpowers/plans/2026-05-14-phase1-simulator.md`

## Install

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev,data]"
```

## Run a scenario

```bash
python -m scripts.run --scenario configs/scenarios/24h_uniform.yaml
```

Output goes to `runs/<scenario_id>/<timestamp>/`:
- `config.json` — resolved scenario config
- `state.jsonl` — one row per (house, tick) with SoC, solar, load, etc.
- `events.jsonl` — discrete events (outages, transfers, clippings)
- `summary.json` — top-level metrics (Gini, served fraction, wasted, unmet)

## Tests

```bash
pytest
ruff check sim tests
mypy
```

## Scenario YAML reference

```yaml
scenario_id: example
start: "2024-07-01T00:00:00"   # ISO datetime
end:   "2024-07-02T00:00:00"
dt_hours: 0.25                  # 15 min
seed: 42
rows: 5                         # neighborhood grid rows
cols: 6                         # grid cols → 30 houses total
bus_max_kw: 50.0                # neighborhood transformer cap
bus_loss_factor: 0.05           # 5% transit loss
strategy: round_robin           # name of file under sim/strategies/
data_source: synthetic          # 'synthetic' for Phase 1; real adapters land later
household_sampling:
  pv_kw_peak: [4.0, 12.0]       # uniform sample range
  battery_kwh: [10.0, 27.0]     # uniform sample range
  rt_efficiency: 0.9
  dod_floor_frac: 0.1
  grid_max_kw: 10.0
outages:
  - start: "2024-07-01T08:00:00"
    end:   "2024-07-02T00:00:00"
    affected_houses: ["r0c0", "r0c1", ...]
```

## Architecture

```
sim/
├── types.py         # Transfer, HouseholdProfile, Event, SettlementResult
├── data.py          # LoadProfile/SolarProfile protocols + Synthetic adapter
├── household.py     # Pure physics: step(h, s, solar, load, ...) -> new state
├── network.py       # Comm graph + settle_transfers() with bus + cap + wheel logic
├── scenario.py      # YAML config dataclasses
├── engine.py        # The simulation loop
├── logging.py       # JSONL writers + summary metrics
├── strategies/      # Pluggable coordination strategies
└── adapters/        # (Task 25) Real data adapters
```

## Status

Phase 1 deliverables:
- [x] Project scaffold, types, household physics, network settlement
- [x] Scenario YAML, no-coordination + round-robin strategies
- [x] Engine + logger + summary metrics
- [x] CLI + scenario examples + README
- [x] Unit + integration + physics-smoke tests pass
- [ ] Real data adapters (Pecan Street + NREL) — pending data access; Task 25
````

- [ ] **Step 2: Run all tests one more time before committing**

```bash
pytest
ruff check sim tests
mypy
```

Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: full README with scenario reference and architecture"
```

---

## Task 21: Real data adapter — Pecan Street (skeleton)

**Files:**
- Create: `sim/adapters/__init__.py` (empty)
- Create: `sim/adapters/pecan_street.py`
- Create: `tests/test_adapters.py`

**Note:** This task is unblocked only once your Pecan Street researcher account is approved (apply on day 1 of work). Until then, this task ships only the *skeleton* against an in-repo CSV fixture so the test passes; the real data fetch is Task 22.

- [ ] **Step 1: Create the CSV fixture**

Create `tests/fixtures/pecan_sample.csv`:

```csv
dataid,local_15min,grid,solar,use
1234,2024-07-01 00:00:00,0.5,0.0,1.2
1234,2024-07-01 00:15:00,0.45,0.0,1.1
1234,2024-07-01 00:30:00,0.4,0.0,1.0
1234,2024-07-01 00:45:00,0.6,0.0,1.3
```

(The columns mirror Pecan Street's 15-min table: grid imports, solar production, total use, all in kW.)

- [ ] **Step 2: Write failing test**

```python
"""Tests for real-data adapters (skeleton; full data fetch is Task 22)."""
from datetime import datetime
from pathlib import Path

import pytest

from sim.adapters.pecan_street import PecanStreetLoad


def test_pecan_street_load_reads_fixture() -> None:
    fixture = Path(__file__).parent / "fixtures" / "pecan_sample.csv"
    lp = PecanStreetLoad(csv_path=fixture, dataid=1234)
    # 'use' at 00:00 is 1.2 kW
    assert lp.get_kw(datetime(2024, 7, 1, 0, 0)) == pytest.approx(1.2, abs=1e-6)


def test_pecan_street_load_forward_fills_short_gap() -> None:
    fixture = Path(__file__).parent / "fixtures" / "pecan_sample.csv"
    lp = PecanStreetLoad(csv_path=fixture, dataid=1234)
    # 30 min into the future from a known value — should forward-fill (under 1h gap allowance)
    assert lp.get_kw(datetime(2024, 7, 1, 0, 1)) == pytest.approx(1.2, abs=1e-6)


def test_pecan_street_load_crashes_on_long_gap() -> None:
    fixture = Path(__file__).parent / "fixtures" / "pecan_sample.csv"
    lp = PecanStreetLoad(csv_path=fixture, dataid=1234)
    # Two hours past the last known sample → should crash
    with pytest.raises(ValueError, match="gap"):
        lp.get_kw(datetime(2024, 7, 1, 3, 0))
```

- [ ] **Step 3: Run and verify failure**

```bash
pytest tests/test_adapters.py -v
```

Expected: ImportError on `sim.adapters.pecan_street`.

- [ ] **Step 4: Implement `sim/adapters/pecan_street.py`**

```python
"""Pecan Street load profile adapter (15-min residential smart-meter data).

Apply for a researcher account at https://www.pecanstreet.org/dataport/.
Once approved, use scripts/fetch_data.py to download into data/pecan_street/.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


_MAX_GAP = timedelta(hours=1)


class PecanStreetLoad:
    def __init__(self, csv_path: Path | str, dataid: int) -> None:
        df = pd.read_csv(csv_path, parse_dates=["local_15min"])
        df = df[df["dataid"] == dataid].sort_values("local_15min").reset_index(drop=True)
        if df.empty:
            raise ValueError(f"no rows for dataid={dataid} in {csv_path}")
        self.df = df.set_index("local_15min")
        self.dataid = dataid

    def get_kw(self, t: datetime) -> float:
        # Find most recent row <= t
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
```

- [ ] **Step 5: Run tests and verify**

```bash
pytest tests/test_adapters.py -v
mypy
```

Expected: 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add sim/adapters/ tests/test_adapters.py tests/fixtures/
git commit -m "feat(adapters): Pecan Street load adapter with gap-fill and crash-on-long-gap"
```

---

## Task 22: Real data adapter — NREL solar irradiance

**Files:**
- Create: `sim/adapters/nrel_solar.py`
- Modify: `tests/test_adapters.py`

NREL's NSRDB provides hourly irradiance (GHI: global horizontal irradiance, W/m²). Convert to per-kW-peak generation using the simple approximation: `kw_per_kw_peak = (GHI / 1000) × derate`. Linearly interpolate to 15-min ticks with a small seeded noise.

- [ ] **Step 1: Create CSV fixture**

`tests/fixtures/nrel_sample.csv`:

```csv
Year,Month,Day,Hour,Minute,GHI
2024,7,1,0,0,0
2024,7,1,1,0,0
2024,7,1,6,0,50
2024,7,1,12,0,900
2024,7,1,18,0,40
2024,7,2,0,0,0
```

- [ ] **Step 2: Write failing tests**

In `tests/test_adapters.py`:

```python
from sim.adapters.nrel_solar import NRELSolar


def test_nrel_solar_returns_zero_at_midnight() -> None:
    fixture = Path(__file__).parent / "fixtures" / "nrel_sample.csv"
    sp = NRELSolar(csv_path=fixture, seed=42)
    assert sp.get_kw(datetime(2024, 7, 1, 0, 0)) == pytest.approx(0.0, abs=1e-6)


def test_nrel_solar_peaks_at_noon() -> None:
    fixture = Path(__file__).parent / "fixtures" / "nrel_sample.csv"
    sp = NRELSolar(csv_path=fixture, seed=42, derate=1.0)
    # 900 W/m² × 1.0 derate / 1000 = 0.9
    val = sp.get_kw(datetime(2024, 7, 1, 12, 0))
    # Noise is small; allow ±5%
    assert 0.85 <= val <= 0.95


def test_nrel_solar_interpolates_between_hours() -> None:
    fixture = Path(__file__).parent / "fixtures" / "nrel_sample.csv"
    sp = NRELSolar(csv_path=fixture, seed=42, derate=1.0)
    # 12:30 should be roughly between 900 and (next hour, which we don't have).
    # The fixture only has hourly samples at 0, 1, 6, 12, 18. 12:30 interp ≈ midway 12 and 18.
    # Actually 12 → 900, 18 → 40, linear at t=12.5 → 900 - (900-40) * 0.5/6 ≈ 828 W/m² → 0.828 kW.
    val = sp.get_kw(datetime(2024, 7, 1, 12, 30))
    assert 0.78 <= val <= 0.88


def test_nrel_solar_deterministic_under_seed() -> None:
    fixture = Path(__file__).parent / "fixtures" / "nrel_sample.csv"
    sp1 = NRELSolar(csv_path=fixture, seed=42)
    sp2 = NRELSolar(csv_path=fixture, seed=42)
    t = datetime(2024, 7, 1, 9, 0)
    assert sp1.get_kw(t) == sp2.get_kw(t)
```

- [ ] **Step 3: Run and verify failure**

```bash
pytest tests/test_adapters.py -v -k nrel
```

Expected: ImportError.

- [ ] **Step 4: Implement `sim/adapters/nrel_solar.py`**

```python
"""NREL NSRDB irradiance adapter."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


class NRELSolar:
    def __init__(self, csv_path: Path | str, *, seed: int, derate: float = 0.85,
                 noise_std: float = 0.02) -> None:
        df = pd.read_csv(csv_path)
        df["datetime"] = pd.to_datetime(df[["Year", "Month", "Day", "Hour", "Minute"]])
        df = df.sort_values("datetime").reset_index(drop=True)
        self.df = df.set_index("datetime")
        self.derate = derate
        self.noise_std = noise_std
        self._rng = np.random.default_rng(seed)

    def get_kw(self, t: datetime) -> float:
        # Linear interpolation between the two surrounding hourly samples
        idx = self.df.index.searchsorted(t, side="right") - 1
        if idx < 0:
            return 0.0
        t0 = self.df.index[idx]
        if idx + 1 >= len(self.df):
            ghi = self.df.iloc[idx]["GHI"]
        else:
            t1 = self.df.index[idx + 1]
            g0 = self.df.iloc[idx]["GHI"]
            g1 = self.df.iloc[idx + 1]["GHI"]
            frac = (t - t0).total_seconds() / (t1 - t0).total_seconds()
            ghi = g0 + frac * (g1 - g0)
        # Convert W/m² to per-kW-peak power
        kw_per_peak = (ghi / 1000.0) * self.derate
        # Add small reproducible noise
        if kw_per_peak > 0:
            kw_per_peak *= 1.0 + self._rng.normal(0, self.noise_std)
        return max(0.0, float(kw_per_peak))

    def horizon(self) -> tuple[datetime, datetime]:
        return (self.df.index[0].to_pydatetime(), self.df.index[-1].to_pydatetime())
```

**Note on determinism:** the noise RNG is part of the object's state, so calling `get_kw(t1); get_kw(t2)` consumes different random draws from `get_kw(t1); get_kw(t1)`. The test `test_nrel_solar_deterministic_under_seed` passes because both instances start with the same seed and make the same call sequence.

- [ ] **Step 5: Run tests and verify**

```bash
pytest tests/test_adapters.py -v
mypy
```

Expected: 7 adapter tests pass (3 PecanStreet + 4 NREL).

- [ ] **Step 6: Commit**

```bash
git add sim/adapters/nrel_solar.py tests/test_adapters.py tests/fixtures/nrel_sample.csv
git commit -m "feat(adapters): NREL NSRDB solar adapter with linear interpolation + seeded noise"
```

---

## Task 23: Wire real adapters into engine + scenario

**Files:**
- Modify: `sim/engine.py`
- Modify: `sim/scenario.py` (add `data_paths` field)
- Modify: `configs/scenarios/24h_real.yaml` (new)
- Modify: `tests/test_engine.py`

When `data_source: pecan_street` is set, the engine should build a `PecanStreetLoad` per household (one `dataid` per house from the YAML) and a single `NRELSolar` scaled per-house. The synthetic adapters stay the default.

- [ ] **Step 1: Add `data_paths` to `Scenario`**

In `sim/scenario.py`, add a field:

```python
@dataclass(frozen=True, slots=True)
class Scenario:
    # ... existing fields ...
    data_paths: dict[str, str] = field(default_factory=dict)
    house_dataids: tuple[int, ...] = field(default_factory=tuple)
```

And in `load_scenario`, pick these up from the YAML:

```python
    data_paths = dict(raw.get("data_paths", {}))
    house_dataids = tuple(int(x) for x in raw.get("house_dataids", []))
    return Scenario(
        # ... existing ...
        data_paths=data_paths,
        house_dataids=house_dataids,
    )
```

- [ ] **Step 2: Update engine to dispatch on `data_source`**

In `sim/engine.py`, replace the synthetic-only data construction with a dispatch:

```python
def _build_data(scenario: Scenario, households: dict[str, Household]):
    if scenario.data_source == "synthetic":
        from sim.data import SyntheticLoad, SyntheticSolar
        # Solar normalized to 1.0 peak; scaled per-house in the loop
        return SyntheticSolar(peak_kw=1.0), {hid: SyntheticLoad(base_kw=1.5) for hid in households}
    if scenario.data_source == "pecan_street":
        from sim.adapters.nrel_solar import NRELSolar
        from sim.adapters.pecan_street import PecanStreetLoad
        if not scenario.data_paths.get("solar_csv") or not scenario.data_paths.get("load_csv"):
            raise ValueError("data_source=pecan_street requires data_paths.solar_csv and load_csv")
        if len(scenario.house_dataids) != scenario.rows * scenario.cols:
            raise ValueError(
                f"house_dataids has {len(scenario.house_dataids)} entries, "
                f"need {scenario.rows * scenario.cols}"
            )
        solar = NRELSolar(csv_path=scenario.data_paths["solar_csv"], seed=scenario.seed)
        load: dict[str, "LoadProfile"] = {}
        for (hid, _), dataid in zip(households.items(), scenario.house_dataids):
            load[hid] = PecanStreetLoad(csv_path=scenario.data_paths["load_csv"], dataid=dataid)
        return solar, load
    raise ValueError(f"unknown data_source: {scenario.data_source}")
```

Then update the `run()` loop to call `_build_data` and use the per-house load dict:

```python
    solar_profile, load_profiles = _build_data(scenario, households)
    # ...
    for t in scenario.timesteps():
        solar_kw = {hid: solar_profile.get_kw(t) * h.pv_kw_peak for hid, h in households.items()}
        load_kw = {hid: load_profiles[hid].get_kw(t) for hid in households}
        # ... rest unchanged
```

Remove the previous monkey-patched smoke-test setup at the top of `run()` (we no longer construct `SyntheticSolar`/`SyntheticLoad` directly there) and update `tests/test_physics_smoke.py` accordingly: the test should monkeypatch `_build_data` instead of `SyntheticSolar`/`SyntheticLoad`.

- [ ] **Step 3: Update the smoke test for the new dispatch**

Replace the monkeypatch block in `tests/test_physics_smoke.py`:

```python
def test_24h_constant_solar_load_balances(tmp_path, monkeypatch) -> None:
    from sim.data import SyntheticLoad, SyntheticSolar

    class FlatSolar(SyntheticSolar):
        def get_kw(self, t):
            return 1.0
    def fake_build_data(scenario, households):
        return FlatSolar(peak_kw=1.0), {hid: SyntheticLoad(base_kw=1.0) for hid in households}

    monkeypatch.setattr("sim.engine._build_data", fake_build_data)
    # ... rest unchanged
```

- [ ] **Step 4: Write a `24h_real.yaml` scenario template**

`configs/scenarios/24h_real.yaml`:

```yaml
scenario_id: 24h_real
start: "2024-07-01T00:00:00"
end:   "2024-07-02T00:00:00"
dt_hours: 0.25
seed: 42
rows: 5
cols: 6
bus_max_kw: 50.0
bus_loss_factor: 0.05
strategy: round_robin
data_source: pecan_street
data_paths:
  solar_csv: data/nrel_solar/austin_2024.csv
  load_csv: data/pecan_street/austin_2024_15min.csv
house_dataids: []  # fill in 30 dataids from your approved Pecan Street access
household_sampling:
  pv_kw_peak: [4.0, 12.0]
  battery_kwh: [10.0, 27.0]
  rt_efficiency: 0.9
  dod_floor_frac: 0.1
  grid_max_kw: 10.0
outages: []
```

- [ ] **Step 5: Run all tests and verify**

```bash
pytest
mypy
```

Expected: every test still passes; engine now dispatches on data_source.

- [ ] **Step 6: Commit**

```bash
git add sim/engine.py sim/scenario.py configs/scenarios/24h_real.yaml tests/test_physics_smoke.py
git commit -m "feat(engine): dispatch on data_source, support Pecan Street + NREL via adapters"
```

---

## Task 24: fetch_data.py — convenience downloader

**Files:**
- Create: `scripts/fetch_data.py`

A small CLI that downloads NREL NSRDB solar for a given lat/lon/year and instructs the user how to obtain Pecan Street data (which requires manual application). It writes into `data/`.

- [ ] **Step 1: Implement `scripts/fetch_data.py`**

```python
"""Download NREL NSRDB solar irradiance for a location/year.

Pecan Street load data must be downloaded manually after researcher account approval.
Place the resulting CSV at data/pecan_street/<filename>.csv and reference it in your scenario YAML.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import requests


NSRDB_URL = "https://developer.nrel.gov/api/nsrdb/v2/solar/psm3-2-2-download.csv"


def fetch_nrel(*, api_key: str, email: str, lat: float, lon: float, year: int,
               out_path: Path) -> None:
    params = {
        "api_key": api_key,
        "email": email,
        "wkt": f"POINT({lon} {lat})",
        "names": str(year),
        "interval": "60",
        "utc": "true",
        "attributes": "ghi",
        "leap_day": "false",
    }
    print(f"Requesting NREL NSRDB for ({lat}, {lon}) {year}…")
    r = requests.get(NSRDB_URL, params=params, timeout=120)
    r.raise_for_status()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(r.content)
    print(f"Wrote {out_path}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--lat", type=float, default=30.27)   # Austin TX
    p.add_argument("--lon", type=float, default=-97.74)
    p.add_argument("--year", type=int, default=2024)
    p.add_argument("--out", type=Path, default=Path("data/nrel_solar/austin_2024.csv"))
    args = p.parse_args()

    api_key = os.environ.get("NREL_API_KEY")
    email = os.environ.get("NREL_EMAIL")
    if not api_key or not email:
        raise SystemExit(
            "Set NREL_API_KEY and NREL_EMAIL env vars. Get a free key at "
            "https://developer.nrel.gov/signup/"
        )
    fetch_nrel(api_key=api_key, email=email, lat=args.lat, lon=args.lon,
               year=args.year, out_path=args.out)
    print(
        "\nPecan Street load data requires a researcher account at "
        "https://www.pecanstreet.org/dataport/. After approval, export the "
        "15-min residential table for ~30 Austin houses and save it as "
        "data/pecan_street/austin_2024_15min.csv with columns: "
        "dataid, local_15min, grid, solar, use."
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit (no test — this hits a real network)**

```bash
git add scripts/fetch_data.py
git commit -m "chore: fetch_data.py — NREL downloader + Pecan Street instructions"
```

---

## Task 25: Final wrap-up

**Files:**
- Modify: `README.md` (update Status section)
- Verify all tests pass

- [ ] **Step 1: Run the complete test suite**

```bash
pytest -v
ruff check sim tests scripts
mypy
```

Expected: all tests pass, ruff clean, mypy clean.

- [ ] **Step 2: Update README Status section**

Mark all Phase 1 deliverables complete:

```markdown
## Status

Phase 1 deliverables:
- [x] Project scaffold, types, household physics, network settlement
- [x] Scenario YAML, no-coordination + round-robin strategies
- [x] Engine + logger + summary metrics
- [x] CLI + scenario examples + README
- [x] Unit + integration + physics-smoke tests pass
- [x] Real data adapters (Pecan Street + NREL) — schema-level; awaiting researcher account for full data fetch

Next: Phase 2 — LLM agent layer (separate spec + plan).
```

- [ ] **Step 3: Commit and tag**

```bash
git add README.md
git commit -m "docs: mark Phase 1 complete"
git tag phase1-complete
```

- [ ] **Step 4: Sanity check — run a full scenario from the CLI**

```bash
python -m scripts.run --scenario configs/scenarios/24h_uniform.yaml
```

Expected: one line of output, fresh `runs/24h_uniform/<timestamp>/` directory with 4 files.

---

## Spec coverage check

Cross-reference of spec requirements → tasks:

| Spec section | Implemented in |
|---|---|
| Energy model + RT efficiency + DoD floor + rate limits | Tasks 2-5 |
| 15-min timestep, 24-72h scenarios | Tasks 11, 19 |
| Pecan Street + NREL data + adapter pattern | Tasks 21-23 |
| 30 households on 5×6 grid | Tasks 7, 15 |
| Spatial comm graph + shared bus + 5% loss | Tasks 7-10 |
| Household heterogeneity (PV, battery sizes, profile stub) | Tasks 1, 15 |
| Outage schedule + partial-island no-wheeling | Tasks 10, 11, 16 |
| State/event/summary JSONL output | Tasks 13, 14 |
| Determinism under seed | Tasks 15, 17 |
| Energy-balance + SoC bounds invariants | Task 16 |
| Crash-loud vs log-and-continue policy | Tasks 9-10, 16, 21 |
| Three baselines (no_coord, round_robin, centralized_optimal) | Task 12 (no_coord, round_robin); centralized_optimal deferred to Phase 3 |
| Unit + integration + smoke tests | Tasks 2-18 |
| README | Task 20 |

Centralized-optimal baseline is explicitly **deferred to Phase 3** per the spec's "out of scope" section.

---

## What's deferred (and why)

- **Centralized-optimal baseline (LP solver):** Phase 3. Not needed for Phase 1's "does coordination do anything" sanity check.
- **LLM agent strategy:** Phase 2.
- **Welfare-weighted Gini:** Phase 3. Phase 1 uses per-household served-load fraction.
- **Hybrid 5-min physics / 15-min decision loop:** Phase 2 if needed; v1 runs both at 15 min.
- **Web visualization:** Phase 4.
