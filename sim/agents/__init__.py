"""Per-household LLM-agent layer for Phase 2.

Modules:
- ``policy``   — structured Policy + YAML round-trip + validator
- ``memory``   — append-only MemoryStream + top-K retrieval
- ``protocol`` — speech-act Message + MessageBus (queue / routing / dropout / budget)
- ``cache``    — content-addressed PromptCache (sha256, atomic, two-tier lookup)
- ``llm``      — abstract LLMClient + AnthropicLLMClient + MockLLMClient
- ``reflection`` — Park-adapted reflection LLM call wrapper
- ``failure_modes`` — FailureModeConfig + NoiseSource + DefectorWrapper
- ``agent``    — LLMAgent (observe / remember / plan / react / act)

Strategies plug in via ``sim.strategies.llm_agent``.
"""
