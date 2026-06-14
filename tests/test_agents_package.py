"""Smoke check: the new sim/agents/ package is importable."""


def test_agents_package_importable() -> None:
    import sim.agents  # noqa: F401


def test_anthropic_dep_installed() -> None:
    """Anthropic SDK must resolve; otherwise live LLM calls (and Task 7) cannot work."""
    import anthropic

    assert hasattr(anthropic, "Anthropic")
