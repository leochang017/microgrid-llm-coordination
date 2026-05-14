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
