---
date: 2026-05-06
project: continuity
type: design
status: draft
authors: [user, claude]
supersedes_partially: 2026-05-03-continuity-design-v3.md
revises: 2026-05-04-memory-and-structure-reframe.md
builds_on: 2026-05-05-build-plan.md
last-revised: 2026-05-07
incorporates-decisions:
  - ~/.claude/plugins/continuity/.claude/decisions/2026-05-07-memory-as-own-plugin.md
  - ~/.claude/plugins/continuity/.claude/decisions/2026-05-07-pm-as-own-plugin.md
  - ~/.claude/plugins/continuity/.claude/decisions/2026-05-07-continuity-as-context-stitcher.md
scope: what was explicitly grounded in the 2026-05-06 conversation, plus the 2026-05-07 decisions formalizing memory/pm extraction and continuity's read/write definition; v3 details not re-validated remain out of scope even if still nominally true
---

# Continuity — design v4

## What continuity is

**A framework that makes Claude sessions feel continuous rather than separate conversations.**

That's the through-line. PM lifecycle, decision archiving, project status are *related concerns* but live in their own plugin (`pm`); continuity reads from pm when its own work calls for that, but does not own pm's domain.

**2026-05-07 sharpening.** Continuity *stitches context together for the user*: reading from any available provider, surfacing relevant details, and **recording emergent insights from cross-source comparison** — insights that only exist as a function of stitching things that aren't seemingly similar. Reading is half the job; the generative write side is the other half.

## Continuity has two surfaces

1. **Callable** — exposes MCP methods, plus its CLI binary (`bin/continuity`).
2. **Independently active** — has its own loops capable of acting without being invoked. Hooks may write/retrieve memory *through* continuity (so the writes/reads carry continuity's interpretation) when the hook's purpose is session-continuity-related.

Both surfaces are permanent. The reframe doc's framing of continuity as "service, not tool surface" is wrong as stated and is revised here.

## Continuity is a composer with providers

Continuity fulfills its work by calling providers and composing their outputs. Providers named in today's conversation:

- **memory** — the substrate for past content; observations, decisions, narratives, etc.
- **pm** — project lifecycle state, decisions, status
- **Serena** — code-level context (project structure, symbol locations, recently-touched code regions)

The provider set is open-ended; others may be added when their need surfaces.

The composition step is where continuity's value lives: cross-provider context lets it frame information and find associations that no single provider would surface alone.

## Memory and continuity are not exclusive

Direct memory writes/reads are fine. Continuity does not gate memory access. The choice between calling memory directly and calling continuity is a strategic choice for the caller:

- **Memory direct**: cheap, fast, raw entries — when the caller knows what it wants or just needs to log a fact.
- **Continuity**: more expensive, contextualized output via cross-provider correlation — when the caller wants the lens.

Same underlying entries, two retrieval paths.

## Continuity's write provider is configurable

Continuity emits its synthesized outputs (resume briefs, recorded insights, surfaced patterns) through a configured *write provider*. The write provider is a setup choice; possible targets include the memory plugin (when installed), the vault directly, a database, or other backends.

**The continuity plugin owns the vault-write code path.** When the configured target is the vault, continuity itself is responsible for putting files there — the file-emission logic lives in continuity, not in another plugin. Delegation only applies when the backend *is* a plugin with its own MCP surface (e.g., memory). This keeps configuration a setup choice, not a code-organization choice.

This applies to continuity's *generative* writes — emergent insights from cross-source comparison. Plain capture (mundane "we decided X today") is not continuity's job; that path goes directly to memory or wherever the capture hook is configured.

(Recorded as decision: `~/.claude/plugins/continuity/.claude/decisions/2026-05-07-continuity-as-context-stitcher.md`.)

## What is preserved from v3 (re-validated through coherence with today's picture)

- **The two failure modes continuity targets**: *recall is slow* and *decisions rot*.
- **Lazy-read, minimal-context philosophy** — Phase 0 of the build plan keeps this.

These weren't re-discussed today; they're carried forward because they remain accurate, not because they were confirmed.

## What is superseded from v3

- v3's identity statement ("continuity IS project management infrastructure"). PM is its own plugin; continuity is narrower.
- v3's tenant model (`<vault>/_continuity/` as continuity's exclusive write zone). Continuity's write target is configurable; when it's the vault, continuity owns the write logic; when it's the memory plugin, continuity calls memory's MCP tools. No tenant prefix is mandated. *(Refined 2026-05-07.)*
- v3's tool list (`continuity index/search/read/recent/backlinks`) — those are memory's tools. Continuity's tools are higher-level; specific names not yet decided.
- v3's Phase 7 (expose PM capabilities from continuity) — pm exposes its own.

## What is revised from the 2026-05-04 reframe

- "Service, not tool surface" framing — continuity has both a callable surface AND independent action.
- Provider concept — providers are real plugins (memory, pm, Serena, …), not abstract computed-providers in code. The recursive layering described in the reframe is concretized as inter-plugin calls.
- **Write target (added 2026-05-07).** The reframe was silent on where continuity's writes go. Today's resolution: continuity writes through a configured write provider; when the target is the vault, continuity owns the file-writing code path; when the target is another plugin, continuity delegates via MCP. See `~/.claude/plugins/continuity/.claude/decisions/2026-05-07-continuity-as-context-stitcher.md`.

## Plugin constellation (per 2026-05-05 build plan, not freshly decided today)

`agent-swarm` + `continuity` + `memory` are the three plugins for normal use. `pm` and `experiment` are added when their need surfaces. Each plugin is small because storage is memory's problem.

## What's already shipping

- **continuity Phase 0** — vault provider + resume-brief composer + MCP server + CLI; commit `75838b6` on continuity `feature/phase-0` (not yet merged to continuity master).
- **agent-swarm SessionStart hook** — PR #92, calls `continuity resume-brief <project>` when continuity is installed and cwd resolves to a known vault project; graceful no-op when continuity is absent.

These are the working ends of v4 already.

## Open

These are explicitly unresolved as of 2026-05-06:

- Specifics of the memory/continuity boundary — "We still need to work out specifics on the boundary responsibilities for continuity and memory." (User, today.) Direct memory access is fine; what *should* default to going through continuity is case-by-case for now.
- Whether cross-cutting concerns (feedback, principles, patterns) are continuity's native writes or just memory writes that continuity reads.
- Whether continuity has any storage of its own, or is pure logic over providers. *(2026-05-07 partial close: configurable per setup. When the write provider is the vault, continuity owns its own files there. When the write provider is the memory plugin, continuity has no storage of its own. Both setups are valid.)*
- The mechanism for "hooks write/retrieve memory through continuity" — sketch only; no implementation contract yet.
- The implementation home for continuity's independent-action loops. (The "feelers" framing surfaced earlier today is not committed; the user questioned where the term came from. Whatever this layer is called and however it's scheduled remains open.)
- Continuity's full MCP method set and CLI subcommand set beyond the Phase 0 deliverables.

## Out of scope for v4

- Memory plugin's internal design.
- PM plugin's internal design.
- Experiment plugin's internal design.
- vault-cli's evolution.
- v3 details not re-validated today (cross-machine sync mechanics, promotion mechanics, schema versioning, plugin sensitivity stance, acceptance criteria from v3, future-enhancements list). Some likely still hold; v4 deliberately does not re-state them.

## Pointers

- v3 design (partially superseded): `2026-05-03-continuity-design-v3.md`
- v3 implementation plan (partially superseded): `2026-05-03-implementation-plan-v3.md`
- 2026-05-04 architectural reframe (revised by v4 on "service, not tool surface"): `<vault>/10-projects/continuity/2026-05-04-memory-and-structure-reframe.md`
- 2026-05-05 build plan (companion — phasing/build sequence lives there): `<vault>/10-projects/continuity/2026-05-05-build-plan.md`
- 2026-05-07 decisions (memory plugin extraction, pm plugin extraction, continuity-as-context-stitcher): `~/.claude/plugins/continuity/.claude/decisions/2026-05-07-*.md`

