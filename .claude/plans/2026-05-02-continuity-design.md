---
date: 2026-05-02
status: draft
authors: [user, claude]
scope: cross-cutting (continuity plugin, vault-cli, ~/.claude, Obsidian vault)
license: open-source (planned)
---

# Project Continuity Upgrade

## Problem

Returning to a personal project after a long absence is expensive and lossy. Two specific failure modes have been observed:

1. **Recall is slow.** Re-loading the project's mental model takes hours of reading scattered artifacts (commits, issues, design docs, narratives), even when the substrate is well-organized.
2. **Decisions rot.** Choices made in the moment — especially the *why* and the alternatives considered — fade or are never captured. The code shows the decision; nothing shows the reasoning.

These problems intensify with absence length. They also generalize across all of the user's personal projects (LOGOS, Saoirse, Chiron, Agent Swarm, etc.) — they're not LOGOS-specific.

The existing infrastructure addresses this only partially:

- `vault-cli` automates daily recaps and weekly rollups
- The vault uses PARA layout with per-project notes, `narrative.md`, and Dataview queries
- The LOGOS-bound project-manager agent regenerates `STATUS.md` on demand
- agent-swarm currently injects an auto-memory protocol that captures user/feedback/project/reference notes
- Source-control hygiene exists per-repo

The **gap** is everything that requires manual upkeep: per-project narrative refresh, decision capture, resumption brief generation. These chores are the first to lapse during busy periods, which is precisely when continuity matters most. Additionally, memory functionality is currently split between agent-swarm (protocol injection) and a hard-coded user-level path — a coupling that a properly-scoped continuity plugin should resolve.

## Constraints

These principles emerged during design and should be treated as invariants:

1. **No urgency framing.** Personal projects don't need backlog/ramp/SLA framing.
2. **Automation over CLI rituals.** The user does not reach for vault-cli commands during busy weeks; anything that depends on remembering to type a command will fail.
3. **Project-generic, not per-project.** Mechanisms must work for any project conforming to the substrate, parameterized by project name/path.
4. **Prompt at lifecycle boundaries; automate inside them.** Ambiguous classifications (is this a project? is this a decision? is this a new MCP server?) get a one-time prompt with persistent memory of the answer. Bounded actions (regenerate STATUS, draft narrative patch) run silently. Reconciliation that the system can compute confidently (e.g., timestamp-based merge) skips the prompt; only genuinely ambiguous cases ask.
5. **Drafts to a queue, never silent edits.** Automated content lands in `.pending/` for human review. Live state changes only on explicit accept.
6. **Sparse-journal-tolerant.** The daily journal stream is thin (low activity → low content). Continuity cannot be load-bearing on journal text alone.
7. **Regenerate, don't maintain.** Aggregate views (status, resumption briefs, polished memory views) are rebuilt from authoritative sources on demand, not hand-maintained.
8. **Optional integrations, never dependencies.** Tools like Serena or other MCP servers enrich outputs when present and degrade gracefully when absent.
9. **Plugin code is shareable; sensitive data is user-configurable.** Plugin behavior, structure, and non-sensitive defaults live in the plugin's repo (which can be public/open-source). Sensitive data directories — memory, drafts, queues, anything containing user content — are referenced by configurable paths with sensible defaults. Users decide where to host their own data, including pointing at existing private repos like a personal vault. Plugins never own user content; they only know how to find it.
10. **Memory is a record, not a sorter.** Memory source files preserve observations append-only; the memory layer performs no reconciliation, no merge logic, no interpretation. Reading memory and reasoning about it is a separate concern from recording observations. Polished views (derived from source) are where synthesis happens — they are regenerable, named explicitly, and never modify source.

## Existing System (do not rebuild)

- **Vault PARA layout** — `00-inbox/`, `10-projects/<Name>/`, `20-areas/`, `30-resources/`, `40-archive/`, `journal/`, `_templates/`
- **Per-project notes** — `<Name>.md` with `type: project, status: <state>` frontmatter; Dataview queries over `10-projects/`
- **Daily recap** — Cron 11 PM. Aggregates git, GitHub, Claude session metadata, shell, gcal, captures
- **Weekly rollup** — Cron Sun 11:30 PM. Per-repo/project breakdown with reflection prompts
- **Claude session harvest** — `vault harvest [--project X]`. Currently metadata only; deep harvest is part of this design
- **Per-project narratives** — LOGOS has `narrative.md` (9.9 KB) with thesis, per-subsystem state, dated decisions, current state. Other projects vary
- **Project-manager agent** — LOGOS-bound. Owns VISION/STATUS/PROJECT_TRACKING. Modes: status update, idea capture, goal assessment, vision review
- **Multi-machine sync** — Vault is git-backed; `vault sync` keeps machines aligned

### Relationship to agent-swarm

Agent-swarm provides a broad set of execution-oriented workflows (iterate, parallel-orchestrate, debug, pipeline, experiment, pr-comment, verify, etc.) that remain the canonical tools for *doing the work*. This design does not touch them.

Five agent-swarm capabilities overlap with concerns this design addresses, and **this design supersedes all of them**:

- `remember` → memory observations appended via Component 9
- `distill` → deep transcript harvest (Component 7) feeding narrative + decisions
- `ctx` → SessionStart resumption brief (Component 2)
- `develop` → generalized PM agent (Component 4)
- **Auto-memory protocol injection** → continuity's session-start hook (Component 9), with the path made configurable

agent-swarm's `protocol_assembly` (or wherever the auto-memory section currently lives) drops the auto-memory instructions; continuity's session-start hook injects an equivalent (or refined) protocol pointing at a configurable path.

The continuity system has **no code dependency on agent-swarm**. They run independently; the new system uses Claude Code primitives (hooks, skills, agents, MCP) directly.

### Built-in `memory.json` non-integration

Claude Code's built-in `~/.claude/memory.json` is intentionally not integrated. The file-based memory pattern (continuity-managed auto-memory + vault decisions + narrative) is the canonical store for durable knowledge; opaque JSON memory is treated as runtime state, not durable knowledge.

## Proposed Architecture

### Packaging and licensing

The continuity system ships as **a Claude Code plugin** named `continuity`, installed to `~/.claude/plugins/continuity/`. The plugin has its own git repo, **planned as open-source**, separate from any user's private data.

**Sensitive data lives at user-configurable paths**, not inside the plugin. The plugin defines defaults (XDG-compliant locations) and reads a config file for user overrides. This separation lets one plugin codebase serve both private use (one user's setup pointing at their vault) and public sharing (other users adopting with their own data locations).

```
~/.claude/                                  ← Claude Code install (no longer a repo)
├── CLAUDE.md
├── ...                                     ← per-machine config; not source-controlled at this level
└── plugins/
    ├── installed_plugins.json
    ├── agent-swarm/                        ← independent plugin
    └── continuity/                         ← this plugin (public/open-source repo)
        ├── .git/
        ├── .claude/
        │   └── plans/                      ← design docs (this file)
        ├── skills/project/
        ├── agents/project-manager.md
        ├── hooks/
        │   ├── hooks.json                  ← declares SessionStart/SessionEnd hooks
        │   ├── sessionstart.sh
        │   └── stop.sh
        ├── lib/
        ├── data/                           ← non-sensitive plugin data
        │   ├── mcp-capabilities.yaml
        │   └── no-bootstrap.list
        ├── config.example.yaml             ← shipped defaults, public
        └── ...

~/.config/continuity/config.yaml            ← user's local override (gitignored from plugin)
                                            ← points at sensitive directories of user's choosing

<sensitive paths, configured>:              ← e.g., for this user:
  memory_dir: <vault>/40-archive/memory/    ← inside the user's private vault
                                            ← contains sources/ (sync'd) and polished/ (gitignored)
```

### Project lifecycle

A project is an emergent property of behavior, not a thing the user declares.

```
[unknown dir] --SessionStart prompt--> [active] --inactivity--> [paused] --inactivity--> [dormant] --confirm--> [archived]
                  |                       ^                       ^                        ^
                  +-- "no" --> [denylist]  +---- new activity -----+------------------------+
```

States and transitions:

| State | Trigger | Behavior |
|---|---|---|
| `active` | First-session yes, or any activity from a non-active state | Full automation: SessionStart brief, Stop drafts, nightly STATUS regen |
| `paused` | 14 days no activity | Same as active but lower-priority for batched jobs |
| `dormant` | 60 days no activity | STATUS regen skipped; SessionStart still briefs on entry |
| `archived` | Explicit confirm, or 365+ days with prompt | All automation off; vault note retained for history |
| denylisted | "no" answer at first SessionStart | Never re-prompted for this path |

State is stored in `<vault>/10-projects/<Name>/<Name>.md` frontmatter (`status:` field). Transitions log to the daily journal.

### Components

**1. Project bootstrap script.** Lives at `<plugin>/lib/bootstrap.py`. Given a path and a name, idempotently creates only vault content:

- `<vault>/10-projects/<Name>/<Name>.md` with all metadata in frontmatter (`type: project, status: active, created: <date>, repos: [<paths>], mcp_servers: [...]`)
- `<vault>/10-projects/<Name>/narrative.md` as a stub
- `<vault>/10-projects/<Name>/decisions/` (empty)
- `<vault>/10-projects/<Name>/.pending/` (empty)
- A journal-line append: *"New project bootstrapped: [[<Name>]]"*

The project's own repo is not touched. No project-local `.claude/` is created; metadata lives entirely in vault frontmatter.

**Project name defaults.** If a name isn't supplied:

1. If `project_root` is a git repo with an `origin` remote, parse the remote URL's basename (strip `.git`) and use that
2. Otherwise, fall back to the directory basename

The default is pre-filled in the SessionStart prompt; the user can override with "yes, call it X" to choose a different name. Casing is preserved as-is — no transformation.

**2. SessionStart hook (`<plugin>/hooks/sessionstart.sh`).** Declared in `<plugin>/hooks/hooks.json`. Logic:

1. Run `vault sync --pull` to fetch latest cross-machine state
2. Walk up from `cwd` to highest dir with `.git/`, `CLAUDE.md`, or `.serena/` — call this `project_root`
3. Look up `project_root` in vault: any `10-projects/*/` whose frontmatter `repos:` includes it?
4. **Match** → silently load that project's `narrative.md` excerpt + recent activity + MCP enrichment into context. Resume mode.
5. **No match, not denylisted** → surface a prompt: *"This dir (`<path>`) isn't tracked. Track as project `<proposed-name>`? [yes / no / not yet / yes, call it X]"* (with `<proposed-name>` from the bootstrap naming algorithm)
6. **No match, denylisted** → no prompt, no action.

User answers in conversation:

- **yes** → bootstrap runs in background; resume-mode brief presented
- **no** → append to `<plugin>/data/no-bootstrap.list`; never re-prompt
- **not yet** → no action; ask again next session
- **yes, call it X** → bootstrap with that name

If `vault sync --pull` fails, hook falls back to local state and notes the staleness — never blocks.

**Rename detection.** When a project is matched, the hook checks for folder/frontmatter name mismatch. If timestamps clearly favor one side (>1h difference between most recent change to the folder vs. the frontmatter), it silently reconciles to the more recent name and updates internal references. If both sides changed within the same window, it prompts the user to choose.

This same hook also injects the auto-memory protocol (Component 9) on every session start, regardless of whether the cwd resolves to a tracked project.

**3. Stop hook (`<plugin>/hooks/stop.sh`).** Declared in `<plugin>/hooks/hooks.json`. When a Claude Code session ends and `cwd` resolves to a tracked project:

1. A small agent reads the conversation
2. Drafts decision notes for any decision-shaped exchanges → `<vault>/10-projects/<Name>/.pending/decision-<timestamp>-<slug>.md`
3. Drafts narrative-patch suggestions for sections that appear out of date → `<vault>/10-projects/<Name>/.pending/narrative-patch-<timestamp>.md`
4. Decisions and patches may include stable references (Serena symbols, GitHub issue numbers, knowledge-graph node IDs) when relevant MCP servers are listed for the project. Decisions can carry multiple anchors.
5. Drafts must be **self-contained** (no references to "the conversation" — reviewer may be on a different machine).
6. Frontmatter on each draft includes `session_id` and `session_machine` for traceability.
7. **Polished memory regeneration**: if any source memory files were modified during the session, regenerate the corresponding polished views (per-machine, gitignored). Async, doesn't block.
8. After drafts are written, runs `vault sync --push` to make drafts immediately available on other machines.
9. Runs fully async (fork-and-forget) — does not block session end.
10. Never edits live state. Never prompts the user.

All draft acceptance lands in vault-tracked paths (`decisions/`, `narrative.md`). Because the vault is a git repo, every accept is rollbackable via `git revert`. This makes batch acceptance safe (see Component 5).

**4. Project-manager agent (generalized).** Lives at `<plugin>/agents/project-manager.md`. Reads project config from the project's vault note frontmatter.

Modes: status update, idea capture, goal assessment, vision review, narrative refresh (new). All consult listed MCP servers.

**5. `/project` skill.** Lives at `<plugin>/skills/project/SKILL.md`. Single front-door verb with subcommands:

| Subcommand | Action |
|---|---|
| `/project` | Show resolved project: status, narrative-staleness, pending count, missing MCP servers |
| `/project list` | All projects grouped by status |
| `/project init [name]` | Bypass auto-detection: bootstrap current dir |
| `/project resume` | On-demand resumption brief |
| `/project status` | Regenerate STATUS.md |
| `/project narrative` | Propose narrative.md patch |
| `/project decide "X because Y"` | Capture decision; bypass `.pending/` (slash IS confirmation) |
| `/project pending` | Walk through queued drafts: accept / reject / edit per item; shows session origin |
| `/project pending accept-all` | Accept every vault-local pending item for the current project |
| `/project pending accept-all --type X` | Filter by type |
| `/project pending accept-all --all-projects` | Across every active project |
| `/project pending accept-all --include-external` | Also accept items affecting remote state |
| `/project archive` | Explicit archival (always confirms) |

#### Batch acceptance semantics

- **Default scope is vault-local** — git-rollback-recoverable
- **External-effect items skipped by default** — opt-in via `--include-external`
- **One commit per batch** — `batch-accept: <Project> — <N> decisions, <M> narrative-patches`
- **Conflicts are held back** — overlapping narrative patches go individual
- **Lifecycle edits are never bulk-accepted** — always require individual confirmation

#### `/project pending` review surfaces session origin

Each item shows source machine and timestamp so reviewers on other machines know the conversational context isn't local.

**6. Daily recap extensions.** Four additions to nightly `vault recap`:

- For each `status: active` project: regenerate STATUS.md
- For each tracked project: check if state transition fires
- Append per-project drift line if narrative.md is stale
- Include today's memory observations from `<memory_dir>/sources/` under a "Memory captures" section in `journal/YYYY-MM-DD.md`. Lightweight aggregation; just extracts dated sections matching today

**7. Deep transcript harvest.** Lives at `<plugin>/lib/deep_harvest.py`. Reads JSONL transcripts and extracts structured per-session notes with `session_machine` metadata. Writes to vault.

**8. MCP enrichment (optional).** Per-project `mcp_servers` list in vault frontmatter. Capability descriptions in `<plugin>/data/mcp-capabilities.yaml`. Intent (synced) vs. availability (per-machine) — gracefully degrades when servers missing.

#### Per-project frontmatter

```yaml
---
type: project
status: active
repos: [...]
mcp_servers: [serena, github, memory]   # optional; omit if none
---
```

#### Capability descriptions

`<plugin>/data/mcp-capabilities.yaml`:

```yaml
serena:
  role: "Semantic code navigation. Use for listing modules, finding symbol references."
github:
  role: "GitHub state. Use for open/recent PRs, issue threads, review activity."
memory:
  role: "Knowledge graph. Use for searching nodes, reading relations."
```

New servers prompt the user once on first encounter (only on machines where the server is reachable).

**9. Auto-memory protocol injection.** Lives at `<plugin>/hooks/sessionstart.sh` (the same hook as Component 2, with this responsibility added).

#### Behavior contract

The protocol injected at session start instructs the agent to:

- Read `<memory_dir>/MEMORY.md` (the index) at session start to know what topics exist
- Read `<memory_dir>/polished/<topic>.md` for current state when consulting memory
- Drill into `<memory_dir>/sources/<topic>.md` only when temporal trajectory, contradiction-checking, or deep history is needed
- When learning something durable about the user, feedback, project, or reference, **append a new dated section to the source file** (or create a new source file if none exists)
- Update `MEMORY.md` when adding new topics

#### Two-layer data model

**Source files** (`<memory_dir>/sources/`):

- Append-only, timestamped observations
- The truth-of-record
- Sync across machines via vault git
- Each observation is an H2 heading with the datetime and machine, followed by freeform body content:

```
## 2026-05-03T14:23:45-04:00 — home-laptop

User pointed out that memory shouldn't sort itself out — it's just a record.
Reconciliation belongs in a separate layer, not baked into memory storage.

## 2026-05-03T18:47:33-04:00 — office-desktop

User noted preference for cleaner format: datetime as heading, not per line.
Body content flows freely once the heading is set.
```

Heading format: `## YYYY-MM-DDTHH:MM:SS±HH:MM — machine-tag`. Datetime appears only in the heading; the body can be one paragraph or many. Datetimes use ISO 8601 with timezone offset so cross-timezone observations remain unambiguous; seconds precision avoids collisions on rapid consecutive appends. Machine tags match the `session_machine` field used in decision drafts.

**Polished views** (`<memory_dir>/polished/`):

- Synthesized current-state distillations, derived from source
- Regenerable from source at any time
- Compact and easy to scan
- **Per-machine; gitignored from vault sync**
- Regenerated by the Stop hook for any source files modified during the session

#### Combining and reconciliation

Source files combine across machines via git's natural merge of non-overlapping appends. Each observation's heading line is unique (datetime to second precision + machine name), so concurrent appends from different machines never collide. Git produces one source file with all observations chronologically ordered; nothing is lost or modified.

The memory layer makes no judgments, performs no reconciliation, and applies no merge logic beyond append. If observations across machines look semantically contradictory, source records both; both are true at the moment they were observed. Interpretation happens in the polishing step or in the agent's real-time reasoning when reading memory — never written back to source.

#### Consumers and access patterns

The two layers serve different consumers:

| Consumer | Reads | Why |
|---|---|---|
| **Journal/recap automation** (vault-cli's nightly job) | `sources/` | Journal is chronological by nature; benefits from raw temporal observations dated within the recap window |
| **Agent at session start** | `polished/` | Agent needs quick current state, not temporal trajectory; polished is compact and synthesized once rather than re-derived on every read |
| **Agent for deep questions** | `sources/` (drill-in) | When the agent needs trajectory, contradiction-checking, or historical context, it falls back to source |

The split aligns each layer with its natural consumer. Source for chronological consumers (durable, sync'd, append-only). Polished for state-oriented consumers (regenerable, per-machine, gitignored).

#### Configurable path

`memory_dir` is read from user config at `~/.config/continuity/config.yaml`. If unset, defaults to `~/.local/share/continuity/memory/` (XDG-compliant). The protocol's path token resolves to whatever the config says.

For this user, `memory_dir` will point at `<vault>/40-archive/memory/` — inside the private vault, gaining vault sync and version control for free, semantically grouped under PARA's archive convention as kept records. Sources sync; polished views (in `<vault>/40-archive/memory/polished/`) are gitignored from the vault.

#### Migration from agent-swarm

1. Continuity's session-start hook ships with the auto-memory protocol
2. agent-swarm's `protocol_assembly` drops its auto-memory section
3. Existing memory files copy from `~/.claude/projects/-home-fearsidhe/memory/` into `<vault>/40-archive/memory/sources/` (re-formatted with a single retrospective `## YYYY-MM-DD — migration` heading wrapping their existing content as the first observation)
4. Initial polished views generated from the migrated sources
5. agent-swarm's `remember`/`distill`/`ctx`/`develop` skills are removed

Behavior is unchanged from the agent's perspective on writes — same instructions, same triggers, just a different path. Reads gain the polished layer for efficiency.

#### Plugin sensitivity stance

The plugin **never bundles user memory data**. Its repo contains code, configuration schemas, and example configs only. Each user's actual memory directory lives at their configured path, in whatever repo they choose to host it (vault, dedicated private repo, or untracked).

This is what makes the plugin shareable as open-source: there's no privacy entanglement at the code level.

### Data flow

```
[Claude session on Machine A]
   |
   |--- SessionStart hook ----> [vault sync --pull + auto-memory protocol injected]
   |                                 |
   |                                 v
   |                            [project resolution + brief or prompt]
   |                                 |
   |                                 +--- MCP enrichment (configured servers only)
   |                                 +--- Agent reads polished/ for current memory state
   |
   |--- (work happens) -------> [git commits, file edits, JSONL transcript stays local]
   |                                 |
   |                                 +--- (Claude appends observations to sources/)
   |
   |--- Stop hook ------------> [drafts to .pending/ — self-contained, with session_machine]
   |                                 |
   |                                 +--- Regenerate polished/ for any modified sources
   |                                 +--- vault sync --push (async)
   |
   v
[overnight cron, on each machine]
   |
   |--- vault recap ----------> [journal/<date>.md including memory captures from sources/]
   |--- deep harvest ---------> [per-session notes with session_machine metadata]
   |--- PM agent (per active project) -> [STATUS.md regen]
   |
   v
[user opens Obsidian on any machine]
   |
   v
[Home.md dashboard]: Dataview surfaces drift, pending counts, stale narratives
   |
   v
[user runs /project pending or /project pending accept-all]: review drafts at leisure
```

### Source control

After this design lands, the repo landscape narrows:

| Repo | Scope | Visibility |
|---|---|---|
| `~/.claude/plugins/continuity/.git/` | Plugin code, schemas, defaults, design docs | Public / open-source |
| `~/.claude/plugins/agent-swarm/.git/` | Execution workflows, narrowed scope after this lands | Independent |
| `vault-cli` (separate location) | Vault operations | Independent |
| `vault` | Personal continuity content (narratives, decisions, journals, **memory sources**) | Private |

**No user-level `~/.claude/.git/`.** With auto-memory pointing at the vault and all plugin-bound state living in plugin repos, the user-level config dir has nothing left that needs source control. It's just a Claude Code install with config files that are per-machine.

The plugin declares its hooks via `<plugin>/hooks/hooks.json`. Claude Code wires them automatically on plugin install. `settings.json` stays per-machine for secrets only — no hook config lives there, so there's no per-machine wiring step.

Within the vault, polished memory views are gitignored — they're per-machine derived state, regenerable from source.

### Multi-machine considerations

#### What syncs and how

- **Plugin contents** (`<plugin>/` repos): plugin manager OR direct git
- **Vault content** (drafts, decisions, narratives, journals, **`40-archive/memory/sources/`**): `vault sync` — nightly cron + boundary sync
- **Per-machine state**: settings.json, credentials, transcripts, caches, polished memory views, plus `~/.config/continuity/config.yaml` (each machine sets its own paths)

#### Boundary sync

SessionStart performs `vault sync --pull` before the brief. Stop hook performs an async `vault sync --push` after writing drafts. This closes the cross-machine loop within seconds. Failures degrade gracefully.

#### Sessions are local; distillates are global

JSONL transcripts stay on the producing machine. Drafts, decisions, narrative patches, harvested notes, **and memory source observations** all sync via the vault. Polished memory views are regenerated locally per machine. Stop-hook drafts must be self-contained (the reviewer may be on a different machine).

#### Per-machine MCP availability

`mcp_servers` is project intent; per-machine availability is environmental. Missing servers degrade silently. `/project` surfaces the gap.

#### Per-machine memory config and polished views

`~/.config/continuity/config.yaml` is per-machine. On a fresh machine without it set, the plugin falls back to its default location (`~/.local/share/continuity/memory/`) and emits a one-time warning. The user then configures the override (e.g., pointing at `<vault>/40-archive/memory/`).

Polished views are regenerated locally on each machine from the synced sources. Two machines might have slightly different polished states at any moment (depending on when each last polished), but both can be reconstituted from the same source. Truth lives in source; polished is just rendering.

#### Concurrent activity

Drafts are uniquely named by timestamp+slug — git merges cleanly. Decisions are append-only. Narrative patches go through `.pending/`. Memory source observations are uniquely keyed by ISO datetime + machine tag in their headings — concurrent appends never collide.

#### New-machine setup

Roughly:

1. Install Claude Code (creates default `~/.claude/`)
2. Install plugins (agent-swarm, continuity) via plugin manager — hooks wired automatically via `hooks.json`
3. Configure `~/.config/continuity/config.yaml` to point `memory_dir` at the desired location (e.g., `<vault>/40-archive/memory/`)
4. Recreate `settings.json` from a template (per-machine secrets only)
5. Clone vault: `git clone <vault-remote> <vault-path>`
6. Clone vault-cli, set `VAULT_DIR`
7. Install MCP servers this machine needs

## Implementation Phases

**Phase 0: Plugin scaffolding** *(no behavior change)*

- Create `~/.claude/plugins/continuity/` directory structure
- `git init`, set up its own private remote (private until ready to publish)
- Add to `installed_plugins.json`
- Place this design doc in `<plugin>/.claude/plans/`
- Create `<plugin>/hooks/hooks.json` declaring SessionStart, SessionEnd, and any other hooks the plugin needs (initially empty stubs that don't change behavior)
- (User-level `~/.claude/` repo is not initialized; the prior `git init` from earlier today can be removed)

**Phase 1: Auto-memory takeover** *(behavior-preserving migration)*

- Implement config schema and loader (reads `~/.config/continuity/config.yaml`)
- Implement session-start hook with auto-memory protocol injection
- Migrate existing memory files from `~/.claude/projects/-home-fearsidhe/memory/` to `<vault>/40-archive/memory/sources/` (re-format existing flat entries with a single retrospective `## YYYY-MM-DD — migration` heading as their first observation)
- Generate initial polished views in `<vault>/40-archive/memory/polished/` (gitignored)
- Implement Stop-hook polished-view regeneration (async, end-of-session)
- Edit agent-swarm's `protocol_assembly` to drop the auto-memory section
- Remove agent-swarm's `remember`/`distill`/`ctx`/`develop` skills (or mark deprecated, then remove)
- Verify auto-memory continues to function without behavior change on writes; reads now use polished by default

**Phase 2: Project bootstrap script** *(manual invocation only)*

- Implement `bootstrap.py` with the naming algorithm (remote basename → directory basename)
- `.serena/` and similar markers added to project-detection signals
- Test by manually bootstrapping 1-2 projects to confirm scaffolding shape

**Phase 3: SessionStart project resolution and resume-brief** *(gated by user confirmation prompt)*

- Extend session-start hook to detect project from `cwd`, prompt or brief
- Persist denylist file
- Resume brief queries `mcp_servers` for context
- `/project` surfaces intent-vs-availability gap
- Rename detection (timestamp-based reconciliation, prompt only on ambiguity)
- Run for 1-2 weeks; tune prompt frequency

**Phase 4: PM agent generalization**

- Move `project-manager.md` to plugin
- Parameterize repo list, doc paths, labels, MCP servers via vault frontmatter
- Initialize `<plugin>/data/mcp-capabilities.yaml`
- Narrative-refresh mode iterates over `mcp_servers`
- `/project` skill with first 3 subcommands
- Verify LOGOS still works; bootstrap one other project end-to-end

**Phase 5: Stop hook and `.pending/` queue**

- Stop hook drafts decision notes and narrative patches (async, vault push)
- Drafts include `session_machine` frontmatter; multi-anchor where applicable
- `/project pending` review flow
- `/project pending accept-all` for batch acceptance
- `/project decide` for in-conversation capture
- First-encounter capability-description prompt for new MCP servers

**Phase 6: Recap extensions**

- Status transitions in nightly recap
- Per-project STATUS regeneration
- Drift flags for stale narratives
- Memory captures section pulling from `<memory_dir>/sources/`

**Phase 7: Deep transcript harvest**

- Extract structured per-session notes from JSONL with `session_machine` metadata
- Replace metadata-only harvest
- Backfill historical sessions

Phase 0–1 deliver the migration without behavior change. Phases 2–4 deliver the core ("project lifecycle automation"). Phases 5–7 extend richness.

## Future enhancements and known refinements

The design is settled enough that there aren't real architectural unknowns left. A few items remain as either deferred enhancements or implementation choices to make on first contact:

- **Project rename auto-detection** — handled in Phase 3 via timestamp-based reconciliation; documented as resolved but worth flagging as a behavior to monitor in real use
- **STATUS output location for projects without `docs_repo`** — defaults to `<vault>/10-projects/<Name>/STATUS.md`; LOGOS continues to use its repo-side `docs/` via override. Could standardize all projects to vault-side later if the inconsistency matters
- **Multi-repo project bootstrap edge cases** — two unrelated repos under a shared parent dir would be detected as one project; mitigated by the prompt-with-rename mechanism. No fix needed unless real friction emerges
- **Per-project MCP role overrides** — capabilities are plugin-level; deferred until a real conflict surfaces
- **Continuation seeds for cross-machine session continuity** — Phase 7+ idea; build only if real-usage signal emerges that drafts-to-pending isn't enough
- **Periodic source pruning** — manual user-initiated curation if individual source files grow unwieldy after years of observations; no automatic pruning since memory is meant to preserve

## Out of Scope

- **Real-time collaborator support.** This is single-user infrastructure (per install).
- **Replacing existing tools.** vault-cli, agent-swarm, and Obsidian remain the substrate. This design adds layers; it does not refactor what exists.
- **Cross-project dependency tracking.** Projects can reference each other in narratives, but automated dependency-graph construction is out of scope.
- **Voice/mobile capture.** All capture happens via Claude Code conversations or existing vault-cli surfaces.
- **Syncing session transcripts across machines.** Transcripts stay local; distillates travel.
- **Auto-installing missing MCP servers.** Per-machine environmental decision; surfaced but not enforced.
- **Bundling user memory data with the plugin.** The plugin's repo contains no user-private content — only code, schemas, and defaults. User data lives at user-configured paths.
- **Forcing a specific memory location.** Defaults to XDG-compliant; users override freely.
- **Reconciliation logic in the memory source layer.** Source records observations faithfully; interpretation happens in polished views or the agent's real-time reasoning, never written back to source.
- **Syncing polished memory views across machines.** Polished is per-machine, regenerable from synced source.

## Acceptance

The design is successful if, returning to any tracked project after 4+ weeks of inactivity:

1. SessionStart presents a brief that re-loads the mental model in under 5 minutes of reading
2. Decisions made during recent (pre-pause) sessions are visible without conversation-mining
3. The user does not need to remember any CLI command to receive these benefits
4. The mechanism works identically for at least 2 distinct projects without per-project code
5. The pending-queue review flow supports batch acceptance for vault-local items
6. Cross-machine continuity works at session boundaries — drafts created on one machine are available on others within seconds of the next session start there
7. Auto-memory behavior is unchanged from before the migration on writes — Claude appends new observations to source memory files at the configured path; reads now use polished views by default with source as fallback
8. The plugin codebase contains no user-private data and can be published open-source as-is
9. Memory source files combine across machines via git merge with no information loss; the system performs no reconciliation logic in the memory source layer
10. Polished memory views are regenerable from source on any machine, never sync'd, and provide the agent's primary read interface for memory
11. The journal includes today's memory observations from source as part of the daily recap

The design is **failing** if any of:

- The user has to manually maintain narrative.md to get value from resumption briefs
- New projects require a configuration step beyond answering one prompt
- Pending-queue drafts grow unbounded because the review flow is unpleasant
- Automation produces false positives (silently edits live state, creates spurious projects)
- MCP enrichment becomes a hard dependency such that projects without configured servers degrade noticeably
- Stop-hook drafts reference conversational context that's only present on one machine
- The plugin can't be shared without leaking the user's data
- Auto-memory migration loses any existing entries or changes the agent's append/read behavior
- Memory source layer attempts to reconcile, merge, or interpret observations rather than just record them
- Polished views drift from source without regeneration paths, or are sync'd across machines and conflict
