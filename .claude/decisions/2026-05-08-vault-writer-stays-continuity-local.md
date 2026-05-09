---
date: 2026-05-08
project: continuity
---

# Decision: vault_writer ships inside continuity through Phase 1; promote to a shared layer when memory plugin lands

## Decision (1 sentence)

`vault_writer` (the file-write code path under continuity's `WriteProvider` abstraction) lives inside the continuity package through Phase 1 of `2026-05-07-implementation-plan.md`; when memory plugin enters scope (Phase 2.x) and acquires its own need to write to vault, `vault_writer` is promoted out of continuity to a shared vault layer that both plugins consume.

## Alternatives considered

- **Build `vault_writer` as a shared layer from the start** — rejected. Speculative abstraction. There is exactly one consumer today (continuity); introducing a shared layer before a second consumer exists costs design and packaging effort with no current beneficiary. The Phase 0 vault_reader already shipped continuity-internal-ish; matching that shape for the writer keeps Phase 1 small.
- **Keep `vault_writer` permanently continuity-local; have memory call continuity to write** — rejected. Inverts the natural layer order. Vault sits beneath the consumer plugins (per the layer-stack diagram in `2026-05-08-reader-writer-architecture.md`); making continuity a dependency of memory contradicts that and creates a dependency cycle when continuity also needs to read from memory.
- **Build `vault_writer` shared but stub `memory_writer` against continuity's instance** — rejected. Same speculative-abstraction objection as the first alternative, plus extra glue code that has to be unwound when memory ships its real writer.

## Why this won

Avoids speculative abstraction: the second consumer doesn't exist yet, so the shared layer doesn't need to exist yet. When memory plugin starts (Phase 2.x), the move is a code relocation — the interface shape is already what it would be in a shared layer, so promotion is mechanical. Phase 1 ships the prototype that generalizes; Phase 2.x generalizes it. The cost of premature extraction is paid only if a second consumer arrives, and is low when it does.

## Stakeholders

- c-daly
