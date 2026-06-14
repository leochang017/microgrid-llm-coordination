"""LLMClient abstract + MockLLMClient. AnthropicLLMClient tests are appended in Task 7."""

from __future__ import annotations

import pytest

from sim.agents.cache import PromptCache
from sim.agents.llm import LLMRequest, LLMResponse, MockLLMClient, NoMockResponseError


def test_mock_returns_canned_response(tmp_path) -> None:
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={
            "hello": LLMResponse(text="world", tokens_in=5, tokens_out=1),
        },
    )
    req = LLMRequest(
        model="claude-haiku-4-5-20251001",
        system="sys",
        user="hello",
        max_tokens=64,
    )
    resp = mock.call(req)
    assert resp.text == "world"


def test_mock_raises_on_unrecognized_prompt(tmp_path) -> None:
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={"hello": LLMResponse(text="world", tokens_in=5, tokens_out=1)},
    )
    req = LLMRequest(
        model="claude-haiku-4-5-20251001",
        system="sys",
        user="surprise!",
        max_tokens=64,
    )
    with pytest.raises(NoMockResponseError, match="surprise"):
        mock.call(req)


def test_mock_uses_cache(tmp_path) -> None:
    """First call hits the mock; second identical call hits the cache and the mock would refuse."""
    cache = PromptCache(local_dir=tmp_path)
    mock = MockLLMClient(
        cache=cache,
        canned={"hello": LLMResponse(text="world", tokens_in=5, tokens_out=1)},
    )
    req = LLMRequest(
        model="claude-haiku-4-5-20251001",
        system="sys",
        user="hello",
        max_tokens=64,
    )
    first = mock.call(req)
    mock.canned.clear()
    second = mock.call(req)
    assert first.text == second.text == "world"


def test_mock_substring_match_is_supported(tmp_path) -> None:
    """For agent prompt tests, we match by substring in the user prompt — exact match is too brittle for evolving prompts."""
    mock = MockLLMClient(
        cache=PromptCache(local_dir=tmp_path),
        canned={"greet": LLMResponse(text="hi", tokens_in=2, tokens_out=1)},
    )
    req = LLMRequest(
        model="claude-haiku-4-5-20251001",
        system="sys",
        user="please greet the user warmly",
        max_tokens=64,
    )
    resp = mock.call(req)
    assert resp.text == "hi"
