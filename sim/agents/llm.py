"""LLMClient abstractions.

This module ships:
- ``LLMRequest`` / ``LLMResponse`` — provider-neutral data shapes
- ``LLMClient`` — abstract base with cache integration
- ``MockLLMClient`` — substring-keyed canned-response client for tests
- ``AnthropicLLMClient`` — real Claude API adapter (Task 7)

Cache integration is in the base class: every call routes through
``self.cache.get(...)`` and ``self.cache.put(...)``. Subclasses only implement
``_call_provider(req)`` for actual API I/O.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import anthropic
import httpx

from sim.agents.cache import PromptCache

# The SDK defaults to read=600 s, so one wedged HTTPS read costs 10 min before
# this module's retry loop sees an exception. Measured across Phase 3.2 Stage 1
# (2026-07-15): 4 hung reads cost 82 min of a 228 min run (36%). 60 s is ~10x the
# observed p99 for an 800-token Haiku call, so it never abandons a healthy
# request — which matters, because a client-side abort still bills server-side.
# Erring long is the safe direction; erring at 600 s was just expensive.
# The SDK's own max_retries is pinned to 0 below for the same reason: this class
# already retries (see AnthropicLLMClient.max_retries), and nesting the SDK's
# default 2 inside our 5 means 15 attempts at a known-dead endpoint, with the
# inner ones invisible to base_backoff_s.
_TIMEOUT = httpx.Timeout(60.0, connect=5.0)


class NoMockResponseError(LookupError):
    """Raised when MockLLMClient receives a prompt it has no canned response for."""


@dataclass(frozen=True)
class LLMRequest:
    model: str
    system: str
    user: str
    max_tokens: int
    temperature: float = 0.0
    tools_schema: list[dict[str, Any]] = field(default_factory=list)

    def to_cache_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "system": self.system,
            "user": self.user,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "tools_schema": self.tools_schema,
        }


@dataclass(frozen=True)
class LLMResponse:
    text: str
    tokens_in: int
    tokens_out: int
    # When tool-use is requested (LLMRequest.tools_schema non-empty), this
    # carries the parsed input dict of the model's tool call. None otherwise.
    tool_input: dict[str, Any] | None = None


@dataclass
class LLMClient:
    """Abstract base. Subclasses implement ``_call_provider``."""

    cache: PromptCache
    # Fresh-call token totals (cache hits are free); feed cost accounting.
    n_fresh_tokens_in: int = 0
    n_fresh_tokens_out: int = 0

    def call(self, req: LLMRequest) -> LLMResponse:
        cache_req = req.to_cache_dict()
        cached = self.cache.get(cache_req)
        if cached is not None:
            return LLMResponse(
                text=cached["text"],
                tokens_in=int(cached.get("tokens_in", 0)),
                tokens_out=int(cached.get("tokens_out", 0)),
                tool_input=cached.get("tool_input"),
            )
        resp = self._call_provider(req)
        self.n_fresh_tokens_in += resp.tokens_in
        self.n_fresh_tokens_out += resp.tokens_out
        self.cache.put(
            cache_req,
            {
                "text": resp.text,
                "tokens_in": resp.tokens_in,
                "tokens_out": resp.tokens_out,
                "tool_input": resp.tool_input,
            },
        )
        return resp

    def _call_provider(self, req: LLMRequest) -> LLMResponse:  # pragma: no cover
        raise NotImplementedError


@dataclass
class MockLLMClient(LLMClient):
    """Returns canned responses keyed by a substring of the user prompt.

    Substring matching is more robust for evolving prompts than exact match.
    First key whose substring appears in ``req.user`` wins (deterministic dict order).
    """

    canned: dict[str, LLMResponse] = field(default_factory=dict)

    def _call_provider(self, req: LLMRequest) -> LLMResponse:
        for key, resp in self.canned.items():
            if key in req.user:
                return resp
        raise NoMockResponseError(
            f"no canned response matches user prompt: {req.user[:80]!r} "
            f"(canned keys: {sorted(self.canned)})"
        )


@dataclass
class AnthropicLLMClient(LLMClient):
    """Anthropic Claude API adapter. Temperature is forced to 0.0.

    Retries on RateLimitError (429), APIConnectionError, and 5xx via
    exponential backoff. The cache hit-path is inherited from ``LLMClient``,
    so a cache hit never touches the network.
    """

    api_key: str = ""
    max_retries: int = 5
    base_backoff_s: float = 1.0
    _sdk_client: anthropic.Anthropic | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self._sdk_client is None:
            # OAuth access tokens (sk-ant-oat01-…) authenticate via the
            # Authorization: Bearer header; regular API keys (sk-ant-api…) use
            # x-api-key. The Anthropic SDK exposes both via separate kwargs.
            key = self.api_key or None
            if key and key.startswith("sk-ant-oat"):
                self._sdk_client = anthropic.Anthropic(
                    auth_token=key, timeout=_TIMEOUT, max_retries=0, api_key=""
                )
            else:
                self._sdk_client = anthropic.Anthropic(api_key=key, timeout=_TIMEOUT, max_retries=0)

    def _call_provider(self, req: LLMRequest) -> LLMResponse:
        last_exc: Exception | None = None
        # If a tool schema is provided, force the model to call the (first)
        # tool. This is how we eliminate the 41% policy-parse failure rate
        # observed in the Phase 2.5 reference run — structured output via
        # tool-use is schema-validated by the API itself, so the response is
        # always parseable.
        extra_kwargs: dict[str, Any] = {}
        if req.tools_schema:
            extra_kwargs["tools"] = req.tools_schema
            tool_name = req.tools_schema[0]["name"]
            extra_kwargs["tool_choice"] = {"type": "tool", "name": tool_name}

        for attempt in range(self.max_retries):
            try:
                assert self._sdk_client is not None
                msg = self._sdk_client.messages.create(
                    model=req.model,
                    max_tokens=req.max_tokens,
                    temperature=0.0,
                    system=req.system,
                    messages=[{"role": "user", "content": req.user}],
                    **extra_kwargs,
                )
                text = "".join(getattr(b, "text", "") for b in msg.content)
                tool_input: dict[str, Any] | None = None
                for b in msg.content:
                    if getattr(b, "type", None) == "tool_use":
                        raw = getattr(b, "input", None)
                        if isinstance(raw, dict):
                            tool_input = raw
                        break
                return LLMResponse(
                    text=text,
                    tokens_in=int(msg.usage.input_tokens),
                    tokens_out=int(msg.usage.output_tokens),
                    tool_input=tool_input,
                )
            except (
                anthropic.RateLimitError,
                anthropic.APIConnectionError,
                anthropic.InternalServerError,
            ) as e:
                last_exc = e
                sleep_s = self.base_backoff_s * (2**attempt)
                time.sleep(sleep_s)
        assert last_exc is not None
        raise last_exc
