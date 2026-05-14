# Microgrid Project — Authoritative Context

> **Resume protocol for new sessions:** read this file first. The spec is the authoritative design; the plan is the authoritative TDD task list.

## Research question

Can a population of LLM agents, one per household, negotiate peer-to-peer to allocate scarce energy during a grid outage in a way that is **(a)** fair across heterogeneous households, **(b)** robust to incomplete or incorrect information, and **(c)** explainable to residents?

The contribution is on the **CS/ML axis** (natural-language agent coordination, robustness, explainability), not the power-systems axis. Classical optimization handles (a) under strong assumptions, struggles with (b), and does not attempt (c). That gap is the paper.

## Timeline + venue

- Started: 2026-05-14. Runway: summer + potentially the following school year (no fixed deadline).
- Target venues: ICLR Tackling Climate Change with ML workshop, NeurIPS Computational Sustainability, or AAMAS applied track. **Not** main NeurIPS — contribution isn't ML-methodological in the way they care about.

## Four-phase plan

| Phase | Weeks | Status | What it builds |
|-------|-------|--------|----------------|
| 1 — Simulator | 1-4 | **in progress** | Deterministic discrete-time microgrid sim, no agents |
| 2 — LLM agent layer | 5-8 | not started | Per-household LLM agent, natural-language P2P messaging |
| 3 — Benchmark & experiments | 9-14 | not started | Scenario suite + baselines + metrics (Gini, served-critical-load, explanation quality) |
| 4 — Web demo & paper writeup | 15-20 | not started | SvelteKit/Next.js visualization on Vercel + paper |

Each phase has its own spec + implementation plan in `docs/superpowers/`.

## Phase 1 status

- **Spec:** `docs/superpowers/specs/2026-05-14-phase1-simulator-design.md`
- **Plan:** `docs/superpowers/plans/2026-05-14-phase1-simulator.md` (26 tasks, TDD)
- **Approved:** 2026-05-14
- **Execution mode:** Inline (Claude executes tasks in-session, batched ~5 at a time with check-ins). Not subagent-driven — per project conventions, every line must be understood by the student.
- **Started executing:** 2026-05-14
- **Current position:** Task 12 next (strategies: no_coordination + round_robin). Tasks 0-11 complete — Scenario YAML loader + two example scenarios land.

### Progress log

Update this after every committed task. Newest entries on top.

| Date | Task | Commit | Tests | Note |
|------|------|--------|-------|------|
| 2026-05-14 | Task 11 — Scenario config | _(this commit)_ | 35 ✓ | `sim/scenario.py` with `OutageWindow` + `Scenario` dataclasses and `load_scenario(path)` YAML reader. `Scenario.timesteps()` iterates the simulation clock; `grid_status_at(t, house_id)` checks the outage schedule. Ships `configs/scenarios/synthetic_smoke.yaml` (24 h, no outage, no_coordination) and `configs/scenarios/24h_uniform.yaml` (24 h, full neighborhood outage from 08:00, round_robin). Also adds the "continuous execution" workflow preference. |
| 2026-05-14 | Task 10 — bus saturation + no-wheeling | `87891c2` | 30 ✓ | Adds no-wheeling filter (sender's grid status != receiver's grid status → reject + `NO_WHEELING_REJECTED` event) and bus-saturation scaling (total gross out > `bus_max_kw` → scale all flows proportionally + `BUS_SATURATED` event). Network module fully done for Phase 1. |
| 2026-05-14 | Task 9 — sender/receiver cap clipping | `a82dbd1` | 26 ✓ | Two-stage clipping in `settle_transfers`: senders that requested more than their cap have outgoing transfers scaled proportionally (`SENDER_DOD_FLOOR` event); receivers whose total inbound exceeds their cap force a back-scale on the sender side (`RECEIVER_FULL` event). Includes workflow-preferences and project-skills sections added to this CLAUDE.md per user request. |
| 2026-05-14 | Task 8 — settle_transfers happy path | `3508a1b` | 23 ✓ | Adds `EventKind` (StrEnum), `Event`, `SettlementResult` to `sim/types.py`. Minimal `settle_transfers`: receiver gets `kw × (1 - bus_loss_factor)`; emits `TRANSFER_EXECUTED` event. Sender/receiver caps accepted but ignored — Task 9 wires them in. Ruff caught a `class EventKind(str, Enum)` pattern; switched to `StrEnum` (Python 3.11+). |
| 2026-05-14 | Task 7 — Neighborhood + comm graph | `a5a0226` | 22 ✓ | `Neighborhood` dataclass + `build_grid_neighborhood(rows, cols)` — 5×6 grid, 4-neighbor comm graph (corners 2, edges 3, interior 4). Network structure only; settle_transfers lands in Tasks 8-10. |
| 2026-05-14 | Task 6 — data layer + SyntheticAdapter | `d9c489e` | 17 ✓ | `LoadProfile`/`SolarProfile` protocols + `SyntheticSolar` (half-sine 6 AM–6 PM) + `SyntheticLoad` (constant). Real Pecan Street + NREL adapters deferred to Tasks 21-22. |
| 2026-05-14 | Task 5 — net export + grid coupling | `9aea280` | 11 ✓ | Wires up `desired_net_export_kw` and `grid_status`. Adds `grid_import_kwh`, `grid_export_kwh`, `achieved_net_export_kw` fields. Household physics now complete for Phase 1. |
| 2026-05-14 | Infrastructure: CI + pre-commit + permissions + skills | `32757b0` | 8 ✓ | GitHub Actions CI workflow, ruff/mypy pre-commit hooks, `.claude/settings.json` allowlist, and four new skills: `/advisormeeting`, `/sweep`, `/explainphysics` (plus `/nextask` + `/simtest` from earlier today). |
| 2026-05-14 | Task 4 — RT efficiency | `b34c754` | 8 ✓ | sqrt(eta) on each leg; full cycle returns eta*input. Ruff RUF002 caught a Unicode `×` in a docstring; replaced with `*`. |
| 2026-05-14 | Task 3 — rate clamps + SoC bounds | `6b4ec72` | 6 ✓ | Added `wasted_kwh` / `unmet_kwh` accounting. |
| 2026-05-14 | Task 2 — household basics | `0d71941` | 2 ✓ | Minimal `step()` with no constraints. |
| 2026-05-14 | Task 1 — shared types | `261e830` | 5 ✓ | `Transfer` + `HouseholdProfile`. |
| 2026-05-14 | Task 0 — scaffold | `76b013d` | 0 ✓ | pyproject.toml + venv + pytest/ruff/mypy. Used built-in `python3 -m venv` (no `uv` installed). |
| 2026-05-14 | Initial commit | `f0169f4` | — | Spec + plan + CLAUDE.md + LICENSE. |

## Locked Phase 1 design decisions

These are decisions you should NOT re-litigate without explicit user re-approval:

- **Physics:** energy model + basic constraints (battery rate, RT efficiency 0.9, DoD floor 0.1, bus transit loss 0.05). No AC power flow.
- **Temporal:** 15-min ticks for both physics and decisions in v1. Architecture supports evolving to 5-min physics / 15-min decisions in Phase 2.
- **Neighborhood:** 30 households on a 5×6 grid. 4-neighbor communication graph + shared physical bus (50 kW default). Configurable.
- **Data:** Pecan Street (Austin TX) primary + NREL ResStock as a robustness check + NREL NSRDB for solar irradiance. Adapter pattern in `sim/adapters/`.
- **Outage model:** schedule of `(start, end, affected_houses)` tuples. Partial-island supported but **no wheeling** (grid-connected houses can't pass grid energy through the bus to islanded neighbors).
- **Coordination plug-point:** `decide_transfers(t, states, households, solar, load, grid, neighborhood, dt_hours) -> list[Transfer]`. Phase 2 LLM agents plug in here without modifying the simulator core.
- **Output:** state.jsonl + events.jsonl + summary.json under `runs/<scenario_id>/<timestamp>/`. `messages.jsonl` reserved for Phase 2.

## Locked Phase 2 references

- **Park et al., "Generative Agents" (arXiv:2304.03442):** advisor-recommended. Decision: do NOT fork the codebase (their world is a 2D social town, fundamentally different from a physics-based microgrid). Treat as a Phase 2 reference for agent architecture patterns (memory stream, reflection, natural-language messaging) which we reimplement adapted to microgrid coordination and cite prominently.

## User context

- High school student, comfortable with Python, new to power systems / energy / multi-agent systems.
- Working on this as a research project under mentor/advisor guidance. Advisor framing is in the kickoff message in session history. No fixed deadline — summer + potentially next school year.
- Capable and engaged — don't be condescending, but do explain power-systems terminology when it first comes up (DoD, RT efficiency, distribution bus, etc.). Don't black-box the work via subagents; the student is here to learn the material.

## Workflow preferences (durable)

These are the user's explicit preferences for how Claude should operate on this project. They override default Claude Code behavior where they conflict.

- **Inline execution, not subagent-driven.** Tasks are executed in the active session, batched ~3-5 at a time with check-ins between. The student wants to see the work happen and learn the material, not have it produced by a fresh agent each time.
- **No `Co-Authored-By: Claude` trailer in commits.** All commits attributed solely to the user.
- **Update `CLAUDE.md` progress log after every completed task**, in the *same* commit as the task's code changes — never a separate "docs" commit.
- **After completing each task, preview the next one** — end the response with a 1-2 sentence summary of what's coming next.
- **Continuous execution: do NOT pause between tasks to ask "want me to continue?"** — just keep going. Stop only on real blockers: ambiguous spec, failing test you can't fix, decision the user hasn't authorized, or anything affecting the public surface area of the repo. The user explicitly opted into "fire-and-forget" execution on 2026-05-14.
- **Mark plan checkboxes as `- [x]` after each task**, in the same commit. The plan file is the source of truth for what's done; `/nextask` reads the first `- [ ]`.
- **Public GitHub repo from day 1.** Repo: github.com/leochang017/microgrid-llm-coordination. MIT licensed.
- **Pre-commit hooks gate every commit.** If a hook reformats files, re-stage and retry — never bypass with `--no-verify`.
- **Explain power-systems jargon when it first appears**, but don't be condescending — the student is capable, just new to the domain.

## Project skills (invoke with `/<name>`)

Project-specific Claude Code skills authored for this project, all at `~/.claude/skills/<name>/SKILL.md`. Available in every session:

- **`/readclaude`** — Load this CLAUDE.md into working context at the start of a session.
- **`/nextask`** — Find the next unchecked step in the plan and report what it will do. Waits for go-ahead.
- **`/simtest`** — Run `pytest + ruff + mypy` and report a one-line summary (or first failure).
- **`/explainphysics`** — Plain-language walkthrough of a `sim/` file with hand-traced numeric examples.
- **`/advisormeeting`** — Draft a 2-paragraph status update for an advisor meeting using the progress log + git history.
- **`/sweep`** — (Phase 3) Run scenarios × strategies × seeds and tabulate summary metrics.

## Conventions (Phase 1)

- Python 3.12, `uv` for env, `pytest`, `ruff`, `mypy --strict` on `sim/`.
- **TDD always.** Every task: write failing test → run it red → minimal impl → run green → commit. Do not skip the red step.
- **Conventional commits** (`feat:`, `test:`, `chore:`, `docs:`).
- **No global state** in `sim/`. Engine owns the RNG. Pass it explicitly.
- **Pure functions** in `household.py` and `network.py`. The engine is the only stateful glue.
- **Determinism is mandatory.** Two runs of the same scenario YAML must produce byte-identical state logs.
- **Strict-mode invariants** (SoC bounds, non-negative wasted/unmet) asserted every tick. Disabled only via `--no-strict` for hacking.

## Critical files

| Path | Purpose |
|------|---------|
| `docs/superpowers/specs/2026-05-14-phase1-simulator-design.md` | Phase 1 design spec (authoritative) |
| `docs/superpowers/plans/2026-05-14-phase1-simulator.md` | Phase 1 implementation plan (TDD task list) |
| `CLAUDE.md` | This file |
| `sim/` | Simulator package (Phase 1 build target) |
| `tests/` | Test suite |
| `configs/scenarios/` | Scenario YAML files |
| `runs/` | Output directory (gitignored) |
| `data/` | Cached raw data (gitignored, see Task 24) |

## Data access

- **NREL NSRDB:** free API key at https://developer.nrel.gov/signup/. Env vars: `NREL_API_KEY`, `NREL_EMAIL`.
- **Pecan Street Dataport:** requires researcher account at https://www.pecanstreet.org/dataport/. **Apply on day 1**; approval can take days to weeks. Until approved, develop against synthetic adapters + CSV fixtures (Task 21 ships those).

## Important warnings (from advisor)

- Do NOT claim the system is ready for real deployment. It isn't, nobody's is.
- Be careful with the equity framing. Read Sovacool's energy-justice work before writing the fairness section.
- The LLM-agents-lie failure mode is interesting; study it but do NOT oversell as an adversarial security contribution.
- Open-source release planned alongside the paper. GitHub repo is **private until paper draft is solid**.

## What to do at the start of a new session

1. Read this file (`/readclaude` does this for you).
2. Read the current phase's spec.
3. Read the current phase's plan.
4. `git status` + `git log -10` to see where execution left off.
5. Find the first unchecked `- [ ]` step in the plan and proceed.
