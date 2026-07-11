"""Energy-conservation tests for the engine's transfer caps (Phase 2.9 Task 3).

Prior to 2026-07-06 the sender cap ignored the sender's own load (and put
sqrt(eta) on the wrong term), so settlement could credit receivers energy the
sender's step() never actually exported — energy created from nothing. The
receiver cap conversely clipped inbound transfers to battery-absorption limits
even though step() routes received energy straight to load (DC bypass). These
tests pin the corrected formulas:

  sender_cap   = max(0, (solar - load) + min(rate, avail/dt)*sqrt(eta) [+ grid_max if connected])
  receiver_cap = max(0, load - solar) + min(rate, headroom/(sqrt(eta)*dt))
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import pytest

from sim.engine import _transfer_caps, run
from sim.household import Household, HouseholdState, step
from sim.logging import JsonlLogger
from sim.scenario import OutageWindow, Scenario
from sim.types import HouseholdProfile, Transfer


def _house(*, battery_kwh: float, rate_kw: float, grid_max_kw: float = 10.0) -> Household:
    return Household(
        id="h",
        pv_kw_peak=0.0,
        battery_kwh=battery_kwh,
        battery_max_rate_kw=rate_kw,
        rt_efficiency=0.9,
        dod_floor_frac=0.1,
        grid_max_kw=grid_max_kw,
        profile=HouseholdProfile(description="test"),
    )


def _state(soc_kwh: float) -> HouseholdState:
    return HouseholdState(
        soc_kwh=soc_kwh, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False
    )


class TestTransferCaps:
    def test_sender_with_night_load_exceeding_deliverable_cannot_send(self) -> None:
        """Battery deliverable 0.76 kW < 1 kW own load -> nothing to spare."""
        h = _house(battery_kwh=4.0, rate_kw=0.8)
        send, _recv = _transfer_caps(
            h, _state(2.0), solar_kw=0.0, load_kw=1.0, connected=False, dt_hours=0.25
        )
        assert send == 0.0

    def test_sender_cap_derates_battery_rate_by_sqrt_eta(self) -> None:
        """No load: cap = min(rate, avail/dt) * sqrt(0.9), NOT the raw rate."""
        h = _house(battery_kwh=4.0, rate_kw=0.8)
        send, _recv = _transfer_caps(
            h, _state(2.0), solar_kw=0.0, load_kw=0.0, connected=False, dt_hours=0.25
        )
        assert send == pytest.approx(0.8 * math.sqrt(0.9), abs=1e-12)

    def test_sender_solar_surplus_passes_through_without_battery(self) -> None:
        """Solar 5 / load 1 with an empty battery: 4 kW exportable (DC bypass)."""
        h = _house(battery_kwh=4.0, rate_kw=0.8)
        send, _recv = _transfer_caps(
            h, _state(0.4), solar_kw=5.0, load_kw=1.0, connected=False, dt_hours=0.25
        )
        assert send == pytest.approx(4.0, abs=1e-12)

    def test_connected_sender_adds_grid_capacity(self) -> None:
        h = _house(battery_kwh=4.0, rate_kw=0.8, grid_max_kw=10.0)
        send, _recv = _transfer_caps(
            h, _state(2.0), solar_kw=0.0, load_kw=0.0, connected=True, dt_hours=0.25
        )
        assert send == pytest.approx(10.0 + 0.8 * math.sqrt(0.9), abs=1e-12)

    def test_full_battery_receiver_with_load_can_still_receive(self) -> None:
        """Received energy serving load directly needs no battery headroom."""
        h = _house(battery_kwh=0.4, rate_kw=0.08)
        _send, recv = _transfer_caps(
            h, _state(0.4), solar_kw=0.0, load_kw=1.0, connected=False, dt_hours=0.25
        )
        assert recv == pytest.approx(1.0, abs=1e-12)  # headroom term is 0

    def test_receiver_cap_battery_term_matches_charge_leg(self) -> None:
        """No load: cap = min(rate, headroom/(sqrt(eta)*dt)) exactly as before."""
        h = _house(battery_kwh=4.0, rate_kw=0.8)
        _send, recv = _transfer_caps(
            h, _state(2.0), solar_kw=0.0, load_kw=0.0, connected=False, dt_hours=0.25
        )
        assert recv == pytest.approx(0.8, abs=1e-12)  # rate binds (headroom ample)


def _scenario() -> Scenario:
    """1x2 islanded synthetic scenario, 1 h horizon (4 ticks at dt=0.25).

    Both houses: 4 kWh battery (rate 0.8 kW), 1.0 kW load, no solar. Battery
    deliverable power is min(0.8, avail/dt)*sqrt(0.9) ~= 0.76 kW < load, so
    neither house ever has spare energy to send.
    """
    return Scenario(
        scenario_id="conservation_test",
        start=datetime(2026, 7, 1, 0, 0),
        end=datetime(2026, 7, 1, 1, 0),
        dt_hours=0.25,
        seed=1,
        rows=1,
        cols=2,
        bus_max_kw=50.0,
        bus_loss_factor=0.05,
        strategy="scripted",
        data_source="synthetic",
        household_sampling={
            "pv_kw_peak": [0.0, 0.0],
            "battery_kwh": [4.0, 4.0],
            "rt_efficiency": 0.9,
            "dod_floor_frac": 0.1,
            "synthetic_load_kw": 1.0,
        },
        outages=(
            OutageWindow(
                start=datetime(2026, 7, 1, 0, 0),
                end=datetime(2026, 7, 1, 1, 0),
                affected_houses=("r0c0", "r0c1"),
            ),
        ),
    )


def _run(scenario: Scenario, decide, out_dir: Path) -> dict[str, float]:  # type: ignore[no-untyped-def]
    logger = JsonlLogger(out_dir, scenario_id=scenario.scenario_id)
    summary = run(scenario, decide, logger, strict=True)
    logger.close()
    return summary


def _greedy(t, states, households, solar, load, grid, nbhd, dt):  # type: ignore[no-untyped-def]
    return [Transfer(from_id="r0c0", to_id="r0c1", kw=0.5)]


def _none(t, states, households, solar, load, grid, nbhd, dt):  # type: ignore[no-untyped-def]
    return []


def test_transfers_cannot_create_energy(tmp_path: Path) -> None:
    """A sender that can't cover its own load must not improve system totals.

    Pre-fix, the scripted 0.5 kW transfer passed settlement (old cap ignored
    load), the sender's export was silently cut by step()'s safety net, and the
    receiver kept full credit -> served_load_fraction rose out of thin air.
    """
    sc = _scenario()
    with_transfers = _run(sc, _greedy, tmp_path / "with")
    without = _run(sc, _none, tmp_path / "without")

    assert with_transfers["served_load_fraction"] == pytest.approx(
        without["served_load_fraction"], abs=1e-9
    )
    assert with_transfers["unmet_kwh_total"] == pytest.approx(without["unmet_kwh_total"], abs=1e-9)


def test_system_net_export_never_negative(tmp_path: Path) -> None:
    """Per tick, sum of achieved net exports = bus losses >= 0.

    A negative system total means somebody was credited energy nobody sourced
    (the pre-fix signature: sender cut to 0, receiver still at -0.475 kW).
    """
    _run(_scenario(), _greedy, tmp_path / "run")
    rows = [json.loads(x) for x in (tmp_path / "run" / "state.jsonl").read_text().splitlines()]
    by_tick: dict[str, float] = {}
    for r in rows:
        by_tick[r["t"]] = by_tick.get(r["t"], 0.0) + r["achieved_net_export_kw"]
    for t, net in by_tick.items():
        assert net >= -1e-9, f"phantom energy at {t}: system net export {net}"


def _solar_receiver_house() -> Household:
    return Household(
        id="rx",
        pv_kw_peak=4.0,
        battery_kwh=10.0,
        battery_max_rate_kw=2.0,
        rt_efficiency=0.9,
        dod_floor_frac=0.0,
        grid_max_kw=10.0,
        profile=HouseholdProfile(description="t", critical_load_frac=0.0),
    )


def test_receiver_cap_subtracts_own_solar_surplus() -> None:
    """Own PV surplus competes for the same battery intake (household.step
    nets solar-load-transfers before storing), so the cap must exclude it."""
    h = _solar_receiver_house()
    s = HouseholdState(soc_kwh=5.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    # surplus 3 kW > 2 kW intake: nothing a peer sends can be used.
    _, recv = _transfer_caps(h, s, solar_kw=4.0, load_kw=1.0, connected=False, dt_hours=0.25)
    assert recv == pytest.approx(0.0)
    # surplus 0.5 kW leaves 1.5 kW of the 2 kW intake for peer energy.
    _, recv2 = _transfer_caps(h, s, solar_kw=1.5, load_kw=1.0, connected=False, dt_hours=0.25)
    assert recv2 == pytest.approx(1.5)


def test_solar_surplus_receiver_stores_exactly_what_the_cap_admits() -> None:
    """Receiving exactly the fixed cap wastes ONLY the sqrt(eta) conversion
    loss — zero curtailment. Under the old cap (2.0 kW) part of the delivered
    energy was silently curtailed."""
    h = _solar_receiver_house()
    s = HouseholdState(soc_kwh=5.0, last_solar_kw=0.0, last_load_kw=0.0, grid_connected=False)
    _, recv = _transfer_caps(h, s, solar_kw=1.5, load_kw=1.0, connected=False, dt_hours=0.25)
    new_s = step(
        h,
        s,
        solar_kw=1.5,
        load_kw=1.0,
        desired_net_export_kw=-recv,
        grid_status=False,
        dt_hours=0.25,
    )
    # surplus_kwh = (1.5 - 1.0 + 1.5) * 0.25 = 0.5; gross_in = 0.5 (rate-capped);
    # stored = 0.5 * sqrt(0.9) = 0.474342; waste = conversion loss only.
    assert new_s.soc_kwh == pytest.approx(5.0 + 0.5 * math.sqrt(0.9))
    assert new_s.wasted_kwh == pytest.approx(0.5 * (1 - math.sqrt(0.9)))
    assert new_s.unmet_kwh == 0.0
