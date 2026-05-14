"""Shared test fixtures."""
import numpy as np
import pytest


@pytest.fixture
def rng() -> np.random.Generator:
    """A deterministic RNG seeded the same way for every test."""
    return np.random.default_rng(seed=42)
