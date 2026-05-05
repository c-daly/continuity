# continuity

Cross-project surfacing and meta-concerns curation for Claude Code.

A reader/surfacer plugin that composes information from providers (vault, memory, git, gh, ...) to answer queries like "what's the state of project X?" and proactively surface what's likely to be needed (resume briefs, recent decisions, cross-cutting patterns). Also curates meta concerns (cross-project feedback, principles, patterns) that don't fit any single project.

## Status

Design phase, with Phase 0 implementation in progress on `feature/phase-0`.

## Architecture

Continuity is one plugin in a constellation:

```
Consumers       (continuity, model directly, future tools)
   ↓
Read providers  (vault, memory, git, gh, ...)
   ↓
Memory          (schema-aware service; substrate-agnostic)
   ↓
Substrate       (vault-substrate, filesystem-substrate, ...)
   ↓
Storage         (Obsidian vault, ~/notes, ... — plain text)
```

Continuity owns:
- **Composers** — read provider results into views (resume briefs, status, recap)
- **Surfacing** — proactive raising of likely-needed information
- **Meta concerns** — cross-cutting feedback, principles, patterns (its native write schemas)

Continuity does NOT own:
- Memory storage (memory plugin)
- Project elements like lifecycle/intake/triage (pm plugin)
- Experimentation tooling (experiment plugin)
- Workflow execution (agent-swarm plugin)
- Terminal vault interaction (vault-cli)

## Plans

Design and build plans live in `.claude/plans/`. The current actionable plan is the 2026-05-05 build plan, snapshot in `<vault>/10-projects/continuity/2026-05-05-build-plan.md`.

## Phase 0

Three components, ~210 lines total:
1. `vault` read provider — knows PARA layout
2. `continuity v0` resume-brief composer — reads vault, composes brief
3. agent-swarm SessionStart hook integration — calls continuity at session start

Phase 0 ships value with no memory plugin needed. The vault is the canonical source; vault-cli (or its successor) handles harvesting external state into vault.
