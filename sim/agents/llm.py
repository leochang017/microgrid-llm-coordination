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

from sim.agents.cache import PromptCache


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


@dataclass
class LLMClient:
    """Abstract base. Subclasses implement ``_call_provider``."""

    cache: PromptCache

    def call(self, req: LLMRequest) -> LLMResponse:
        cache_req = req.to_cache_dict()
        cached = self.cache.get(cache_req)
        if cached is not None:
            return LLMResponse(
                text=cached["text"],
                tokens_in=int(cached.get("tokens_in", 0)),
                tokens_out=int(cached.get("tokens_out", 0)),
            )
        resp = self._call_provider(req)
        self.cache.put(
            cache_req,
            {"text": resp.text, "tokens_in": resp.tokens_in, "tokens_out": resp.tokens_out},
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
            self._sdk_client = anthropic.Anthropic(api_key=self.api_key or None)

    def _call_provider(self, req: LLMRequest) -> LLMResponse:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                assert self._sdk_client is not None
                msg = self._sdk_client.messages.create(
                    model=req.model,
                    max_tokens=req.max_tokens,
                    temperature=0.0,
                    system=req.system,
                    messages=[{"role": "user", "content": req.user}],
                )
                text = "".join(getattr(b, "text", "") for b in msg.content)
                return LLMResponse(
                    text=text,
                    tokens_in=int(msg.usage.input_tokens),
                    tokens_out=int(msg.usage.output_tokens),
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
