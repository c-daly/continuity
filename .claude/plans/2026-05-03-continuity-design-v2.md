---
date: 2026-05-03
status: draft
authors: [user, claude]
scope: cross-cutting (continuity plugin, vault-cli, ~/.claude, Obsidian vault)
license: open-source (planned)
supersedes: 2026-05-02-continuity-design.md
revision_notes: |
  Incorporates 19 design risks identified in 2026-05-03 design review
  (see 10-projects/continuity/design-risks.md in vault for full risk list).
  Major changes vs v1:
  - Reframed memory injection from "potential contamination" to "part of measured system" — capture conditions per use, don't suppress
  - Added regenerator semantics (engine choice, contradiction policy, cadence, provenance headers)
  - Added cross-machine concrete mitigations (.gitattributes union merge, per-project polished views, SessionStart regeneration check)
  - Added operational sections (vault sync atomicity, WSL/Windows mount semantics, schema versioning)
  - Bench/measurement coupling inverted — bench writes plain files; continuity reads as memory source
  - Phase 1 explicitly redefined as truly behavior-preserving (skill-removal deferred to post-dependency-audit phase)
---

# Project Continuity Upgrade — v2

## Problem

Returning to a personal project after a long absence is expensive and lossy. Two specific failure modes have been observed:

1. **Recall is slow.** Re-loading the project's mental model takes hours of reading scattered artifacts (commits, issues, design docs, narratives), even when the substrate is well-organized.
2. **Decisions rot.** Choices made in the moment — especially the *why* and the alternatives considered — fade or are never captured. The code shows the decision; nothing shows the reasoning.

These problems intensify with absence length. They generalize across all of the user's personal projects (LOGOS, Saoirse, Chiron, Agent Swarm, Continuity itself, etc.).

The existing infrastructure addresses this only partially:
- `vault-cli` automates daily recaps and weekly rollups
- The vault uses PARA layout with per-project notes, `narrative.md`, and Dataview queries
- The LOGOS-bound project-manager agent regenerates `STATUS.md` on demand
- agent-swarm currently injects an auto-memory protocol that captures user/feedback/project/reference notes
- Source-control hygiene exists per-repo

The **gap** is everything that requires manual upkeep: per-project narrative refresh, decision capture, resumption brief generation. These chores are the first to lapse during busy periods, which is precisely when continuity matters most. Additionally, memory functionality is currently split between agent-swarm (protocol injection) and a hard-coded user-level path — a coupling that a properly-scoped continuity plugin should resolve.

## Constraints

1. **Don't rebuild what exists.** Vault-cli, PARA layout, per-project narratives, project-manager STATUS regen — all stay. Continuity composes with them, doesn't replace.
2. **Don't require manual upkeep for things that can be automated.** Anything that lapses during busy periods loses value when it lapses.
3. **Cross-machine first.** Anything stored locally that doesn't sync is bound to drift; sync via vault git.
4. **No hard MCP dependencies.** Optional integrations enrich; absences degrade gracefully.
5. **Capture conditions, don't suppress them.** Memory injection, polished views, accumulated context are part of the system being used. When measurement is needed, capture what was injected per use; let the analyst (current user, future user, future LLM) interpret.
6. **Memory is a record at the source layer; sorting happens in polished.** Sources accumulate honestly; polished views interpret. Polished is regenerable from source — never the other way around.
7. **Plugin code is shareable; data is user-configurable.** Plugin repo contains code + non-sensitive defaults. Memory paths and other sensitive locations are configured by the user.
8. **Default scope is vault-local** — git-rollback-recoverable. Nothing happens to the user's project repos that the plugin can't undo via vault git.

## Existing System (do not rebuild)

- **Vault PARA layout** — `00-inbox/`, `10-projects/<Name>/`, `20-areas/`, `30-resources/`, `40-archive/`, `journal/`, `_templates/`
- **Per-project notes** — `<Name>.md` with `type: project, status: <state>` frontmatter; Dataview queries over `10-projects/`
- **Daily recap** — Cron 11 PM. Aggregates git, GitHub, Claude session metadata, shell, gcal, captures
- **Weekly rollup** — Cron Sun 11:30 PM. Per-repo/project breakdown with reflection prompts
- **Claude session harvest** — `vault harvest [--project X]`. Currently metadata only; deep harvest is part of this design
- **Per-project narratives** — LOGOS has `narrative.md` (9.9 KB) with thesis, per-subsystem state, dated decisions, current state. Other projects vary
- **Project-manager agent (LOGOS-bound)** — regenerates `STATUS.md` from current code+vault state on demand

### Relationship to agent-swarm

Memory injection currently lives in agent-swarm via protocol assembly. This is a coupling that continuity will resolve by extracting the memory concern into a plugin scoped to it. **This is a load-shedding move on agent-swarm**, not just additive new infrastructure: agent-swarm becomes more focused on workflow coordination; continuity owns memory and project lifecycle.

The extraction must be done carefully — see Phase 1 in the implementation plan, which defers actual skill removal until a dependency audit confirms no breakage.

### Built-in `memory.json` non-integration

Claude Code's built-in `memory.json` is not used. Reasons: (1) opaque schema; (2) per-machine, no cross-machine semantics; (3) not introspectable. Continuity's source files are markdown — diffable, greppable, human-editable.

## Proposed Architecture

### Packaging and licensing

Plugin repo at `~/.claude/plugins/continuity/`. Open-source target: code only — no user data ever in plugin repo. Sensitive paths configured by user via `~/.config/continuity/config.yaml`:

```yaml
memory_dir: <vault>/40-archive/memory/   # or wherever user wants
projects_root: <vault>/10-projects/      # standard PARA location
journal_dir: <vault>/journal/
machine_tag: home-laptop                  # this machine's identifier
```

Defaults shipped in `<plugin>/config.example.yaml`. Plugin code reads only from configured paths; never assumes vault layout beyond what config says.

### Project lifecycle

A project is an emergent property of behavior, not a thing the user declares.

```
[unknown dir] --SessionStart prompt--> [active] --inactivity--> [paused] --inactivity--> [dormant] --confirm--> [archived]
                  |                       ^                       ^                        ^
                  +-- "no" --> [denylist]  +---- new activity -----+------------------------+
```

| State | Trigger | Behavior |
|---|---|---|
| `active` | First-session yes, or any activity from a non-active state | Full automation: SessionStart brief, Stop drafts, nightly STATUS regen |
| `paused` | 14 days no activity | Same as active but lower-priority for batched jobs |
| `dormant` | 60 days no activity | STATUS regen skipped; SessionStart still briefs on entry |
| `archived` | Explicit confirm, or 365+ days with prompt | All automation off; vault note retained for history |
| denylisted | "no" answer at first SessionStart | Never re-prompted for this path |

State stored in `<vault>/10-projects/<Name>/<Name>.md` frontmatter (`status:` field). Transitions log to the daily journal.

**Hand-edited preservation in regenerated files** — When automated regeneration touches `narrative.md`, `STATUS.md`, or other regenerable files, it preserves user-edited sections marked with `<!-- preserve-start -->` ... `<!-- preserve-end -->` HTML comment markers. The regenerator parses these from the existing file, regenerates everything outside them, and re-inserts the preserved sections verbatim. Without this, automated regen would silently destroy careful curation.

### Two-layer memory model

#### Source files (`<memory_dir>/sources/`)

- Append-only, timestamped observations
- The truth-of-record
- Sync across machines via vault git
- Each observation is an H2 heading with datetime + machine tag, followed by freeform body
- Heading format: `## YYYY-MM-DDTHH:MM:SS±HH:MM — machine-tag`
- ISO 8601 with timezone offset for cross-timezone unambiguity; seconds precision avoids collision on rapid appends

Each source file has frontmatter:

```yaml
---
topic: <topic-name>
type: source
protocol_version: 1
created: <iso8601>
description: <one-line>
---
```

`protocol_version` allows schema evolution; readers refuse to interpret data with mismatched major version, falling back to a documented compatibility mode. Bump major version when schema changes are non-backward-compatible.

#### Polished views (`<memory_dir>/polished/`)

- Synthesized current-state distillations, derived from sources
- Regenerable from sources at any time
- Compact and easy to scan
- **Authoritative provenance** — every polished view starts with metadata header (see below)
- Cross-machine: regenerable on each machine; sync behavior depends on user choice (gitignored by default; can be committed if desired)

#### Polished view provenance header (mandatory)

Every polished view starts with:

```yaml
---
type: polished-view
topic: <topic>
generated_at: <iso8601>
generator: <template-version + llm-engine + version>
source_count: N
date_range: <oldest-source-ts> - <newest-source-ts>
contradictions_resolved: <count>
authoritative: false
escape_hatch: "Polished is interpretation. Truth-of-record is sources/<topic>.md"
protocol_version: 1
---
```

Without this header, readers refuse to interpret the file (treat as needs-regeneration). The `authoritative: false` line and explicit escape hatch are deliberate: polished views are *interpretation*, not truth. Agents (and users) reading them must know the messy reality is one click away.

#### Regenerator engine

Hybrid strategy with explicit boundary:

- **Template-driven** for structural rendering: section ordering, table layout, recency-based selection (top-N most recent observations per topic-predicate), source counts, date ranges. Cheap, deterministic, predictable. Handles 80%+ of regenerations.
- **LLM-driven** only for contradiction detection and resolution. Trigger condition: template detects multiple observations on the same predicate where assertions differ. LLM call is invoked with both observations + context, asked to either (a) emit "still valid in different contexts: <explanation>" preserving both, (b) emit "superseded — latest stands" with footnote linking the prior, or (c) emit "merge as evolution: <synthesis>" preserving both as trajectory.

Engine choice is captured in the polished view's provenance header (`generator: template-v1 + llm-claude-opus-4-7`) so future-you can see how each view was produced.

#### Contradiction reconciliation policy (default)

When sources contain conflicting observations on the same predicate:
1. Both observations remain in source (untouched)
2. Polished view surfaces only the most-recent observation per topic-predicate
3. If the most-recent contradicts a prior, the polished entry includes a footnote: `[supersedes 2026-04-15 observation: "<earlier text>"]`
4. If the LLM step ran (engine triggered the LLM path), the polished entry includes `[reconciliation: <one-line summary of why>]`

Users can configure alternative policies in `config.yaml`:
- `latest-wins` (default, above)
- `both-surface` (show both, with timestamps; let agent decide)
- `llm-arbitrated-always` (every multi-observation predicate goes through LLM)

#### Read paths and within-session staleness

Default read path for agents: `polished/<topic>.md`. But because polished is regenerated only at session end (via Stop hook), an agent that records an observation at minute 10 won't see it reflected when reading at minute 30.

**Within-session freshness mitigation:** the auto-memory read function:
1. Loads polished view
2. Checks if any source files were modified since polished's `generated_at` timestamp
3. If yes, appends the unsynthesized recent observations to what's returned, marked `[unpolished, since session start]`

Cheap to implement (filesystem mtime check + tail-N-lines), removes the staleness without forcing mid-session regeneration.

#### Source-bypass affordance

Auto-memory protocol injection includes explicit instruction: *"If the polished view seems off, contradicts your current observation, or you need temporal trajectory / contradiction history — read `<memory_dir>/sources/<topic>.md` directly. Polished is interpretation; source is truth."*

Documented in agent briefings as standard practice, not edge-case behavior. Otherwise polished view's biases compound silently.

#### Combining and reconciliation across machines

Source files combine across machines via git's union merge:

```
<memory_dir>/sources/.gitattributes:
  *.md merge=union
```

`merge=union` concatenates both sides' additions on conflict, eliminating manual resolution for non-overlapping appends. Heading uniqueness (datetime + machine tag) ensures observations don't collide; union merge ensures the file accommodates concurrent writes without losing data.

This must be tested with a deliberate concurrent-append scenario before relying on it. Phase 1 includes the test.

#### Project context tagging

Observations are tagged with project context at write time when the session has a resolved project:

```
## 2026-05-03T14:23:45-04:00 — home-laptop — project:agent-swarm

User pointed out that memory shouldn't sort itself out...
```

Polished views are generated both globally and per-project:
- `polished/<topic>.md` — global view (excludes observations tagged with a specific project unless explicitly marked global)
- `polished/by-project/<project>/<topic>.md` — per-project views (only that project's observations)

Without this, observations recorded on one machine while working on project P1 contaminate global polished views with P1-specific assertions.

#### Regeneration cadence — three triggers

1. **Stop hook** regenerates polished views for sources modified during the just-completed session. Cheap; covers the common case.
2. **SessionStart hook** checks polished view's `generated_at` against sources' max mtime. If sources are newer (e.g., fresh sync from another machine), regenerates before injecting. Expensive on cross-machine first-session, free on same-machine subsequent sessions. Acceptable cost for cross-machine integrity.
3. **Weekly cron** fully regenerates all polished views. Catches drift, allows engine improvements (template version bumps, prompt refinements) to backfill across all topics.

All three triggers must check `protocol_version` and refuse to regenerate views written under an incompatible major version.

#### Plugin sensitivity stance

The plugin **never bundles user memory data**. Its repo contains code, configuration schemas, and example configs only. Each user's actual memory directory lives at their configured path, in whatever repo they choose to host it (vault, dedicated private repo, or untracked). This is what makes the plugin shareable as open-source: there's no privacy entanglement at the code level.

### Auto-memory protocol injection

Lives at `<plugin>/hooks/sessionstart.sh`. Behavior contract — at session start, the protocol instructs the agent to:

- Read `<memory_dir>/polished/MEMORY.md` (the index) to know what topics exist
- Read `<memory_dir>/polished/<topic>.md` for current state when consulting memory
- Drill into `<memory_dir>/sources/<topic>.md` only when temporal trajectory, contradiction-checking, or deep history is needed (with explicit reminder that polished is interpretation, source is truth)
- When learning something durable about the user, feedback, project, or reference, **append a new dated section to the source file** (or create a new source file if none exists)
- Tag observations with project context when a project is resolved
- Update `MEMORY.md` (regenerated at session end) when adding new topics

The protocol is parameterized by `protocol_version` and includes the version string in the injected text so observed behavior anomalies are diagnosable across protocol upgrades.

#### Capture-as-data principle (for benchmarks and measurement)

Continuity provides primitives for capturing what the agent received at session start; benchmarks/experiments use them to record conditions. **Continuity does not know about benchmarks; benchmarks know about continuity.**

Primitives provided:
- `continuity memory hash` — deterministic hash of all source files (snapshots memory state)
- `continuity memory snapshot <name>` / `restore <name>` — explicit snapshot/restore (or use vault git: snapshot is a commit hash, restore is `git checkout <hash> -- sources/`)
- `CONTINUITY_MEMORY` env var with `on` (default) / `read-only` / `off` — honored by SessionStart hook and write paths. Optional infrastructure for stricter controls.

Bench scripts use these to record per-run starting context (memory state hash, optional injected content snapshot). Memory injection is *part of the system being measured*, not contamination — bench captures what was injected so the analyst can interpret comparisons. See agent-swarm's `experiments/workflow-runs.md` schema for the run-record format that consumes these primitives.

### MCP capability descriptions

`<plugin>/data/mcp-capabilities.yaml`:

```yaml
serena:
  role: "Semantic code navigation. Use for listing modules, finding symbol references."
  fallback_when_absent: "Use grep/find via shell. Symbol lookup will be string-based, not semantic."
github:
  role: "GitHub state. Use for open/recent PRs, issue threads, review activity."
  fallback_when_absent: "Use `gh` CLI directly. Some features (e.g., review threads) require GraphQL."
memory:
  role: "Knowledge graph. Use for searching nodes, reading relations."
  fallback_when_absent: "No graph queries; rely on file-based source/polished memory only."
context7:
  role: "Library documentation lookup."
  fallback_when_absent: "Web search or library README only."
```

Each capability declares both its `role` (what it provides when present) and its `fallback_when_absent` (what to do when unavailable). Without explicit fallbacks, "optional" becomes "mandatory in practice" because the absence cases were never coded. SessionStart prompts the user once on first encounter (only on machines where the server is reachable).

### Data flow

```
[Claude session on Machine A]
   |
   |--- SessionStart hook -----> [vault sync --pull (with retry+lockfile)]
   |                              [check polished freshness vs sources mtime]
   |                              [regenerate stale polished views if needed]
   |                              [auto-memory protocol injected]
   |                              [project resolution + brief or prompt]
   |                              [MCP enrichment from configured + reachable servers]
   |                              [agent reads polished/ for current state; sources/ when needed]
   |
   |--- (work happens) --------> [git commits, file edits, JSONL transcript stays local]
   |                              [Claude appends observations to sources/<topic>.md]
   |                              [each observation tagged with project context]
   |
   |--- Stop hook --------------> [regenerate polished/ for any sources modified this session]
   |                              [drafts to .pending/ — IF Phase 5+, with explicit consumption semantics]
   |                              [vault sync --push (blocking ≤10s, retry on failure, marker file on persistent failure)]
   |
   v
[overnight cron, on each machine]
   |
   |--- vault recap ------------> [journal/<date>.md including memory captures from sources/]
   |--- deep harvest -----------> [per-session notes with session_machine metadata]
   |--- weekly rollup ----------> [Sun 11:30 PM, per-project breakdown]
   |--- weekly polished regen --> [Sun ~midnight, full regeneration of all polished views]
```

### Source control

Defaults:
- `<memory_dir>/sources/` — committed to vault git
- `<memory_dir>/polished/` — gitignored by default (per-machine, regenerable)
- `<memory_dir>/sources/.gitattributes` — `*.md merge=union` (resolves concurrent appends without manual intervention)

User can override polished commit behavior in config.yaml if cross-machine polished consistency is preferred over per-machine flexibility.

### Multi-machine considerations

#### Vault sync atomicity

The naive flow (`pull at start, push at end`) has race conditions:
- User closes laptop before push completes → observations lost
- Two machines sync concurrently → push race, manual conflict
- Slow network on push → SessionStart hangs

Mitigations:
1. **Stop hook push is blocking up to a short timeout** (10s default), then async with marker file
2. **Marker file `<memory_dir>/.pending-push`** signals next session to retry pending pushes
3. **`pull --rebase` before any push**, retry on rejection up to N times
4. **Sync status indicator** visible to user in SessionStart output ("memory sync: ✓ up to date" / "⚠ pending push from previous session, retrying...")

#### WSL/Windows mount semantics

For users (like the primary user) where vault lives on `/mnt/c/...` (Windows NTFS via WSL):
- Atomic writes are not guaranteed
- File locking is unreliable
- Performance is 10x slower for many small files

Mitigation: writes go to a staging area on native filesystem, then `mv` (single-syscall) into vault location. Phase 1 tests against the actual `/mnt/c/...` path before committing to direct writes.

#### Session-machine tagging

Observations include the machine tag in their heading. Decision drafts (`.pending/`) include `session_machine` metadata. This enables:
- Per-machine source-file diffs in retrospect
- Detecting cross-machine context drift (observations from machine A about project P1 vs machine B about project P2)
- Audit trail for which machine made which decision

#### Project context drift across machines

Observations recorded on Machine A (used mostly for project P1) get implicitly project-correlated. Without per-project tagging (above), polished views average across contexts that shouldn't be averaged. Per-project polished views (`polished/by-project/<project>/<topic>.md`) prevent this.

## Implementation Phases

See companion document `2026-05-03-implementation-plan.md` for full phase breakdown with concrete tasks, dependencies, definition-of-done, and validation strategy.

Summary:

| Phase | Scope | Behavior change | User-visible value |
|---|---|---|---|
| 0 | Plugin scaffolding | none | none |
| 1 | Auto-memory takeover (true behavior-preserving migration) | none | none |
| 2 | Project bootstrap script (manual invocation only) | minimal | resume-brief stub |
| 3 | SessionStart project resolution + resume-brief | gated by user prompt | the headline feature |
| 4 | PM agent generalization | active | per-project STATUS regen |
| 5 | Stop hook + polished view regeneration | active | within-session memory works |
| 6 | Recap extensions | active | richer journal entries |
| 7 | Deep transcript harvest | active | session-level memory granularity |

**Critical revision vs v1:** Phase 1 in v2 is *truly* behavior-preserving — it adds continuity's memory layer alongside agent-swarm's existing one, without removing anything. Skill removal (`remember`/`distill`/`ctx`/`develop`) is deferred to a post-Phase-1 dependency-audit phase to avoid silently breaking dependents. See implementation plan for sequencing.

## Future enhancements and known refinements

- **Project rename auto-detection** — handled in Phase 3 via timestamp-based reconciliation; documented as resolved but worth flagging as a behavior to monitor in real use
- **Cross-project links in narratives** — supported via Obsidian wikilinks; no special handling needed
- **Continuation seeds for cross-machine session continuity** — Phase 7+ idea; build only if real-usage signal emerges that drafts-to-pending isn't enough. Producer (`.pending/` writes in Phase 5) gated on consumer design first to avoid producer-without-consumer trap.
- **Polished view diff visualization** — long-term: an Obsidian view that shows polished views' evolution over time (week-over-week) so prophecy effects are visually detectable

## Out of Scope

- **Replacement for vault-cli.** Continuity composes with it.
- **Cross-project dependency tracking.** Projects can reference each other in narratives, but automated dependency-graph construction is out of scope.
- **Real-time collaboration features.** Cross-machine, but single-user.
- **Encryption at rest.** Vault is the user's; vault-level security applies.
- **General-purpose memory as a service.** This is for one user, one vault, several machines.

## Acceptance

The plugin succeeds if, after a 30-day absence, the user can:
1. `cd` into a project they haven't touched in a month
2. Start Claude
3. Receive a SessionStart brief that names: current state, what was being worked on last, what's blocked, what decisions are pending, what's interesting in recent commits
4. Start work without 1+ hour of catchup reading

And, in the steady state:
1. Decisions made today appear in the relevant project's narrative tomorrow without manual upkeep
2. Cross-machine work doesn't lose observations
3. The memory system survives a vault restore from git history (everything is regenerable from sources)
4. Benchmarks of agent-swarm workflows (or any other measurable system) can capture what continuity injected per run, making longitudinal comparisons interpretable

## Acknowledgments

Design v1 (2026-05-02) established the architecture. v2 (2026-05-03) refines based on extended design review covering 19 risks. Key conceptual shift: memory injection is not contamination — it is part of the system being used. Capture conditions per use; let the analyst interpret. Suppression is a last-resort tool for isolating workflow contributions, not the default.
