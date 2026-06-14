"""MemoryStream: append-only invariant, retrieval ranking, importance heuristics."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from sim.agents.memory import MemoryEntry, MemoryStream


def _entry(t: datetime, kind: str, importance: float, nl: str = "") -> MemoryEntry:
    return MemoryEntry(t=t, kind=kind, content={}, nl=nl, importance=importance)


def test_memory_stream_append_only() -> None:
    s = MemoryStream()
    t0 = datetime(2026, 1, 1, 8, 0)
    s.append(_entry(t0, "obs", 5.0))
    s.append(_entry(t0 + timedelta(minutes=15), "msg_recv", 7.0))
    assert len(s.entries) == 2
    with pytest.raises((AttributeError, TypeError)):
        s.entries.append(_entry(t0, "obs", 1.0))  # type: ignore[attr-defined]


def test_memory_top_k_ranks_recent_and_important() -> None:
    s = MemoryStream()
    t0 = datetime(2026, 1, 1, 8, 0)
    s.append(_entry(t0, "reflection", importance=10.0, nl="old reflection"))
    s.append(_entry(t0 + timedelta(hours=4), "obs", importance=2.0, nl="recent obs"))
    s.append(_entry(t0 + timedelta(hours=4), "reflection", importance=9.0, nl="recent reflection"))

    top = s.top_k(now=t0 + timedelta(hours=4), k=3)
    assert top[0].nl == "recent reflection"
    nls = [e.nl for e in top]
    assert nls.index("recent reflection") < nls.index("old reflection")


def test_memory_top_k_respects_k() -> None:
    s = MemoryStream()
    t0 = datetime(2026, 1, 1, 8, 0)
    for i in range(50):
        s.append(_entry(t0 + timedelta(minutes=i), "obs", importance=float(i), nl=f"e{i}"))
    top = s.top_k(now=t0 + timedelta(minutes=60), k=20)
    assert len(top) == 20
    assert any(e.nl == "e49" for e in top)


def test_memory_entry_is_frozen() -> None:
    e = _entry(datetime(2026, 1, 1), "obs", 5.0)
    with pytest.raises((AttributeError, TypeError)):
        e.importance = 10.0  # type: ignore[misc]


def test_memory_stream_jsonl_round_trip(tmp_path) -> None:
    s = MemoryStream()
    t0 = datetime(2026, 1, 1, 8, 0)
    s.append(_entry(t0, "obs", 3.0, nl="hello"))
    s.append(_entry(t0 + timedelta(minutes=15), "reflection", 8.0, nl="world"))
    path = tmp_path / "mem.jsonl"
    s.write_jsonl(path)
    loaded = MemoryStream.from_jsonl(path)
    assert len(loaded.entries) == 2
    assert loaded.entries[0].nl == "hello"
    assert loaded.entries[1].importance == 8.0
