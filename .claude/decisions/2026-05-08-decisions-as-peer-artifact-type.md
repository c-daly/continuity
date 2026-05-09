---
date: 2026-05-08
project: continuity
---

# Decision: Decisions are a peer artifact type to observations; each scope-owning surface hosts decisions in its own subtree, at the root of the scope they govern

## Decision (1 sentence)

Decisions and observations are parallel first-class artifact types — observations are descriptive ("after X, Y happens", append-only, freeform-ish), decisions are prescriptive ("we're choosing C because performance is essential", structured with alternatives + why); decisions are not nested inside memory or pm but are hosted by whatever scope-owning surface governs the decision's scope, with the rule **decisions live at the root of the scope they govern**.

## Alternatives considered

- **Decisions are pm-domain only, with cross-references from memory** — rejected. Doesn't accommodate decisions outside the project domain: decisions about memory's own architecture, decisions about how continuity itself works, personal preferences (terse responses, no AI attribution), workflow choices (TDD for core logic), and tooling defaults (`gh` over GitHub MCP). None of those have a project home, so a pm-only model leaves them homeless.
- **Decisions are a structured kind of memory observation (`kind: decision` field)** — rejected. Conflates descriptive and prescriptive. Observations record what *is*; decisions declare what we're *choosing*. Different shapes (observations are freeform paragraphs; decisions need alternatives + why + stakeholders), different read patterns (observations are time-indexed; decisions are point-in-time choices that can be revisited and superseded). Mixing them muddles both.
- **A dedicated decisions plugin with its own `(reader, writer)`** — rejected. Each scope-owning surface already has a writer; requiring a separate plugin to write decisions adds a routing layer for no gain. The "root of the scope" rule routes a decision to its natural home without intermediation.
- **Promote everything (no native global decisions surface; only promoted-from-local items exist at higher scopes)** — rejected. Some decisions are global from the moment they're made (personal preferences, cross-cutting principles); forcing them through a "make local first, then promote" lifecycle is artificial and loses the original intent.

## Why this won

The peer-artifact framing matches how the two things actually work. Promotion still applies — a project-scoped decision can be promoted to project-domain meta when its applicability broadens, and a personal observation can be promoted to a global pattern — but promotion lifts an artifact across scope, not across type. Decisions stay decisions; observations stay observations.

The "root of the scope" rule routes decisions naturally:

| Subject of decision | Location |
|---|---|
| A specific project | `<vault>/10-projects/<Name>/decisions/` |
| All projects (project-domain meta) | `<vault>/10-projects/decisions/` |
| Memory itself | `<vault>/40-archive/memory/decisions/` (when memory plugin lands) |
| A specific plugin's internal architecture | `<plugin>/.claude/decisions/` (already happening for continuity) |
| Personal / cross-everything (preferences, workflow, tooling) | `<vault>/meta/decisions/` |

`<vault>/meta/` is unprefixed, alongside `docs/` and `journal/` — primary content that doesn't fit the PARA tiers, sits in the vault so it syncs across machines (which is what personal preferences should do).

This collapses the "where do non-project-scoped decisions live?" question that fell out of `2026-05-08-reader-writer-architecture.md` Open #3 (decision mirroring) and replaces it with a positive structural rule.

## Stakeholders

- c-daly
