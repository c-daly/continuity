---
date: 2026-05-07
project: continuity
type: implementation-plan
status: current
supersedes: 2026-05-03-implementation-plan-v3.md
builds-on:
  - 2026-05-06-continuity-design-v4.md
  - 2026-05-05-build-plan.md
  - ~/.claude/plugins/continuity/.claude/decisions/2026-05-07-memory-as-own-plugin.md
  - ~/.claude/plugins/continuity/.claude/decisions/2026-05-07-pm-as-own-plugin.md
  - ~/.claude/plugins/continuity/.claude/decisions/2026-05-07-continuity-as-context-stitcher.md
---

# Continuity — implementation plan (2026-05-07)

## Premise (load-bearing facts from v4 + 2026-05-07 decisions)

- **Continuity stitches context for the user.** Reads from any provider, surfaces relevant details, records emergent cross-source insights. Two surfaces: callable (MCP + CLI) and independently-active (loops + hooks).
- **Memory and pm are peer plugins, not part of continuity.** Build them when their need surfaces; pm is deferred until something concrete demands it.
- **Continuity's write target is configurable.** When the target is the vault, continuity owns the file-writing code path. When the target is another plugin (memory), continuity delegates via MCP. Setup choice, not code-organization choice.
- **Phase 0 already shipped.** Vault read provider + resume-brief composer + MCP server + CLI (`bin/continuity`); agent-swarm SessionStart hook consumes it (PR #92 merged 2026-05-06). Branch `feature/phase-0` in continuity repo not yet merged to continuity master — landing it is item 0 below.

## Sequencing principle

Each phase is independently shippable. Phase 1 lands today's three decisions in code with no new plugin dependency. Phase 2 builds memory only when continuity's write surface starts producing enough that vault-direct writes feel awkward. PM/experiment plugins follow when their drivers materialize, not on a schedule.

## Phase 0.5 — close the Phase 0 loop *(small, do first)*

Tasks already done in spirit; just bookkeeping.

| # | Item | Estimate |
|---|---|---|
| 0.1 | Merge `feature/phase-0` → `master` in continuity repo | 15 min |
| 0.2 | Write Phase 0 acceptance note in continuity narrative (what shipped, what's exercised by agent-swarm hook, what isn't) | 30 min |
| 0.3 | Tag continuity repo `v0.1.0` (first phase boundary) | 5 min |

**Exit:** continuity master == feature/phase-0; `bin/continuity resume-brief` continues working end-to-end via agent-swarm hook.

## Phase 1 — Write-provider abstraction + first generative write *(no memory dependency)*

Make the 2026-05-07 decisions real in code. Smallest possible end-to-end path that exercises continuity-as-stitcher with a generative write.

| # | Item | Estimate | Notes |
|---|---|---|---|
| 1.1 | `WriteProvider` interface in continuity plugin | ~30 lines | Methods: `write(kind, id, frontmatter, body)`, `exists(kind, id)`. `kind` is a continuity-namespaced string (`cont.insight`, `cont.decision`, etc.) so memory can later interpret it as schema. |
| 1.2 | `VaultWriteProvider` impl | ~120 lines | Continuity-owned per 2026-05-07 decision. Maps `kind` → vault path (`cont.insight` → `<vault>/10-projects/<X>/insights/<id>.md`, etc.). Atomic write, frontmatter serialization, idempotent. |
| 1.3 | `MemoryWriteProvider` stub | ~40 lines | Raises `NotImplementedError("memory plugin not yet available")`. Placeholder so config can already name it; resolves in Phase 2.5. |
| 1.4 | Config: `write_provider: vault \| memory` selector | ~20 lines | Reads `~/.config/continuity/config.yaml`. Default `vault`. |
| 1.5 | `continuity record-insight` CLI subcommand | ~80 lines | Takes `--project`, `--title`, body via stdin. Composes frontmatter (`type: insight, source-providers: [...]`), routes through configured WriteProvider. First exercised generative write. |
| 1.6 | `continuity__record_insight` MCP tool | ~40 lines | Same as CLI; MCP-exposed for in-session calls from Claude. |
| 1.7 | Tests for VaultWriteProvider (atomicity, frontmatter shape, path mapping) + integration test for record-insight | ~150 lines | |

**Exit:** From a Claude session, calling `continuity__record_insight` writes a frontmatter-tagged markdown file to the vault at the right PARA path. Same call against `write_provider: memory` raises a clear "memory plugin not installed" error.

**What this proves:** the 2026-05-07 picture works end-to-end with one provider; memory plugin can be added later without changing continuity's surface.

## Phase 2 — Memory plugin v0

Build when the volume of continuity writes (or other consumers' need for shared memory) makes the vault-direct path feel limiting. Per build plan; restated here with today's decision boundaries.

| # | Item | Estimate | Notes |
|---|---|---|---|
| 2.1 | Plugin scaffold `~/.claude/plugins/memory/` | ~1 hr | Same shape as continuity Phase 0 scaffold. |
| 2.2 | `SubstrateProvider` interface + `VaultSubstrate` impl | ~150 lines | Maps `(schema, id)` → vault path. Atomic write/read/list. |
| 2.3 | Memory service: schema registration, write/read/query API | ~250 lines | Native schemas: `mem.feedback`, `mem.user_fact`, `mem.project_memory`, `mem.reference`, `mem.principle`. Continuity's `cont.*` schemas register here too. |
| 2.4 | MCP tools: `memory__write`, `memory__read`, `memory__query` | ~80 lines | |
| 2.5 | Auto-memory migration helper | ~80 lines | One-shot: reads existing `~/.claude/projects/<sanitized>/memory/*.md`, writes via VaultSubstrate. |
| 2.6 | SessionStart hook: pull relevant memory entries via memory__query | ~60 lines | Replaces harness auto-memory loading. |

**Exit:** memory plugin installed alongside continuity; `~/.claude/projects/.../memory/` content migrated to vault; CLAUDE.md "Continuity (until plugin lands)" section deleted.

## Phase 2.5 — Activate `MemoryWriteProvider` in continuity *(small)*

Now the stub from Phase 1 has a backend.

| # | Item | Estimate |
|---|---|---|
| 2.5.1 | Implement `MemoryWriteProvider` body — calls `memory__write` MCP tool | ~50 lines |
| 2.5.2 | Update continuity config docs: `write_provider: memory` is now functional | ~docs |
| 2.5.3 | Test parity: `record-insight` against `vault` and against `memory` produces equivalent stored entries | ~50 lines |

**Exit:** continuity can write through either provider; flipping the config flag is the only difference.

## Phase 3 — Continuity expands: more read providers + first independently-active loop

The reader/composer half catches up with the writer half. Driven by what's missing from resume briefs.

| # | Item | Estimate | Notes |
|---|---|---|---|
| 3.1 | `git` read provider | ~40 lines | Live `git log -N`, `git status`, branch state for cwd. |
| 3.2 | `gh` read provider | ~40 lines | Live `gh pr list`, `gh pr view`. |
| 3.3 | `serena` read provider (optional) | ~80 lines | If a serena MCP is available, query symbol overview / recently-touched code. Skipped gracefully when absent. |
| 3.4 | `claude-sessions` read provider | ~80 lines | Wraps vault-cli `harvest` output if present. |
| 3.5 | First independently-active loop: post-session insight scan | ~150 lines | Hook on session-end (or scheduled tick): reads recent providers, looks for cross-source patterns ("file X edited heavily but no decision recorded", "feedback memory mentions Y but no narrative entry"), writes `cont.insight` candidates. Naming of this layer is still open; implement under a working name. |
| 3.6 | Resume-brief composer upgraded to use new providers | ~80 lines | Brief now incorporates git/gh state, not just vault. |

**Exit:** Resume briefs get noticeably richer; first emergent-insight write happens unprompted; continuity's read+write loop is closed.

## Phase 4 — PM plugin v0 *(deferred until driver appears)*

No commitment to timing. When agent-swarm's `pm` agent reference becomes blocking, or when project lifecycle bookkeeping becomes painful, build this. Build plan's Phase 2 item, restated.

Schemas: `pm.intake_decision`, `pm.lifecycle_event`, `pm.status_snapshot`. MCP tools: `pm__intake`, `pm__triage`, `pm__status`. Resolves dead `pm` references in agent-swarm workflows.

## Phase 5 — Experiment plugin v0 *(deferred until driver appears)*

Same. When experiment cadence picks up enough to warrant the move, lift bench scripts and the experiment workflow into their own plugin. Same shape as Phase 4.

## Cross-cutting concerns (unchanged from v3 prerequisites where still relevant)

- **CC1. `sync-plugin` script** — already exists at `~/.claude/bin/sync-to-cache` per recent agent-swarm work; reuse for memory/pm/experiment plugins as they land.
- **CC2. Vault filesystem semantics on WSL** — already validated by Phase 0 vault writes; no new work.
- **CC3. Vault `.gitattributes` for concurrent appends** — only relevant once multiple machines write to the same files; defer until cross-machine sync is exercised.
- **CC4. Config schema** — keep `~/.config/continuity/config.yaml` minimal: `vault_root`, `machine_tag`, `write_provider`. Each new plugin gets its own config file.

## Open items (carried from v4, not blocking start)

- The "feelers" / independently-active layer needs a real name (Phase 3.5 ships under a placeholder).
- Cross-cutting writes (feedback, principles, patterns): are they `cont.*` schemas continuity owns, or `mem.*` schemas memory owns and continuity reads? Decide when the first such case is concrete.
- Whether continuity has its own dedicated vault subdirectory or scatters writes per project. Lean: per-project (e.g., `10-projects/<X>/insights/`); revisit if scatter becomes hard to query.

## Suggested next concrete move

Phase 0.5 (15 min — merge `feature/phase-0` to continuity master) followed by Phase 1.1 + 1.2 (the WriteProvider interface and VaultWriteProvider impl, ~150 lines, ~half a day). That gets the 2026-05-07 decisions into code with the shortest path to a working generative write.

## Pointers

- v4 design: `2026-05-06-continuity-design-v4.md`
- 2026-05-05 build plan (parent of this plan): `2026-05-05-build-plan.md`
- 2026-05-04 reframe (drove the plugin extractions): `2026-05-04-memory-and-structure-reframe.md`
- 2026-05-07 decisions: `~/.claude/plugins/continuity/.claude/decisions/2026-05-07-*.md`
- v3 implementation plan (superseded): `2026-05-03-implementation-plan-v3.md`
