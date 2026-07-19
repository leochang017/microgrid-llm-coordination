"""Policy schema: defaults, validator, YAML round-trip, fallback behavior."""

from __future__ import annotations

import pytest

from sim.agents.policy import Policy, PolicyValidationError, policy_from_yaml


def _valid_policy_dict() -> dict:
    return {
        "sharing_intent": "balanced",
        "share_min_soc_frac": 0.50,
        "max_share_kw_per_tick": 1.5,
        "recipient_priority": [
            {"circle": "owner", "weight": 1.0},
            {"circle": "geographic", "weight": 0.4},
        ],
        "distrusted_peers": [],
        "request_urgency": "normal",
        "belief_note": "no strong beliefs yet",
        "ttl_ticks": 4,
    }


def test_policy_from_yaml_parses() -> None:
    yaml_str = """\
sharing_intent: balanced
share_min_soc_frac: 0.5
max_share_kw_per_tick: 1.5
recipient_priority:
- circle: owner
  weight: 1.0
- circle: geographic
  weight: 0.4
distrusted_peers: []
request_urgency: normal
belief_note: no strong beliefs yet
ttl_ticks: 4
share_fraction_per_tick: 0.05
"""
    p = policy_from_yaml(yaml_str)
    assert p.sharing_intent == "balanced"
    assert p.share_min_soc_frac == 0.5
    assert p.recipient_priority[0].circle == "owner"
    assert p.recipient_priority[0].weight == 1.0
    assert p.distrusted_peers == ()
    assert p.ttl_ticks == 4


def test_policy_rejects_negative_weight() -> None:
    d = _valid_policy_dict()
    d["recipient_priority"][0]["weight"] = -0.5
    with pytest.raises(PolicyValidationError, match="weight"):
        Policy.from_dict(d)


def test_policy_rejects_nan_weight() -> None:
    """C3-3: float('nan') < 0 is False, so a bare '< 0' check lets NaN through.
    Reachable only via the free-text YAML fallback (yaml 1.1 accepts .nan)."""
    d = _valid_policy_dict()
    d["recipient_priority"][0]["weight"] = float("nan")
    with pytest.raises(PolicyValidationError, match="weight"):
        Policy.from_dict(d)


def test_policy_rejects_inf_weight() -> None:
    d = _valid_policy_dict()
    d["recipient_priority"][0]["weight"] = float("inf")
    with pytest.raises(PolicyValidationError, match="weight"):
        Policy.from_dict(d)


def test_policy_accepts_normal_weight() -> None:
    d = _valid_policy_dict()
    d["recipient_priority"][0]["weight"] = 0.75
    p = Policy.from_dict(d)
    assert p.recipient_priority[0].weight == 0.75


def test_policy_rejects_ttl_zero() -> None:
    d = _valid_policy_dict()
    d["ttl_ticks"] = 0
    with pytest.raises(PolicyValidationError, match="ttl_ticks"):
        Policy.from_dict(d)


def test_policy_rejects_unknown_sharing_intent() -> None:
    d = _valid_policy_dict()
    d["sharing_intent"] = "ravenous"
    with pytest.raises(PolicyValidationError, match="sharing_intent"):
        Policy.from_dict(d)


def test_policy_rejects_bad_request_urgency() -> None:
    d = _valid_policy_dict()
    d["request_urgency"] = "panic"
    with pytest.raises(PolicyValidationError, match="request_urgency"):
        Policy.from_dict(d)


def test_policy_default_round_robin_fallback() -> None:
    fb = Policy.default_round_robin_fallback()
    assert fb.sharing_intent == "balanced"
    assert fb.share_min_soc_frac > 0.0
    assert any(rp.circle == "geographic" for rp in fb.recipient_priority)
    assert fb.ttl_ticks >= 1


def test_policy_is_frozen() -> None:
    p = Policy.from_dict(_valid_policy_dict())
    with pytest.raises((AttributeError, TypeError)):
        p.share_min_soc_frac = 0.9  # type: ignore[misc]


def _valid() -> dict:
    return {
        "sharing_intent": "balanced",
        "share_min_soc_frac": 0.3,
        "max_share_kw_per_tick": 4.0,
        "recipient_priority": [{"circle": "geographic", "weight": 1.0}],
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("share_min_soc_frac", 30),
        ("share_min_soc_frac", 1.01),
        ("max_share_kw_per_tick", 101.0),
        ("max_share_kw_per_tick", -1.0),
        ("share_fraction_per_tick", -0.5),
        ("share_fraction_per_tick", 5.0),
    ],
)
def test_policy_bounds_rejected(field: str, value: float) -> None:
    d = _valid()
    d[field] = value
    with pytest.raises(PolicyValidationError, match=field):
        Policy.from_dict(d)


def test_policy_boundary_values_accepted() -> None:
    d = _valid()
    d["share_min_soc_frac"] = 1.0
    d["share_fraction_per_tick"] = 1.0
    Policy.from_dict(d)
