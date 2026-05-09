---
date: 2026-05-08
project: continuity
---

# Decision: PM owns project narratives; continuity drafts and promotes

## Decision (1 sentence)

The pm plugin (when it lands) is the canonical writer for `<vault>/10-projects/<Name>/narrative.md`; continuity drafts narrative content to `<vault>/_continuity/<Name>/narrative-draft.md` and a promote step calls `pm_writer.append_narrative(name, content)` to land it in the canonical file — and during the pre-pm-plugin gap, continuity writes drafts only and the user hand-merges into `narrative.md` until pm ships.

## Alternatives considered

- **Continuity owns narrative.md directly (status quo via CLAUDE.md prose protocol)** — rejected. Violates the tenancy rule established in `2026-05-08-reader-writer-architecture.md` that `<vault>/10-projects/<Name>/*` is pm's subtree. Cementing a continuity write path now means a forced reversal when pm lands.
- **Continuity writes narrative.md with an explicit "borrowed authority" note until pm ships** — rejected. Lower-friction in the short term but bakes in a write path that has to be revoked. The migration cost of routing through `_continuity/` from the start is small.
- **Memory hosts narratives as a kind of observation** — rejected. Narratives are project-lifecycle artifacts (current-state synthesis), not append-only observation records. Different shape, different audience.
- **Continuity drafts directly into `<vault>/10-projects/<Name>/narrative-draft.md`** — rejected. Writes to pm's subtree even though it's a draft; muddies tenancy. Drafts belong under `_continuity/` where continuity owns the subtree.

## Why this won

Tenancy stays clean: the project subtree under `10-projects/<Name>/` belongs to pm and only pm writes there. Continuity contributes value (synthesizing narrative content from cross-source signals) without owning the canonical file. The promotion mechanism is the bridge: continuity proposes, pm ratifies. The pre-pm gap is short and the manual merge cost is cheap relative to the cost of unwinding a wrong-tenant write path later.

## Stakeholders

- c-daly
