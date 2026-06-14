"""FailureModeConfig defaults, deterministic defector assignment, NoiseSource, DefectorWrapper."""

from __future__ import annotations

from datetime import datetime

from sim.agents.failure_modes import (
    DefectorWrapper,
    FailureModeConfig,
    NoiseSource,
    ObsNoiseConfig,
    assign_defectors,
)
from sim.agents.protocol import Message


def test_failure_mode_defaults_are_clean_cell() -> None:
    cfg = FailureModeConfig()
    assert cfg.defector_fraction == 0.0
    assert cfg.defector_realization == "prompt"
    assert cfg.obs_noise.soc_std_frac == 0.0
    assert cfg.comm.per_tick_budget is None
    assert cfg.comm.drop_prob_by_circle == {}


def test_defector_assignment_deterministic() -> None:
    house_ids = [f"r{r}c{c}" for r in range(5) for c in range(6)]
    cfg = FailureModeConfig(defector_fraction=0.2, defector_assignment="random")
    a = assign_defectors(house_ids, cfg, scenario_seed=42)
    b = assign_defectors(house_ids, cfg, scenario_seed=42)
    assert a == b
    c = assign_defectors(house_ids, cfg, scenario_seed=43)
    assert a != c


def test_defector_assignment_manual_overrides() -> None:
    house_ids = [f"r{r}c{c}" for r in range(5) for c in range(6)]
    cfg = FailureModeConfig(
        defector_fraction=0.2,
        defector_assignment="manual",
        defector_house_ids=("r2c3", "r4c1"),
    )
    ids = assign_defectors(house_ids, cfg, scenario_seed=42)
    assert ids == {"r2c3", "r4c1"}


def test_defector_count_matches_fraction() -> None:
    house_ids = [f"h{i}" for i in range(30)]
    cfg = FailureModeConfig(defector_fraction=0.2, defector_assignment="random")
    ids = assign_defectors(house_ids, cfg, scenario_seed=0)
    assert len(ids) == 6


# --- NoiseSource tests ---


def test_noise_source_deterministic_per_seed() -> None:
    cfg = ObsNoiseConfig(soc_std_frac=0.1)
    ns_a = NoiseSource(cfg=cfg, scenario_seed=42)
    ns_b = NoiseSource(cfg=cfg, scenario_seed=42)
    seq_a = [
        ns_a.noise_soc(t_idx=i, house_id="r0c0", true_soc=10.0, capacity=20.0) for i in range(5)
    ]
    seq_b = [
        ns_b.noise_soc(t_idx=i, house_id="r0c0", true_soc=10.0, capacity=20.0) for i in range(5)
    ]
    assert seq_a == seq_b


def test_noise_source_zero_std_returns_true_value() -> None:
    cfg = ObsNoiseConfig(soc_std_frac=0.0, load_std_frac=0.0)
    ns = NoiseSource(cfg=cfg, scenario_seed=42)
    assert ns.noise_soc(t_idx=0, house_id="r0c0", true_soc=10.0, capacity=20.0) == 10.0
    assert ns.noise_load(t_idx=0, house_id="r0c0", true_load=2.5) == 2.5


def test_noise_source_respects_soc_bounds() -> None:
    """Noisy SoC must stay in [0, capacity] — never negative, never above capacity."""
    cfg = ObsNoiseConfig(soc_std_frac=10.0)
    ns = NoiseSource(cfg=cfg, scenario_seed=42)
    for i in range(200):
        noisy = ns.noise_soc(t_idx=i, house_id="r0c0", true_soc=5.0, capacity=10.0)
        assert 0.0 <= noisy <= 10.0


# --- DefectorWrapper tests ---


def test_defector_wrapper_passes_through_when_not_defector() -> None:
    wrap = DefectorWrapper(defectors=set(), scenario_seed=42)
    m = Message(
        t_sent=datetime(2026, 1, 1, 8, 0),
        sender="r0c0",
        recipient="r0c1",
        performative="OFFER",
        payload={"kwh": 0.5},
        rationale_nl="ok",
        correlation_id="x",
    )
    out = wrap.maybe_corrupt(m)
    assert out is m


def test_defector_wrapper_mutates_offered_kwh_for_defector() -> None:
    wrap = DefectorWrapper(defectors={"r0c0"}, scenario_seed=42)
    m = Message(
        t_sent=datetime(2026, 1, 1, 8, 0),
        sender="r0c0",
        recipient="r0c1",
        performative="OFFER",
        payload={"kwh": 1.0},
        rationale_nl="ok",
        correlation_id="x",
    )
    out = wrap.maybe_corrupt(m)
    assert out is not m
    assert out.payload["kwh"] != 1.0
    ratio = out.payload["kwh"] / 1.0
    assert 0.5 <= ratio <= 1.5


def test_defector_wrapper_deterministic_given_seed() -> None:
    a = DefectorWrapper(defectors={"r0c0"}, scenario_seed=42)
    b = DefectorWrapper(defectors={"r0c0"}, scenario_seed=42)
    m = Message(
        t_sent=datetime(2026, 1, 1, 8, 0),
        sender="r0c0",
        recipient="r0c1",
        performative="OFFER",
        payload={"kwh": 1.0},
        rationale_nl="ok",
        correlation_id="x",
    )
    out_a = [a.maybe_corrupt(m).payload["kwh"] for _ in range(5)]
    out_b = [b.maybe_corrupt(m).payload["kwh"] for _ in range(5)]
    assert out_a == out_b
