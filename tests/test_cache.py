"""PromptCache: content-addressed lookup, atomic writes, two-tier search order."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim.agents.cache import PromptCache, cache_key


def _req(user: str = "hello") -> dict:
    return {
        "model": "claude-haiku-4-5-20251001",
        "system": "you are a helpful assistant",
        "user": user,
        "temperature": 0.0,
        "max_tokens": 256,
        "tools_schema": [],
    }


def test_cache_key_deterministic() -> None:
    k1 = cache_key(_req())
    k2 = cache_key(_req())
    assert k1 == k2
    assert cache_key(_req("hi")) != k1


@pytest.mark.parametrize(
    ("field_name", "new_value"),
    [
        ("model", "claude-other-model-x"),
        ("system", "a completely different system prompt"),
        ("temperature", 0.7),
        ("max_tokens", 999),
        ("tools_schema", [{"name": "foo"}]),
    ],
)
def test_cache_key_changes_when_any_hashed_field_varies(field_name: str, new_value: object) -> None:
    """cache_key() hashes {model, system, user, temperature, max_tokens,
    tools_schema} (sim/agents/cache.py:27-40) — the only prior test isolated
    `user`. This guards each of the other four fields independently (C7-1):
    a future refactor that silently drops one of them from the hashed dict
    (e.g. max_tokens, which the 2026-07-17 judge-token-budget fix depended on
    being cache-key-significant) would otherwise collide two genuinely
    different requests onto the same cache entry undetected."""
    base = _req()
    varied = dict(base)
    varied[field_name] = new_value
    assert cache_key(varied) != cache_key(base)


def test_cache_miss_then_hit(tmp_path: Path) -> None:
    cache = PromptCache(local_dir=tmp_path / "local")
    req = _req()
    assert cache.get(req) is None
    cache.put(req, {"completion": "world"})
    got = cache.get(req)
    assert got == {"completion": "world"}


def test_cache_two_tier_lookup_local_wins(tmp_path: Path) -> None:
    """When both local and reference caches have the same key, local wins."""
    local = tmp_path / "local"
    ref = tmp_path / "ref"
    cache = PromptCache(local_dir=local, reference_dir=ref)
    req = _req()
    ref_cache = PromptCache(local_dir=ref)
    ref_cache.put(req, {"completion": "from-reference"})
    cache.put(req, {"completion": "from-local"})
    got = cache.get(req)
    assert got == {"completion": "from-local"}


def test_cache_falls_back_to_reference(tmp_path: Path) -> None:
    local = tmp_path / "local"
    ref = tmp_path / "ref"
    cache = PromptCache(local_dir=local, reference_dir=ref)
    req = _req()
    PromptCache(local_dir=ref).put(req, {"completion": "from-reference"})
    got = cache.get(req)
    assert got == {"completion": "from-reference"}


def test_cache_writes_are_atomic(tmp_path: Path) -> None:
    cache = PromptCache(local_dir=tmp_path / "local")
    cache.put(_req(), {"completion": "x"})
    leftover = list((tmp_path / "local").rglob("*.tmp"))
    assert leftover == []


def test_cache_files_are_well_formed_json(tmp_path: Path) -> None:
    cache = PromptCache(local_dir=tmp_path / "local")
    cache.put(_req(), {"completion": "x"})
    files = list((tmp_path / "local").rglob("*.json"))
    assert len(files) == 1
    blob = json.loads(files[0].read_text())
    assert blob["response"] == {"completion": "x"}
    assert blob["model"] == "claude-haiku-4-5-20251001"
