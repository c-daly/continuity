---
date: 2026-05-07
project: continuity
---

# Decision: Project management is its own plugin

## Decision (1 sentence)

Project management capabilities (lifecycle state machine, tasks, status regeneration, milestones) live in their own pm plugin, separate from continuity and from memory.

## Alternatives considered

- **PM inside continuity (per v3 Phase 7)** — rejected. v3's "expose PM agent capabilities" plan made continuity own both meaning-making (decisions, patterns) and state-of-work (lifecycle, status). Once memory was extracted, the same logic applied to PM: it has its own coherent domain and shouldn't be tangled with continuity's read-side identity.
- **PM as agent-swarm tools** — rejected. agent-swarm executes workflows; pm owns state *about* projects (what's in flight, blocked, done). Different domains; conflating them re-creates the agent-swarm `pm` agent ambiguity that's been deferred for months.
- **PM as a memory consumer with no plugin (conventions only)** — rejected for the same reason as the memory-no-plugin alternative: no shared MCP surface, every consumer reimplements.

## Why this won

PM has a distinct, narrow domain — state of work, lifecycle transitions, status. Splitting it from continuity gives both plugins a single coherent responsibility: pm owns state-of-work, continuity owns context-across-time. The agent-swarm `pm` agent reference (currently undefined, deferred to continuity) now resolves to pm plugin MCP tools.

## Stakeholders

- c-daly
