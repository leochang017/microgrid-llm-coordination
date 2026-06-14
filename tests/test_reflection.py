"""Reflection: given recent memories, produces belief statements appended to MemoryStream."""

from __future__ import annotations

from datetime import datetime, timedelta

from sim.agents.cache import PromptCache
from sim.agents.llm import LLMResponse, MockLLMClient
from sim.agents.memory import MemoryEntry, MemoryStream
from sim.agents.reflection import Reflection


def test_reflection_parses_mock_response_into_memories(tmp_path) -> None:
    canned_json = (
        "Beliefs:\n"
        '[{"belief": "peer r2c3 refused 4/4 requests", "importance": 9.0},'
        ' {"belief": "owner-group reciprocated 3/3 offers", "importance": 8.0}]'
    )
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={
            "Reflect on the recent observations": LLMResponse(
                text=canned_json, tokens_in=200, tokens_out=80
            ),
        },
    )
    refl = Reflection(client=mock, model="claude-haiku-4-5-20251001")
    mem = MemoryStream()
    t0 = datetime(2026, 1, 1, 8, 0)
    mem.append(MemoryEntry(t=t0, kind="obs", content={}, nl="my SoC is 6.0/10", importance=3.0))

    new_beliefs = refl.reflect(
        mem,
        now=t0 + timedelta(hours=1),
        house_id="r0c0",
        trust_circles={"owner": "owner_acme"},
    )
    assert len(new_beliefs) == 2
    assert new_beliefs[0].kind == "reflection"
    assert "r2c3" in new_beliefs[0].nl
    assert new_beliefs[0].importance >= 7.0


def test_reflection_handles_unparseable_response_gracefully(tmp_path) -> None:
    """If the LLM returns garbage, reflection returns no new beliefs."""
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={"Reflect on": LLMResponse(text="i am a teapot", tokens_in=10, tokens_out=5)},
    )
    refl = Reflection(client=mock, model="claude-haiku-4-5-20251001")
    mem = MemoryStream()
    mem.append(MemoryEntry(t=datetime(2026, 1, 1), kind="obs", content={}, nl="x", importance=1.0))
    new_beliefs = refl.reflect(
        mem, now=datetime(2026, 1, 1, 9, 0), house_id="r0c0", trust_circles={}
    )
    assert new_beliefs == []


def test_reflection_includes_trust_circles_in_prompt(tmp_path) -> None:
    """The reflection prompt must surface the agent's trust-circle membership by name."""
    captured: dict[str, str] = {}

    class _Capture(MockLLMClient):
        def _call_provider(self, req):  # type: ignore[no-untyped-def]
            captured["user"] = req.user
            return LLMResponse(text="[]", tokens_in=1, tokens_out=1)

    refl = Reflection(
        client=_Capture(
            cache=PromptCache(local_dir=tmp_path),
            canned={"": LLMResponse(text="", tokens_in=0, tokens_out=0)},
        ),
        model="claude-haiku-4-5-20251001",
    )
    refl.reflect(
        MemoryStream(),
        now=datetime(2026, 1, 1, 9, 0),
        house_id="r0c0",
        trust_circles={"owner": "owner_acme", "hoa": "hoa_north"},
    )
    assert "owner_acme" in captured["user"]
    assert "hoa_north" in captured["user"]
