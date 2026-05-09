---
date: 2026-05-08
project: continuity (cross-cutting: memory, pm, experiment)
type: design
status: draft
authors: [user, claude]
builds-on:
  - 2026-05-06-continuity-design-v4.md
  - 2026-05-07-implementation-plan.md
  - ~/.claude/plugins/continuity/.claude/decisions/2026-05-07-memory-as-own-plugin.md
  - ~/.claude/plugins/continuity/.claude/decisions/2026-05-07-pm-as-own-plugin.md
  - ~/.claude/plugins/continuity/.claude/decisions/2026-05-07-continuity-as-context-stitcher.md
refines: continuity's WriteProvider pattern (v4 + 2026-05-07 impl plan), generalized to all state-owning plugins
scope: cross-plugin contract specification only; phase sequencing stays in the 2026-05-07 implementation plan
---

# Cross-plugin reader/writer architecture

## Why this doc

v4 framed continuity as a context stitcher with a configurable write surface. The 2026-05-07 implementation plan codified that as a `WriteProvider` interface inside continuity (`VaultWriteProvider`, `MemoryWriteProvider` stub).

What v4 does not yet specify: **how do memory and pm consume each other and expose themselves to continuity?** When memory plugin lands, what is its API surface? When pm lands, what does it expose? Today's conversation worked the answer out: every state-owning plugin uses the same `(reader, writer)` shape continuity already prototypes.

This doc generalizes that pattern. Same vocabulary across the four-plugin picture.

## The pattern: `(reader, writer)` per plugin

Every state-owning plugin exposes exactly two interface types:

- **`<plugin>_reader`** — read surface. Small fixed methods. Consumed by sibling plugins and (where exposed via MCP) the model.
- **`<plugin>_writer`** — write surface. Small fixed methods. Used by producers (model auto-capture, hooks, CLI, other plugins delegating via a configured write-provider).

Each interface admits **multiple implementations**. Implementation choice is configuration, not API. Examples:

- FS-backed (default)
- sqlite-backed (future migration)
- in-memory fixture (tests)
- cached wrapper (composes another)
- remote (cross-machine future)
- multi-vault (one instance per vault)

Critically: the MCP/CLI surface is **not** one tool per source-of-write or per-access-pattern. It is a small fixed set of method calls on whichever instance is configured. Plurality lives at the implementation level, not the operation level.

## Layer stack

```
+----------------------------------------------------------------------+
| continuity (stitcher)                                                |
|   continuity_writer: composes via N readers; writes through          |
|                      configured WriteProvider (vault | memory)       |
|   continuity_reader: briefs, drafts, recorded insights               |
|   + independently-active loops/hooks (per v4)                        |
+----------------------------------------------------------------------+
       | reads via               | reads via            | reads via
       v                         v                      v
+--------------+  +--------------+  +------------------+  +--------------+
|memory_reader |  | pm_reader    |  | experiment_reader|  | serena, git, |
|memory_writer |  | pm_writer    |  | experiment_writer|  | github, ...  |
+--------------+  +--------------+  +------------------+  +--------------+
       |                 |                    |
       +-----------------+--------------------+
                         | all built on
                         v
                +------------------+
                | vault_reader     | <- Phase 0 shipped
                | vault_writer     | <- emerging in continuity Phase 1;
                |                  |    promote to shared layer when
                |                  |    memory plugin starts
                +------------------+
                         |
                         v
                    <vault>/ on disk
```

External MCP sources (serena, git, github) are **additional readers** continuity can plug in. They are not built on vault and are not subject to vault-tenancy rules.

## Tenancy rules

1. **Cross-plugin reads go through reader interfaces.** No plugin reads another plugin's files directly. (Exception: `vault_reader` exposes paths regardless of which plugin "owns" the subtree — vault is below the plugin layer.)
2. **Writes go to your own subtree.** Each plugin's writer touches only its tenant subtree:
   - memory → `<vault>/40-archive/memory/sources/*.md`
   - pm → `<vault>/10-projects/<Name>/*`
   - experiment → TBD when experiment plugin scoped
   - continuity → `<vault>/_continuity/*` (when configured to write to vault)
3. **Path resolution via `vault_reader.path_for(...)`.** No plugin hardcodes vault paths.
4. **External sources are pure readers.** Continuity reads serena/git/github but never writes through them.

The v4-established exception: continuity's write target is *configurable* (currently `vault` per Phase 1 plan, later optionally `memory`). When configured to memory, continuity's writes route through `memory_writer.append(...)` instead of `vault_writer.write(...)`. The configurability lives in continuity, not the receiver.

## Per-plugin contracts (sketch)

Method shapes are illustrative. Lock-in happens when each plugin enters its build phase; this section is a target for that lock-in.

### vault — Phase 0 read shipped; write emerging

`vault_reader` (shipped):
- `path_for(kind, *args) -> str` — canonical path resolution (`kind` in {`project`, `memory_corpus`, `continuity_subtree`, ...})
- `read(path) -> str` — raw file content
- `list(dir, pattern?) -> [str]`
- `exists(path) -> bool`
- `metadata(path) -> Metadata`

`vault_writer` (Phase 1 plan introduces `VaultWriteProvider` inside continuity; this doc proposes promoting it to a vault-layer concern shared across plugins when memory plugin starts):
- `write(path, content, frontmatter?) -> ()`
- `append(path, content) -> ()`
- `mkdir(path) -> ()`
- (no delete in v1; require explicit operator action)

### memory — to be built

`memory_reader`:
- `query(topic?, project?, scope?, since?, limit?) -> [Observation]`
- `get(observation_id) -> Observation`
- `topics() -> [Topic]`
- `index() -> [IndexEntry]` — what `MEMORY.md` represents

`memory_writer`:
- `append(topic, body, scope, project?) -> observation_id` — applies dedupe, frontmatter, index update
- `amend(observation_id, change) -> ()`
- `mark_stale(observation_id, reason) -> ()`

The auto-memory protocol currently encoded as CLAUDE.md prose (two-step write, scope inference, refusal criteria) becomes the default `memory_writer` implementation's policy. CLAUDE.md eventually shrinks to "the memory plugin is loaded; talk to it via these tools."

### pm — deferred per current plan

`pm_reader`:
- `list_projects() -> [Project]`
- `get_project(name) -> ProjectState`
- `decisions(name, since?) -> [Decision]`
- `status(name) -> Status`
- `narrative(name) -> str` — *ownership of narrative is open; see Open*

`pm_writer`:
- `create_project(name, metadata) -> ()`
- `write_decision(name, decision) -> decision_id`
- `update_status(name, status) -> ()`
- `append_narrative(name, section) -> ()` — caller-supplied content; pm does not synthesize

### experiment — scope TBD

When this plugin enters scope, expect the same shape: `experiment_reader` (runs, contexts) + `experiment_writer` (start_run, end_run, record_observation). Bench-start/end scripts likely migrate into the writer.

### continuity — already in motion via Phase 1

`continuity_writer`:
- Composes via injected reader dependencies: `memory_reader`, `pm_reader`, `experiment_reader`, `vault_reader`, optional `serena_reader`, `git_reader`, `github_reader`
- Writes through configured `WriteProvider` (vault | memory)
- Operations: `compose_resume_brief(project)`, `compose_status(project)`, `record_insight(...)`, `draft_narrative(project)`, `session_end_capture(signals)`

`continuity_reader`:
- `briefs(project?) -> [Brief]`
- `insights(project?, since?) -> [Insight]`
- `drafts(project?) -> [Draft]`

Independently-active surface (loops, hooks) per v4 lives alongside these — not part of the reader/writer contract.

## Multiplicity

Each interface admits multiple implementations. Common patterns:

- **Tests** swap in fixture readers/writers
- **Storage migration** runs dual-write (FS writer + sqlite writer chained as a composite implementation of the same interface)
- **Composition**: `CachedReader(FsReader(...))` — wrappers
- **Multi-vault**: two `vault_reader` instances pointed at user-vault and shared-vault
- **Per-source-policy writers**: auto-memory writer (aggressive scope inference, dedupe) and CLI writer (caller-supplied scope, light dedupe) both implementing `memory_writer` — selected per call site

Growth happens by adding implementations and reader source plugins, not by sprouting new tool names.

## Optional readers and graceful degradation

Continuity declares its reader dependencies typed and explicit. Some are required (memory_reader once memory plugin lands); others are optional (serena_reader, git_reader, github_reader). When an optional reader is unavailable, the synthesized output omits that section rather than crashing. This makes continuity portable across environments with different available sources.

## Promotion is a write call site, not new machinery

Promotion (continuity-draft → pm-canonical) is:
1. continuity_writer drafts to `_continuity/<Name>/narrative-draft.md`
2. A promote operation reads the draft via `continuity_reader`, calls `pm_writer.append_narrative(name, content)`, marks the draft as promoted
3. Trigger (manual command, scheduled, end-of-session) is policy

No "promotion writer." Just a writer call from the right context. Same mechanism handles narrative, status pages, and any future continuity-generated → user-curated artifact.

## What this resolves

- **Cross-plugin contract:** reader interfaces; small, typed, stable
- **v4 "provider" vocabulary generalized:** every state-owning plugin has a `(reader, writer)` pair, same shape
- **Auto-memory protocol's destination home:** `memory_writer` default-implementation policy
- **Promotion mechanism:** writer call site, not infrastructure
- **External sources** (serena, git, github): readers continuity depends on; degrade gracefully when absent
- **Service-vs-data tension:** hybrid — files canonical and inspectable, typed read surface for cross-plugin use

## Decisions as a peer artifact type

Memory is the substrate for **observations** (descriptive, append-only, time-indexed: "after X, Y happens"). The architecture also needs a home for **decisions** (prescriptive, structured: "we're choosing C because performance matters; alternatives considered: A, B"). These are parallel artifact types, not one a sub-type of the other.

Decisions are not owned by any single plugin. Each scope-owning surface hosts decisions in its own subtree, with the rule **decisions live at the root of the scope they govern**:

| Subject of decision | Location |
|---|---|
| A specific project | `<vault>/10-projects/<Name>/decisions/` |
| All projects (project-domain meta) | `<vault>/10-projects/decisions/` |
| Memory itself | `<vault>/40-archive/memory/decisions/` (when memory plugin lands) |
| A specific plugin's internal architecture | `<plugin>/.claude/decisions/` |
| Personal / cross-everything (preferences, workflow, tooling) | `<vault>/meta/decisions/` |

Promotion still applies and still lifts artifacts across scope when applicability broadens — but promotion does not convert observations to decisions or vice versa. Each type stays itself.

See `~/.claude/plugins/continuity/.claude/decisions/2026-05-08-decisions-as-peer-artifact-type.md`.

## Open

Resolved this session (see `~/.claude/plugins/continuity/.claude/decisions/2026-05-08-*.md`):

- ~~**Narrative ownership.**~~ Resolved: pm canonical; continuity drafts to `<vault>/_continuity/<Name>/narrative-draft.md`; promote step calls `pm_writer.append_narrative(...)`. See `2026-05-08-pm-owns-project-narratives.md`.
- ~~**`vault_writer` placement.**~~ Resolved: continuity-local through Phase 1; promote to shared vault layer when memory plugin lands (Phase 2.x). See `2026-05-08-vault-writer-stays-continuity-local.md`.
- ~~**Decision mirroring.**~~ Reframed and resolved: decisions are a peer artifact type to observations, not nested in pm or memory; routed by scope per the table above. See `2026-05-08-decisions-as-peer-artifact-type.md` and the new "Decisions as a peer artifact type" section above.

Still open:

- **Reader signatures lock-in.** Methods sketched here are illustrative; freeze each interface when its plugin enters build phase. Vault's signatures (Phase 0 already shipped) should be locked retroactively in this doc.
- **MCP tool surface per plugin.** Do all reader/writer methods become MCP tools, or only a subset (rest as in-process library calls)? Cross-plugin consistency question; matters for cross-machine since in-process calls don't cross machine boundaries.
- **Write authority enforcement.** Does the writer interface validate that the calling tenant matches the subtree being written, or is tenancy convention-only? Lean: convention-only at first; promote to interface-enforced if accidents happen.

## Phase implications (overlay on 2026-05-07 plan)

- **Phase 1 (in progress):** continuity's `WriteProvider` ships in continuity package. Treat as the prototype that will generalize. Keep `VaultWriteProvider` continuity-local for now.
- **Phase 2.x (memory plugin):** build `memory_reader` / `memory_writer` with the shape sketched here. Migrate `MemoryWriteProvider` from stub to real. **Decide whether to promote `vault_writer` out of continuity at this point.**
- **Phase 3+ (pm plugin):** build `pm_reader` / `pm_writer` with the shape here. **Resolve narrative-ownership question before this lands.**
- **Continuity Phase 2 (provider integration):** generalize from "memory provider stub" to typed reader-set; declare which readers are required vs. optional.

## Related documents

- `2026-05-06-continuity-design-v4.md` — continuity-as-stitcher framing
- `2026-05-07-implementation-plan.md` — phased build plan
- 2026-05-07 decisions for memory / pm / continuity extraction
- 2026-05-08 decisions: `2026-05-08-pm-owns-project-narratives.md`, `2026-05-08-vault-writer-stays-continuity-local.md`, `2026-05-08-decisions-as-peer-artifact-type.md`
- `2026-05-03-phase-0-impl.md` — Phase 0 reference
