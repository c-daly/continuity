---
date: 2026-05-07
project: continuity
---

# Decision: Memory is its own plugin

## Decision (1 sentence)

The memory substrate (loop+providers+schema, capture/read/promote/sync, INDEX generation, tenant pattern) lives in its own plugin; continuity, pm, agent-swarm, vault-cli, bench, AgentArena, and future consumers are tenants of it, not hosts.

## Alternatives considered

- **Memory inside continuity (per v3 design)** — rejected. v3's "memory and PM are inseparable" identity statement didn't survive scrutiny once memory's role with experimentation, agent assistance, conversation continuity, and personal knowledge work was noticed. Hosting memory inside continuity made continuity overscoped and prevented other consumers from sharing the substrate cleanly.
- **Memory as a vault-cli extension** — considered. vault-cli already opportunistically aggregates activity (daily recap), so the pattern fits. Cost: scope creep into vault-cli's identity. Rejected as the lower-discipline option.
- **Convention spec + reference scripts (no plugin)** — rejected. No enforcement, no shared MCP surface, every consumer reimplements the loop. The whole point of recognizing memory as a primitive is to share the implementation.

## Why this won

Memory as a leaf substrate is independent of any one consumer's identity. Multiple Level-2 services (continuity, pm, experimentation) read and write through it; a peer plugin gives them a single MCP surface to integrate against. The dependency-chain concern from the v3 plugin-extraction debate dissolves because memory depends on nothing else and many things depend on it. Naming a plugin commits the boundary.

## Stakeholders

- c-daly
