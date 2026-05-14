"""Physics smoke test: hand-computable scenario that catches battery-model regressions.

This is the "canary" test. The setup is intentionally simple so the expected
end state can be computed on paper:
  - PV = 2 kW peak per house, FlatSolar gives full peak all day -> solar = 2 kW
  - Load = constant 1 kW
  - Net surplus = 1 kW per house per tick
  - dt_hours = 0.25, eta = 1.0 (no RT loss), DoD floor = 0, battery oversized
  - 24 hours = 96 ticks * 1 kW * 0.25 h = 24 kWh net gain per house
  - Battery starts at 50% of 100 kWh = 50 kWh
  - Therefore end SoC must be exactly 74.0 kWh per house

If this test ever fails, the physics in sim/household.py:step() has regressed.
Do NOT 'fix' the test's expected number — fix the physics.
"""

from datetime import datetime, timedelta
from pathlib import Path

from sim.data import SyntheticLoad, SyntheticSolar
from sim.engine import run
from sim.logging import JsonlLogger
from sim.scenario import Scenario
from sim.strategies.no_coordination import decide_transfers


class FlatSolar(SyntheticSolar):
    """Solar that returns its full peak at every timestep, regardless of clock."""

    def get_kw(self, t: datetime) -> float:
        return 1.0  # normalized peak; engine multiplies by pv_kw_peak per house


def test_24h_constant_solar_load_balances(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Every house must end at exactly 74.0 kWh after 24 h of net +1 kW."""
    flat_solar = FlatSolar(peak_kw=1.0)
    flat_load = SyntheticLoad(base_kw=1.0)
    # Replace the constructors used inside sim.engine.run with no-op lambdas
    # that return the pre-built constants. This bypasses the half-sine /
    # default-1.5-kW configuration without changing engine code.
    monkeypatch.setattr("sim.engine.SyntheticSolar", lambda peak_kw: flat_solar)
    monkeypatch.setattr("sim.engine.SyntheticLoad", lambda base_kw: flat_load)

    s = Scenario(
        scenario_id="smoke",
        start=datetime(2024, 7, 1),
        end=datetime(2024, 7, 1) + timedelta(hours=24),
        dt_hours=0.25,
        seed=99,
        rows=2,
        cols=2,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
        strategy="no_coordination",
        data_source="synthetic",
        household_sampling={
            "pv_kw_peak": [2.0, 2.0],  # pin PV
            "battery_kwh": [100.0, 100.0],  # oversized; never hits capacity
            "rt_efficiency": 1.0,  # no RT loss
            "dod_floor_frac": 0.0,  # no DoD floor
            "grid_max_kw": 0.0,  # no grid backup
        },
        outages=(),
    )
    out = tmp_path / "smoke"
    logger = JsonlLogger(out, scenario_id="smoke")
    run(s, decide_transfers, logger, strict=True)
    logger.close()

    import json

    rows = [json.loads(line) for line in (out / "state.jsonl").read_text().splitlines()]
    last_per_house: dict[str, float] = {}
    for r in rows:
        last_per_house[r["house_id"]] = r["soc_kwh"]
    for hid, soc in last_per_house.items():
        assert abs(soc - 74.0) < 0.01, f"{hid}: expected 74.0 kWh, got {soc}"
