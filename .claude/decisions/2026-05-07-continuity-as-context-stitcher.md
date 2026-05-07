---
date: 2026-05-07
project: continuity
---

# Decision: Continuity's purpose is to stitch context together for the user

## Decision (1 sentence)

Continuity reads from any available provider, surfaces relevant details to the user, recognizes emergent insights from cross-source comparison, and writes those insights through its configured write provider — and the continuity plugin itself owns the write code path when the configured target is the vault (delegation to another plugin only happens when the backend *is* a plugin, e.g., memory).

## Alternatives considered

- **Continuity as memory + PM host (v3 design)** — rejected. Overscoped; the "memory and PM are inseparable" identity claim didn't survive once memory's role with experimentation, agent assistance, conversation continuity, and PKM was noticed. Memory and pm are now their own plugins.
- **Continuity as pure read-only synthesizer (no writes)** — rejected. Continuity generates emergent insights by comparing things that aren't seemingly similar; those insights don't exist anywhere until continuity produces them. Recording them is part of the value, not bookkeeping that belongs elsewhere.
- **Continuity hard-coupled to memory plugin as its write target** — rejected. The write provider is configurable per setup (memory plugin, vault directly, database, etc.), so continuity stays agnostic about backend choice.
- **Write logic delegated entirely to a backend plugin** — rejected. When the configured target is the vault directly, the continuity plugin owns the file-writing code path. Delegation only applies when the backend itself is a plugin with its own MCP surface (e.g., memory).
- **Continuity dissolves entirely (since memory and pm extracted)** — rejected. Stitching context across providers, surfacing relevant details, and recording cross-source insights is a coherent, narrow job that none of memory, pm, or experimentation does.

## Why this won

Stitching is a real, distinct job. Reading across providers, presenting coherent context to the user, and recording emergent insights through a configured write provider gives continuity a narrow domain that doesn't overlap memory (substrate), pm (state of work), or experimentation (experiment state). The four plugins compose cleanly: memory holds entries, pm holds work-state, experimentation holds runs, continuity stitches all of it for the user. The plugin's surface gets small and pure — one read operation parameterized by the cue, plus a write path for synthesized insights, with the plugin owning the vault-target write code so configuration stays a setup choice, not a code-organization choice.

## Stakeholders

- c-daly
