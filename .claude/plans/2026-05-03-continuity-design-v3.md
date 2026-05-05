---
date: 2026-05-03
status: draft
authors: [user, claude]
scope: cross-cutting (continuity plugin, vault-cli, ~/.claude, Obsidian vault)
license: open-source (planned)
supersedes: 2026-05-03-continuity-design-v2.md
revision_notes: |
  Major architectural reframe based on user clarification:
  "All of the vault should be Claude's memory" + "lazy load with efficient indexing,
  minimal context" + "promotion mechanism for memories arising in local context"
  + "memory files should go under continuity since that's the process that generated
  them — the vault consolidates info from various sources" + "the continuity project
  is about everything a project manager cares about" + "continuity even creates projects."

  v3 collapses most of v2's machinery. The vault is the consolidation hub for
  multiple contributing sources (user, vault-cli, continuity, etc.); continuity
  is one tenant within it. Continuity-generated files live under <vault>/_continuity/.
  User-curated content (10-projects/, 20-areas/, 30-resources/, journal/) is
  user/vault-cli territory — continuity does not write there casually.

  Promotion is the explicit cross-tenant move: continuity-generated observation
  → user-curated location (with bidirectional provenance comments). Read access
  spans the whole vault; write access is scoped to continuity's tenant by default.

  No polished view layer. No regenerator/contradiction/provenance complexity.
  Lazy read via small index. Index updates atomically on agent writes; reconciles
  on recap.

  CONTINUITY IS PROJECT MANAGEMENT INFRASTRUCTURE. It owns project creation,
  lifecycle (active → paused → dormant → archived), narrative refresh, decision
  capture, observation accumulation, status regeneration, cross-project promotion,
  and resume-brief generation. Memory is one mechanism within this; not the identity.
  PM functions are facets of continuity, not a separate concern.

  Subordinate plugin extraction (e.g., for an opinionated agentic project-assistant
  layer) is left as a Phase 7 decision based on what that work actually needs at
  that point — not preemptively planned. Default: everything in continuity.
---

# Project Continuity Upgrade — v3

## What continuity is

**Project management infrastructure for personal projects across machines and over time.** Continuity owns the user's interaction with their projects: creation, lifecycle, narrative, decisions, status, observations, recall, and cross-project pattern recognition. Memory is one mechanism by which it does this work — not its identity.

The two failure modes it targets — articulated as the original v1 problem statement, still accurate:

1. **Recall is slow.** Re-loading the project's mental model takes hours when returning after absence.
2. **Decisions rot.** The *why* and the alternatives considered fade or are never captured.

Generalizes across all of the user's personal projects (LOGOS, agent-swarm, continuity itself, Saoirse, Chiron, etc.). The PM functions and the memory mechanisms are not separable concerns — they're facets of the same project-management work.

## Conceptual reframe (the v3 shift)

**The vault is a consolidation hub for multiple sources.** User curates 10-projects/, 20-areas/, 30-resources/. vault-cli writes journal/ (daily recaps) and weekly rollups. Continuity is one more contributing source. Each source has its tenant; the vault is the shared addressable space; cross-tenant traffic is explicit (promotion).

**The vault's PARA structure is user territory.** Continuity does not casually write into 10-projects/<Name>/narrative.md or decisions/ — those are user-curated content. Continuity reads from anywhere in the vault but writes only to its own tenant by default.

**Continuity tenant: `<vault>/_continuity/`**. All continuity-generated content lives here:

```
<vault>/_continuity/
├── INDEX.md                          # the lazy-load index
├── projects/<Name>/
│   ├── observations.md               # auto-captured observations for project
│   └── decisions-draft/              # decisions captured by agent (drafts)
├── general/observations.md           # cross-cutting observations not tied to a project
├── inbox/                            # observations needing target resolution
│   └── YYYY-MM-DD-<slug>.md
└── recap/                            # daily promotion-candidate logs
    └── YYYY-MM-DD.md
```

**Read access spans the whole vault.** When an agent looks up memory, it reads broadly: index points at user-curated content (10-projects narratives, decisions, areas, resources, journal entries) AND continuity-generated content (auto-captured observations, drafts). The index is the unified entry point; capture is tenant-scoped.

**Push (auto-inject) vs pull (lazy load).** v2's architecture pushed memory into context at SessionStart via polished view injection. v3 pulls: an agent reads the small index when it has reason to, then reads only the relevant files. Context stays minimal; the vault's full richness is one query away.

**Capture targets** (continuity-tenant scoped):

| Observation type | Target |
|---|---|
| Project-specific state observation | `<vault>/_continuity/projects/<Name>/observations.md` (append dated section) |
| Project-specific decision draft | `<vault>/_continuity/projects/<Name>/decisions-draft/YYYY-MM-DD-<slug>.md` (new file) |
| Cross-cutting observation | `<vault>/_continuity/general/observations.md` (append) |
| Doesn't fit anywhere | `<vault>/_continuity/inbox/YYYY-MM-DD-<slug>.md` (new; for later sorting) |

User-curated locations (10-projects/<Name>/narrative.md, decisions/, 20-areas/, 30-resources/, journal/) are written by the user (via Obsidian), by vault-cli (recaps), or — explicitly — via continuity's promotion mechanism (next section). Never via casual capture.

**Promotion** — observations captured in continuity's tenant sometimes deserve elevation to user-curated content (a project's "official" narrative entry, a cross-cutting area preference, a reference fact). Promotion is the explicit cross-tenant move: continuity-generated → user-curated, with bidirectional provenance comments preserving traceability.

## Constraints

1. **Don't rebuild what exists.** Vault-cli, PARA layout, Dataview, narratives, decisions/, journal — all stay. Continuity composes.
2. **Minimal context cost.** Memory access is lazy by default. Index is small (~2KB target). No auto-injection.
3. **Cross-machine first.** All capture goes to the vault, which already syncs.
4. **No hard MCP dependencies.** Optional integrations enrich; absences degrade.
5. **Capture to natural homes; don't create parallel structures.** A project's `narrative.md` IS the project's memory. Don't duplicate into a memory subdirectory.
6. **Promotion preserves provenance.** When local content is recognized as broader, promotion is an *extraction* (synthesis at higher scope) with bidirectional links — never a destructive move. Original local capture is the truth-of-record.

## Existing System (do not rebuild)

- **Vault PARA layout** — `00-inbox/`, `10-projects/<Name>/`, `20-areas/`, `30-resources/`, `40-archive/`, `journal/`, `_templates/`
- **Per-project notes** — `<Name>.md` with frontmatter; Dataview queries
- **Per-project narratives** — `<Name>/narrative.md` with dated sections
- **Decisions** — `<Name>/decisions/<date>-<slug>.md` (new convention from v3)
- **Daily recap** — vault-cli, cron 11 PM
- **Weekly rollup** — vault-cli, cron Sun 11:30 PM
- **Claude session harvest** — `vault harvest [--project X]`
- **Project-manager agent (LOGOS)** — STATUS regen on demand
- **Vault git** — sync across machines

## Proposed Architecture

### Index

A single small file at `<vault>/_continuity/INDEX.md`. Target size: <2KB. Always cheap to read. Indexes both continuity-generated content AND user-curated vault content (per "read access spans the whole vault").

```markdown
---
type: continuity-index
generated_at: <iso8601>
generator: continuity v0.1
vault_root: /mnt/c/Users/cddal/Obsidian/vault
---

# Continuity Index

## Active projects (status: active)

| Project | Path | Last touched | Tags | One-line state |
|---|---|---|---|---|
| agent-swarm | 10-projects/agent-swarm/ | 2026-05-03 | plugin, claude-code, workflow | bench infra built; orchestrate brief revised; PR-thread polling discipline open |
| continuity | 10-projects/continuity/ | 2026-05-03 | plugin, design, memory | design v3; lazy-load model; pre-Phase 0 |
| LOGOS | 10-projects/LOGOS/ | 2026-04-29 | research, primary | <user-supplied state line> |
| ... | | | | |

## Areas (cross-cutting)

| Area | Path | Last touched | Tags |
|---|---|---|---|
| methodology | 20-areas/methodology.md | 2026-05-03 | experimentation, capture-as-data |
| testing-preferences | 20-areas/testing.md | 2026-04-15 | tdd, integration |
| ... | | | |

## Recent journal entries (last 7)

| Date | Highlights |
|---|---|
| 2026-05-03 | bench infra; design v2→v3; orchestrate brief; resolveReviewThread verified |
| 2026-05-02 | continuity design v1 |
| ... | |

## Inbox (unsorted captures, n=N)

| File | Created | Snippet |
|---|---|---|
| 00-inbox/2026-05-01-X.md | 2026-05-01 | <first 60 chars> |
```

The index is the agent's entry point. When Claude has a task that *might* benefit from prior context, it reads INDEX.md (~2KB), scans for relevance, then reads only the specific files referenced.

### Read mechanism (tools)

The continuity plugin exposes a small set of tools:

- **`continuity index`** — print INDEX.md to stdout (or return as MCP tool result)
- **`continuity search <query>`** — grep across vault, return matches with file:line context
- **`continuity read <path>`** — read a specific vault file (relative to vault root)
- **`continuity recent [--days N]`** — list files modified in last N days, sorted by mtime
- **`continuity backlinks <path>`** — list files that reference this file via wikilinks (uses Obsidian's native link resolution)

Agents use these on demand. No tool is invoked at SessionStart by default.

### Capture targets (continuity-tenant scoped)

When an agent has a durable observation to record, it picks the target by content. All targets are within continuity's tenant (`<vault>/_continuity/`):

- `continuity capture --project <name> --kind observation <body>` → appends dated section to `<vault>/_continuity/projects/<name>/observations.md`
- `continuity capture --project <name> --kind decision --slug <slug> <body>` → creates `<vault>/_continuity/projects/<name>/decisions-draft/<date>-<slug>.md` with frontmatter (decisions captured by agent are drafts; user promotes to project's user-curated `decisions/` if blessed)
- `continuity capture --kind general <body>` → appends to `<vault>/_continuity/general/observations.md`
- `continuity capture --kind inbox --slug <slug> <body>` → creates `<vault>/_continuity/inbox/<date>-<slug>.md` (default for ambiguous captures)

Each capture also updates `<vault>/_continuity/INDEX.md` in the same operation (atomic — either both succeed or both fail).

**Important:** continuity NEVER writes to user-curated locations (10-projects/<Name>/narrative.md, 10-projects/<Name>/decisions/, 20-areas/, 30-resources/, journal/) via the capture path. Those locations only receive continuity content via the explicit promotion mechanism (next section).

journal/ specifically remains vault-cli's tenant — continuity doesn't write there. If continuity captures something time-of-day-relevant, it goes to general/observations.md or to the project's observations.md, with the date in the H2 heading.

### Index update on write

Two paths:

1. **Agent writes via `continuity capture`** — the tool atomically updates the file AND the index entry. No drift.

2. **User writes directly in Obsidian** — index drifts. Mitigations:
   - **Lazy validation on read**: when an agent reads INDEX.md and intends to use a row, it spot-checks the row's `last_modified` against the actual file mtime. If stale, agent regenerates that row.
   - **Periodic full reconciliation**: vault-cli's daily recap walks the vault, updates any index rows where mtime > recorded last_modified.
   - **Optional**: `continuity reindex` CLI for manual full rebuild.

The combination handles both hot-path correctness and background freshness without filesystem watchers (no extra infrastructure).

### Promotion mechanism (cross-tenant)

When a continuity-generated observation deserves elevation to user-curated content, promotion explicitly moves it across the tenant boundary. Two types of promotion:

1. **Within-tenant generalization**: continuity observation in a project's `observations.md` → continuity's `general/observations.md` (recognized as broader than one project, but still continuity-generated)
2. **Cross-tenant elevation**: continuity observation → user-curated location (`10-projects/<Name>/narrative.md`, `20-areas/<area>.md`, `30-resources/<topic>.md`, or `10-projects/<Name>/decisions/`). This is the user explicitly blessing the observation as part of their curated content.

**Promotion is extraction with provenance trail.** Original continuity-tenant location is never modified destructively; the target file synthesizes/restates and links back.

#### Detection: recap-mediated

The daily recap (vault-cli) is extended with a "promotion candidates" section. After listing the day's activity, it surfaces:

```markdown
## Promotion candidates

The following observations from today look like they may apply beyond their
captured local context. Promote to a higher-scope location?

1. **From `10-projects/agent-swarm/narrative.md` (2026-05-03 entry):**
   "Memory injection isn't contamination — it's part of the system being
   measured. Capture conditions per use; let the analyst interpret."

   Suggested target: `20-areas/methodology.md` — recurring
   experimental-design principle. Approve? (y/n/skip/edit-target)

2. **From `journal/2026-05-03.md`:**
   "Plugin cache lives at ~/.claude/plugins/cache/<plugin>/<version>/, not
   at dev path. Editing dev doesn't propagate."

   Suggested target: `30-resources/claude-code-platform.md` — Claude Code
   platform fact. Approve? (y/n/skip/edit-target)
```

Detection is initially LLM-driven (recap calls Claude with the day's captures + a prompt asking "which of these look like cross-cutting principles vs project-specific?"). Could be rule-based later if patterns emerge.

#### Execution: extraction with bidirectional links

When promotion is approved:

1. The higher-scope file gets a new dated section synthesizing the observation in its general form
2. The original local capture remains unchanged
3. A `<!-- promoted-to: <path> -->` HTML comment is added at the original location's section
4. The higher-scope section includes a `<!-- promoted-from: <original-path>#<heading> -->` reference

Both files now know about each other. Future readers of either find the other. Original location is still the truth-of-record (when, where, in what context the observation arose); higher-scope file is the interpretation/generalization.

#### Promotion paths

Typical patterns:

- **Continuity-project-observation → User-narrative**: project-state observation that the user blesses as part of the official project narrative (`_continuity/projects/<Name>/observations.md` → `10-projects/<Name>/narrative.md`)
- **Continuity-decision-draft → User-decision**: agent-captured decision that the user blesses as official (`_continuity/projects/<Name>/decisions-draft/X.md` → `10-projects/<Name>/decisions/X.md`)
- **Continuity-project-observation → User-area**: project-specific observation that reflects a cross-cutting preference or methodology (`_continuity/projects/<Name>/observations.md` → `20-areas/<area>.md`)
- **Continuity-general-observation → User-resource**: general observation that's actually a reference fact (`_continuity/general/observations.md` → `30-resources/<topic>.md`)
- **Continuity-inbox → anywhere**: triage of unsorted captures during recap

Within-tenant generalization (project observations → general observations) doesn't require user approval — agent or recap can do it. Cross-tenant elevation requires explicit user approval (it's adding to user-curated content).

Demotion (rare): if a promoted entry turns out to be wrong-targeted, the comment markers make it traceable; demotion just removes the user-curated section and the promoted-to comment. The continuity-tenant original is unchanged.

### Auto-memory protocol injection (minimal)

A short instruction at SessionStart, much smaller than v2's protocol:

```
Memory: vault-native, lazy-read. Continuity is one tenant; user/vault-cli own others.
- Read INDEX (`continuity index`) when starting a non-trivial task that might
  benefit from prior context. Cheap (~2KB). Indexes the whole vault.
- Read specific files when index points at relevance (any tenant).
- Capture durable observations via `continuity capture` (writes to continuity tenant
  at <vault>/_continuity/, updates index atomically). NEVER write directly to
  10-projects/, 20-areas/, 30-resources/, journal/ — those are user/vault-cli
  territory, reachable only via explicit promotion.
- Don't pre-load. The vault is large; only read what you need.
```

That's the entire SessionStart contribution. Adds ~10 lines to context, not 50.

### Cross-machine

Vault git syncs everything (continuity-tenant content included). Mitigations from v2 still apply at the vault layer:
- `<vault>/.gitattributes` includes `*.md merge=union` for files prone to concurrent appends (continuity tenant: `_continuity/**/*.md`; user/vault-cli tenant: `journal/*.md`, `10-projects/**/narrative.md`, `20-areas/*.md`) — set up by `continuity install` once
- Vault sync atomicity: blocking push at SessionEnd up to short timeout, marker file for retry on failure, lockfile coordination for concurrent machines

Per-machine state (very minimal): just the agent's current session metadata; no per-machine memory store. Index is in vault and shared.

### Schema versioning

Index frontmatter includes `protocol_version: N`. If continuity reads an index with mismatched major version, it refuses + prompts for upgrade migration. Vault content itself is plain markdown — no schema lock-in; if continuity goes away, the vault is still fully functional.

### Plugin sensitivity stance

The plugin code contains no user data. Vault paths are configured by user via `~/.config/continuity/config.yaml`. Plugin can be open-sourced freely.

## Implementation Phases

See companion document `2026-05-03-implementation-plan-v3.md` for full phase breakdown.

Summary (much smaller than v2):

| Phase | Scope | User-visible value |
|---|---|---|
| 0 | Plugin scaffolding (config, CLI entry, hook stubs) | none |
| 1 | Capture tools (`continuity capture`) + index generation | manual capture works; `continuity index` returns current state |
| 2 | Read tools (`continuity search/read/recent/backlinks`) | agent can lazy-read vault content |
| 3 | SessionStart minimal protocol + first-time project resolution prompt | agent knows about vault on entry; new projects offered bootstrap |
| 4 | Capture-target inference + agent integration with capture/read tools | agents naturally capture to right place; observations accumulate |
| 5 | Recap extension: promotion candidates surfaced in daily recap | promotion mechanism live |
| 6 | Cross-machine vault sync hardening (atomicity, marker files, .gitattributes setup) | reliable cross-machine operation |
| 7 | (Optional) PM-agent generalization for STATUS regen | per-project STATUS automation |

Phases 0–4 deliver core value. Phase 5 adds promotion. Phase 6 hardens cross-machine. Phase 7 is bonus from v2.

**Critical contrast with v2:** no polished view layer, no regenerator, no within-session staleness mitigation, no provenance headers (because there's no synthesis layer to vouch for — promoted entries explicitly state their provenance via the bidirectional links). Roughly 1/3 the implementation surface.

## Future enhancements

- **LLM-driven semantic search** in addition to grep — for cases where keyword search misses the right entry
- **Topic clustering visualization** — Obsidian graph of vault entries by tag/promotion lineage
- **Per-machine "context buffer"** — lightweight scratch for in-progress work that doesn't yet warrant a vault entry; promoted to vault when done
- **Decision retrospective tooling** — given a project's decisions/ dir, surface "decisions that may need revisiting" based on age + relevance to current work

## Out of Scope

- Replacing vault-cli (composes with it)
- Cross-project dependency tracking
- Real-time collaboration features
- Encryption at rest (vault-level concern)
- Memory beyond the vault (agent only sees what's in the vault — by design)

## Acceptance

The plugin succeeds if, after a 30-day absence, the user can:
1. Open Claude in a project they haven't touched
2. Get a useful 200-word brief at SessionStart driven from the index + recent narrative
3. Start work without 1+ hour of catchup

And in steady state:
1. Observations recorded today are findable tomorrow via index lookup or search
2. Cross-machine work doesn't lose observations (vault git handles it)
3. Recurring patterns get surfaced as promotion candidates and find their way to the right cross-cutting location
4. Memory access during a typical session adds <500 tokens of context (vs v2's polished-view auto-injection which would have added thousands)

## Acknowledgments

v3 supersedes v2 (2026-05-03) which superseded v1 (2026-05-02). The progression:
- v1: established two-layer memory model (sources + polished) with auto-injection
- v2: refined v1 with 19 risks-derived improvements (regenerator semantics, provenance, cross-machine, etc.) — same overall architecture
- v3: reframed entirely on user direction. Vault IS memory. Lazy read. Index-on-write. Recap-mediated promotion.

The v3 model is much closer to what the vault already is, and much further from a parallel knowledge base.
