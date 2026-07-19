"""Dotted-key scenario overrides for dose-response sweeps (Phase 3 Task 9).

`apply_overrides(scenario, ["failure_modes.defector_fraction=0.4", ...])`
returns a new Scenario with the given fields replaced. Paths walk Scenario
fields, nested frozen dataclasses (failure_modes, failure_modes.obs_noise,
failure_modes.comm), and plain dicts (household_sampling, llm, data_paths).
Values are YAML-coerced (`0.4` -> float, `null` -> None, `[1,2]` -> list).

Unknown keys are a HARD ERROR — a typo'd sweep axis must never silently run
the base scenario and report it as a treated cell.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import yaml

from sim.scenario import _KNOWN_LLM_KEYS, Scenario

# Known-key sets for the plain-dict Scenario fields, applied to the FINAL leaf
# segment of an override path targeting them (e.g. "llm.react_max_per_tick").
# `None` means "no fixed known-set" (household_sampling's keys are
# mode-dependent, mirroring sim/scenario.py's deliberate non-strict load-time
# check) — for those, a leaf key is only accepted if it's already present in
# the scenario's current dict, so a typo can't add a silent dead key.
_DICT_FIELD_KNOWN_KEYS: dict[str, frozenset[str] | None] = {
    "llm": _KNOWN_LLM_KEYS,
    "household_sampling": None,
    "data_paths": None,
}


def _set_path(obj: Any, parts: list[str], value: Any, path_so_far: str) -> Any:
    key = parts[0]
    full = f"{path_so_far}{key}"
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        names = {f.name for f in dataclasses.fields(obj)}
        if key not in names:
            raise ValueError(f"unknown override key {full!r} (valid: {sorted(names)})")
        if len(parts) == 1:
            return dataclasses.replace(obj, **{key: value})
        child = getattr(obj, key)
        if isinstance(child, dict) and len(parts) == 2 and key in _DICT_FIELD_KNOWN_KEYS:
            leaf = parts[1]
            known = _DICT_FIELD_KNOWN_KEYS[key]
            allowed = known if known is not None else set(child)
            if leaf not in allowed:
                raise ValueError(f"unknown override key {full}.{leaf!r} (valid: {sorted(allowed)})")
        return dataclasses.replace(obj, **{key: _set_path(child, parts[1:], value, full + ".")})
    if isinstance(obj, dict):
        new = dict(obj)
        if len(parts) == 1:
            new[key] = value
            return new
        if key not in new or not isinstance(new[key], dict):
            raise ValueError(f"unknown override key {full!r} in mapping")
        new[key] = _set_path(new[key], parts[1:], value, full + ".")
        return new
    raise ValueError(f"cannot descend into {full!r} (parent is {type(obj).__name__})")


def apply_overrides(scenario: Scenario, sets: list[str]) -> Scenario:
    """Apply `key.path=value` overrides; returns a new Scenario."""
    for spec in sets:
        if "=" not in spec:
            raise ValueError(f"override must look like key.path=value, got {spec!r}")
        path, _, raw = spec.partition("=")
        parts = [p for p in path.strip().split(".") if p]
        if not parts:
            raise ValueError(f"empty override path in {spec!r}")
        value = yaml.safe_load(raw)
        result = _set_path(scenario, parts, value, "")
        assert isinstance(result, Scenario)
        scenario = result
    return scenario
