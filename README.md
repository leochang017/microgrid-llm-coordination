# Microgrid LLM Coordination

Research project: can a population of LLM agents, one per household, negotiate peer-to-peer to allocate scarce energy during a grid outage in a way that is fair across heterogeneous households, robust to incomplete or incorrect information, and explainable to residents?

The contribution is on the CS/ML axis (natural-language agent coordination, robustness, explainability), not the power-systems axis. Classical optimization handles fairness under strong assumptions, struggles with robustness, and does not attempt explainability. That gap is what this project explores.

## Status

🚧 **Pre-implementation.** Phase 1 spec and TDD plan are written; code lands as work progresses.

- Phase 1 — Simulator (in progress)
- Phase 2 — LLM agent layer (not started)
- Phase 3 — Benchmark & experiments (not started)
- Phase 4 — Web demo & paper writeup (not started)

## Repository layout

```
microgrid/
├── CLAUDE.md                       # Authoritative project context for collaborators
├── docs/superpowers/
│   ├── specs/                      # Per-phase design specs
│   └── plans/                      # Per-phase TDD implementation plans
├── sim/                            # (Phase 1) simulator package
├── tests/                          # Test suite
├── configs/scenarios/              # Scenario YAML files
└── scripts/                        # CLI runners, data fetchers
```

## Start here

1. **`CLAUDE.md`** — research question, four-phase plan, design decisions, conventions.
2. **`docs/superpowers/specs/2026-05-14-phase1-simulator-design.md`** — Phase 1 design.
3. **`docs/superpowers/plans/2026-05-14-phase1-simulator.md`** — Phase 1 task-by-task implementation plan.

## License

MIT — see [LICENSE](LICENSE).
