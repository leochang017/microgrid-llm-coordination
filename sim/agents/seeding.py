"""Process-stable RNG seeding for the agent layer.

Python's built-in ``hash()`` on strings is salted by PYTHONHASHSEED, which is
randomized per process — so any RNG seeded via ``hash((seed, "label", ...))``
produces DIFFERENT streams in different processes even with the same scenario
seed. That silently violated the project's byte-identical-determinism mandate
for everything cross-process: defector assignment, observation-noise draws,
bus dropout sequences, per-agent RNGs, and defector message corruption.
(In-process replay tests could never catch it; the flaky
test_bus_dropout_is_deterministic_given_seed fixed in e56941d was the first
symptom, discovered again 2026-07-07 via a per-process-flaky agent test.)

``stable_seed(*parts)`` hashes a canonical string with sha256 instead:
same inputs -> same 32-bit seed on every process, platform, and Python
version.
"""

from __future__ import annotations

import hashlib


def stable_seed(*parts: object) -> int:
    """A 32-bit seed derived deterministically from the given parts."""
    key = "|".join(repr(p) for p in parts).encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:4], "big")
