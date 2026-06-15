"""LLMClient abstract + MockLLMClient + AnthropicLLMClient (Tasks 6, 7)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sim.agents.cache import PromptCache
from sim.agents.llm import (
    AnthropicLLMClient,
    LLMRequest,
    LLMResponse,
    MockLLMClient,
    NoMockResponseError,
)


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


# --- AnthropicLLMClient tests (Task 7) ---


def test_anthropic_client_calls_messages_create(tmp_path) -> None:
    fake_msg = MagicMock()
    fake_msg.content = [MagicMock(text="hello world")]
    fake_msg.usage = MagicMock(input_tokens=12, output_tokens=3)

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_msg

    with patch("sim.agents.llm.anthropic.Anthropic", return_value=fake_client):
        adapter = AnthropicLLMClient(
            cache=PromptCache(local_dir=tmp_path),
            api_key="sk-test",
        )
        req = LLMRequest(
            model="claude-haiku-4-5-20251001",
            system="sys",
            user="hi",
            max_tokens=64,
        )
        resp = adapter.call(req)

    assert resp.text == "hello world"
    assert resp.tokens_in == 12
    assert resp.tokens_out == 3
    kwargs = fake_client.messages.create.call_args.kwargs
    assert kwargs["temperature"] == 0.0
    assert kwargs["model"] == "claude-haiku-4-5-20251001"


def test_anthropic_client_retries_on_rate_limit(tmp_path) -> None:
    import anthropic as anthropic_sdk

    fake_msg = MagicMock()
    fake_msg.content = [MagicMock(text="ok")]
    fake_msg.usage = MagicMock(input_tokens=1, output_tokens=1)

    fake_client = MagicMock()
    err = anthropic_sdk.RateLimitError(
        message="slow down",
        response=MagicMock(status_code=429),
        body=None,
    )
    fake_client.messages.create.side_effect = [err, fake_msg]

    with (
        patch("sim.agents.llm.anthropic.Anthropic", return_value=fake_client),
        patch("sim.agents.llm.time.sleep") as sleeper,
    ):
        adapter = AnthropicLLMClient(
            cache=PromptCache(local_dir=tmp_path),
            api_key="sk-test",
            max_retries=3,
            base_backoff_s=0.1,
        )
        req = LLMRequest(
            model="claude-haiku-4-5-20251001",
            system="sys",
            user="hi",
            max_tokens=64,
        )
        resp = adapter.call(req)

    assert resp.text == "ok"
    assert fake_client.messages.create.call_count == 2
    sleeper.assert_called()


def test_anthropic_client_cache_hit_skips_api(tmp_path) -> None:
    cache = PromptCache(local_dir=tmp_path)
    req = LLMRequest(
        model="claude-haiku-4-5-20251001",
        system="sys",
        user="hi",
        max_tokens=64,
    )
    cache.put(req.to_cache_dict(), {"text": "cached", "tokens_in": 0, "tokens_out": 0})

    fake_client = MagicMock()
    with patch("sim.agents.llm.anthropic.Anthropic", return_value=fake_client):
        adapter = AnthropicLLMClient(cache=cache, api_key="sk-test")
        resp = adapter.call(req)

    assert resp.text == "cached"
    fake_client.messages.create.assert_not_called()


# --- Tool-use tests (Phase 2.6) ---


def test_anthropic_client_passes_tools_and_forces_tool_choice(tmp_path) -> None:
    """When LLMRequest.tools_schema is non-empty, the SDK call includes tools +
    tool_choice forcing the named tool."""
    fake_msg = MagicMock()
    fake_msg.content = []
    fake_msg.usage = MagicMock(input_tokens=1, output_tokens=1)
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_msg

    schema = {
        "name": "submit_policy",
        "description": "x",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    }

    with patch("sim.agents.llm.anthropic.Anthropic", return_value=fake_client):
        adapter = AnthropicLLMClient(
            cache=PromptCache(local_dir=tmp_path),
            api_key="sk-test",
        )
        req = LLMRequest(
            model="claude-haiku-4-5-20251001",
            system="sys",
            user="hi",
            max_tokens=64,
            tools_schema=[schema],
        )
        adapter.call(req)

    kwargs = fake_client.messages.create.call_args.kwargs
    assert kwargs["tools"] == [schema]
    assert kwargs["tool_choice"] == {"type": "tool", "name": "submit_policy"}


def test_anthropic_client_parses_tool_use_response_into_tool_input(tmp_path) -> None:
    """A response with a tool_use content block populates LLMResponse.tool_input."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.text = ""  # tool_use blocks carry no text content
    tool_block.input = {"sharing_intent": "balanced", "share_min_soc_frac": 0.5}

    fake_msg = MagicMock()
    fake_msg.content = [tool_block]
    fake_msg.usage = MagicMock(input_tokens=10, output_tokens=5)
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_msg

    with patch("sim.agents.llm.anthropic.Anthropic", return_value=fake_client):
        adapter = AnthropicLLMClient(
            cache=PromptCache(local_dir=tmp_path),
            api_key="sk-test",
        )
        req = LLMRequest(
            model="claude-haiku-4-5-20251001",
            system="sys",
            user="hi",
            max_tokens=64,
            tools_schema=[
                {
                    "name": "submit_policy",
                    "description": "x",
                    "input_schema": {"type": "object", "properties": {}, "required": []},
                }
            ],
        )
        resp = adapter.call(req)

    assert resp.tool_input == {"sharing_intent": "balanced", "share_min_soc_frac": 0.5}


def test_tool_input_round_trips_through_cache(tmp_path) -> None:
    """A cached tool_input dict is restored on the next call."""
    cache = PromptCache(local_dir=tmp_path)
    schema = {
        "name": "submit_policy",
        "description": "x",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    }
    req = LLMRequest(
        model="claude-haiku-4-5-20251001",
        system="sys",
        user="hi",
        max_tokens=64,
        tools_schema=[schema],
    )
    cache.put(
        req.to_cache_dict(),
        {
            "text": "",
            "tokens_in": 0,
            "tokens_out": 0,
            "tool_input": {"sharing_intent": "conservative"},
        },
    )

    fake_client = MagicMock()
    with patch("sim.agents.llm.anthropic.Anthropic", return_value=fake_client):
        adapter = AnthropicLLMClient(cache=cache, api_key="sk-test")
        resp = adapter.call(req)

    assert resp.tool_input == {"sharing_intent": "conservative"}
    fake_client.messages.create.assert_not_called()
