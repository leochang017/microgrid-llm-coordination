"""Task 1 (Phase 4b): the web-demo data export layer.

Every constant asserted here was measured off the committed artifacts, never
invented — the same house rule as ``tests/test_golden_numbers.py``.
"""

from __future__ import annotations

import itertools
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from scripts.export_demo_data import (
    DEMO_CELLS,
    build_explanations,
    build_houses,
    build_messages,
    build_ticks,
    export_cell,
    keep_message,
    load_jsonl,
    scenario_for,
    tick_times,
)
from sim.agents.failure_modes import assign_defectors

REPO = Path(__file__).resolve().parent.parent
CLEAN_DIR = REPO / "reference_runs" / "haves_havenots_solar__llm" / "llm_agent" / "clean__seed23"
COMM_DIR = REPO / "reference_runs" / "haves_havenots_solar__comm" / "llm_agent" / "comm__seed23"


def _clean_state() -> list[dict[str, Any]]:
    return load_jsonl(CLEAN_DIR / "state.jsonl")


def _tick_of(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {t: i for i, t in enumerate(tick_times(rows))}


def test_demo_cells_pins() -> None:
    assert DEMO_CELLS == {
        "clean": ("haves_havenots_solar__llm", 23),
        "defectors": ("haves_havenots_solar__defectors", 7),
        "noise": ("haves_havenots_solar__noise", 23),
        "comm": ("haves_havenots_solar__comm", 23),
    }


def test_tick_times() -> None:
    ts = tick_times(_clean_state())
    assert len(ts) == 96
    assert ts[0] == "2018-01-01T00:00:00"
    assert ts[-1] == "2018-01-01T23:45:00"
    assert all(a < b for a, b in itertools.pairwise(ts))


def test_build_houses_rederivation() -> None:
    state = _clean_state()
    houses = build_houses(scenario_for("clean"), state)
    assert len(houses) == 30
    assert houses[0]["id"] == "r0c0"
    assert houses[29]["id"] == "r4c5"
    assert [h["id"] for h in houses] == [f"r{r}c{c}" for r in range(5) for c in range(6)]
    for h in houses:
        assert h["have"] == (h["pvKwPeak"] > 0)
        assert h["defector"] is False

    max_soc: dict[str, float] = {}
    max_solar: dict[str, float] = {}
    for r in state:
        hid = r["house_id"]
        max_soc[hid] = max(max_soc.get(hid, 0.0), r["soc_kwh"])
        max_solar[hid] = max(max_solar.get(hid, 0.0), r["solar_kw"])
    for h in houses:
        assert h["batteryKwh"] >= max_soc[h["id"]] - 1e-9
        assert (max_solar[h["id"]] > 0.0) == h["have"]

    by_id = {h["id"]: h for h in houses}
    assert by_id["r0c0"]["circles"] == {"owner": "owner_a", "dr_aggregator": "agg_gridflex"}


def test_build_houses_defectors() -> None:
    scenario = scenario_for("defectors")
    state = load_jsonl(
        REPO
        / "reference_runs"
        / "haves_havenots_solar__defectors"
        / "llm_agent"
        / "defectors__seed7"
        / "state.jsonl"
    )
    houses = build_houses(scenario, state)
    assert sum(h["defector"] for h in houses) == 6
    expected = assign_defectors(
        sorted(h["id"] for h in houses), scenario.failure_modes, scenario.seed
    )
    assert {h["id"] for h in houses if h["defector"]} == expected


def test_keep_message_policy() -> None:
    rows = load_jsonl(CLEAN_DIR / "messages.jsonl")
    kept = [m for m in rows if keep_message(m)]
    assert len(kept) == 12258
    for m in kept:
        assert m["performative"] != "INFORM" or not m["templated"]
    built = build_messages(rows, _tick_of(_clean_state()))
    assert len(built["messages"]) == 12258
    assert "t_decided" not in json.dumps(built)


def _clean_messages() -> list[dict[str, Any]]:
    return build_messages(load_jsonl(CLEAN_DIR / "messages.jsonl"), _tick_of(_clean_state()))[
        "messages"
    ]


def test_message_ids_are_unique() -> None:
    """``id`` is what a keyed Svelte ``{#each}`` uses — duplicates crash at runtime."""
    msgs = _clean_messages()
    assert len({m["id"] for m in msgs}) == len(msgs)


def test_cid_is_a_shared_thread_id_not_a_unique_key() -> None:
    """Measured on clean@23: 12,258 rows, only 8,210 distinct correlation ids.

    A REQUEST and its ACCEPT/COUNTER/REJECT reply deliberately share one, which
    is how a negotiation thread is tracked — so ``cid`` must stay non-unique.
    """
    cids = [m["cid"] for m in _clean_messages()]
    assert len(cids) == 12258
    assert len(set(cids)) == 8210
    assert Counter(cids).most_common(1)[0][1] >= 2


def test_build_messages_comm_drops() -> None:
    rows = load_jsonl(COMM_DIR / "messages.jsonl")
    state = load_jsonl(COMM_DIR / "state.jsonl")
    tick_of = _tick_of(state)
    built = build_messages(rows, tick_of)
    dropped = [m for m in built["messages"] if m["outcome"] == "dropped"]
    assert len(dropped) > 0
    assert any(m["reason"] == "comm_drop" for m in dropped)

    events = load_jsonl(COMM_DIR / "events.jsonl")
    house_order = [f"r{r}c{c}" for r in range(5) for c in range(6)]
    ticks = build_ticks(state, events, rows, tick_of, house_order, dt_hours=0.25)
    inform_dropped = sum(ic["dropped"] for ic in ticks["informCounts"])
    assert inform_dropped + len(dropped) == 12692


def test_build_ticks_shapes_and_served_identity() -> None:
    state = _clean_state()
    events = load_jsonl(CLEAN_DIR / "events.jsonl")
    messages = load_jsonl(CLEAN_DIR / "messages.jsonl")
    house_order = [f"r{r}c{c}" for r in range(5) for c in range(6)]
    t = build_ticks(state, events, messages, _tick_of(state), house_order, dt_hours=0.25)
    assert len(t["socFrac"]) == 96
    assert len(t["socFrac"][0]) == 30
    assert all(0.0 <= v <= 1.001 for row in t["socFrac"] for v in row)
    assert len(t["transfers"][2]) >= 1
    assert t["servedFracCum"][-1] == pytest.approx(0.6725764138021589, abs=5e-5)


def test_build_explanations() -> None:
    obj = json.loads((CLEAN_DIR / "explanations_eval.json").read_text())
    expl = build_explanations(obj, _tick_of(_clean_state()))
    assert expl["means"] == {
        "state_accuracy": 3.03,
        "actionability": 4.05,
        "consistency": 4.46,
    }
    assert expl["nScored"] == 100
    assert len(expl["samples"]) == 100
    for s in expl["samples"]:
        assert set(s) == {"sender", "t", "stateAccuracy", "actionability", "consistency"}
        assert 0 <= s["t"] <= 95


def test_export_cell_integration(tmp_path: Path) -> None:
    export_cell("clean", tmp_path)
    out = tmp_path / "clean"
    names = ["meta.json", "ticks.json", "messages.json", "explanations.json"]
    for name in names:
        p = out / name
        assert p.exists(), name
        raw = p.read_text()
        assert raw.endswith("\n") and not raw.endswith("\n\n")
        assert p.stat().st_size < 15_000_000

    meta = json.loads((out / "meta.json").read_text())
    assert meta["live"]["served_load_fraction"] == 0.6725764138021589
    assert set(meta["baselines"]) == {
        "no_coordination",
        "llm_fallback",
        "round_robin",
        "lp_optimal",
    }
    assert 0 < meta["gapClosedControlToLp"] < 1
    assert meta["cleanSeedSpread"] == {
        "1": 0.8248454685184583,
        "7": 0.7963806526129852,
    }
    assert meta["outage"] == {
        "start": "2018-01-01T00:00:00",
        "end": "2018-01-02T00:00:00",
    }

    # ``export_cell`` overrides build_ticks' capacities with the re-derived
    # household values; without this the override path is unexercised (mutating
    # it to ``capacities=None`` left every other assertion green). Pins BOTH that
    # the override is wired and that the INFORM-derived fallback agrees with it.
    state = _clean_state()
    events = load_jsonl(CLEAN_DIR / "events.jsonl")
    messages = load_jsonl(CLEAN_DIR / "messages.jsonl")
    tick_of = _tick_of(state)
    order = [h["id"] for h in meta["houses"]]
    exact = {h["id"]: h["batteryKwh"] for h in meta["houses"]}
    with_exact = build_ticks(state, events, messages, tick_of, order, 0.25, capacities=exact)
    fallback = build_ticks(state, events, messages, tick_of, order, 0.25, capacities=None)
    assert with_exact["socFrac"] == json.loads((out / "ticks.json").read_text())["socFrac"]
    # socFrac ships rounded to 3 dp, so a sub-1e-6 real disagreement can still
    # straddle one 1e-3 grid step; the tolerance is that step, not more.
    for a, b in zip(with_exact["socFrac"], fallback["socFrac"], strict=True):
        for x, y in zip(a, b, strict=True):
            assert abs(x - y) <= 1e-3 + 1e-9
