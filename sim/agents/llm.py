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

from dataclasses import dataclass, field
from typing import Any

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
