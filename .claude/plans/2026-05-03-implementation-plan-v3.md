---
date: 2026-05-03
status: draft
type: implementation-plan
companion-to: 2026-05-03-continuity-design-v3.md
supersedes: 2026-05-03-implementation-plan.md
---

# Continuity v3 — Implementation Plan

Phased build plan for continuity per design v3 (vault-as-memory, lazy-load, recap-mediated promotion). Substantially smaller than v2's plan because the architecture itself is smaller.

## Cross-cutting prerequisites

### CC1. Plugin cache sync workflow (carried from v2 plan)

Skills load from cache, not dev path. Write `~/.claude/bin/sync-plugin <name>` script that copies dev → cache. Document in user CLAUDE.md.

### CC2. WSL/Windows mount filesystem testing (carried from v2 plan)

Vault on `/mnt/c/...` has different filesystem semantics. Test atomic appends, file locking, and rename semantics against the actual vault path before any Phase implementation.

### CC3. Vault `.gitattributes` setup

```
<vault>/.gitattributes:
# Continuity tenant — most prone to concurrent appends
_continuity/**/*.md merge=union

# User/vault-cli tenant — files that may receive concurrent appends
journal/*.md merge=union
10-projects/**/narrative.md merge=union
20-areas/*.md merge=union
```

Resolves concurrent appends across machines without manual conflict. Test with deliberate concurrent-append scenario before relying on it.

### CC4. Config schema

`~/.config/continuity/config.yaml`:
```yaml
vault_root: /mnt/c/Users/cddal/Obsidian/vault
machine_tag: home-laptop

# Continuity tenant (where continuity writes)
continuity_tenant: _continuity
index_path: _continuity/INDEX.md       # relative to vault_root

# User/vault-cli tenants (continuity reads, never writes — except via promotion)
projects_dir: 10-projects
areas_dir: 20-areas
resources_dir: 30-resources
journal_dir: journal
inbox_dir: 00-inbox

# Promotion engine
recap_promotion_engine: llm   # locked in 2026-05-03
recap_promotion_model: claude-opus-4-7

# Cross-machine sync
sync:
  push_timeout_seconds: 10
  pull_retry_count: 3

# Tool exposure
expose_mcp: true              # see Phase 2 notes
```

Defaults shipped in `<plugin>/config.example.yaml`.

---

## Phase 0 — Plugin scaffolding

**Goal:** empty plugin structure, no behavior change.

### Tasks

1. Create directory structure:
   ```
   continuity/
   ├── README.md
   ├── config.example.yaml
   ├── lib/
   │   ├── __init__.py
   │   ├── config.py
   │   ├── capture.py        (Phase 1)
   │   ├── index.py          (Phase 1)
   │   ├── read.py           (Phase 2)
   │   ├── recap.py          (Phase 5)
   │   └── sync.py           (Phase 6)
   ├── hooks/
   │   ├── hooks.json
   │   ├── sessionstart.sh   (stub for Phase 0; populated Phase 3)
   │   └── sessionend.sh     (stub for Phase 0; populated Phase 6)
   ├── bin/
   │   └── continuity        (CLI entry point; subcommands stubbed)
   └── .claude/plans/        (already populated with design + plan)
   ```

2. `git init`, add to `~/.claude/installed_plugins.json`
3. Implement `lib/config.py` (read config.yaml with defaults from config.example.yaml)
4. Stub all CLI subcommands so `continuity --help` lists them

### DoD

- New session shows continuity hook loaded but emits no behavior
- `continuity --help` lists subcommands (capture, index, read, search, recent, backlinks, recap, install)
- `continuity install --check` validates vault paths exist

---

## Phase 1 — Capture tools + index generation

**Goal:** `continuity capture` writes to vault AND updates index atomically. `continuity index` returns current state.

**Prerequisites:** Phase 0; CC2 (filesystem test passes); CC3 (.gitattributes configured)

### Tasks

1. Implement `lib/capture.py` — all targets within continuity tenant (`<vault_root>/_continuity/`):
   - `capture_observation(project, body, tags=None)` → append dated H2 to `_continuity/projects/<project>/observations.md`
   - `capture_decision_draft(project, slug, decision, alternatives, why, stakeholders)` → write `_continuity/projects/<project>/decisions-draft/YYYY-MM-DD-<slug>.md`
   - `capture_general(body, tags=None)` → append to `_continuity/general/observations.md`
   - `capture_inbox(slug, body, tags=None)` → write `_continuity/inbox/YYYY-MM-DD-<slug>.md`
   - All capture functions take `project_context` from cwd auto-detection if not specified
   - **Capture functions REFUSE to write outside continuity tenant.** If asked to write to `10-projects/<Name>/narrative.md` (user-curated), return error pointing user at promotion mechanism instead.

2. Implement `lib/index.py`:
   - `Index` class wrapping `<vault_root>/_continuity/INDEX.md`
   - `upsert_row(path, tags, last_modified, brief)` — adds or updates a row in the appropriate section
   - `regenerate()` — full vault walk (BOTH continuity tenant and user-curated tenants); rebuilds index from scratch
   - `validate_row(path)` — checks if recorded last_modified matches actual mtime; if stale, regenerates that row
   - Sections: Active projects (user-curated, status: active), Areas (user-curated), Resources (user-curated), Recent journal (vault-cli, last 7), Continuity captures (per-project + general + inbox), Other (paused/dormant projects)
   - Section ordering and column schema fixed
   - Each row tags the tenant (user | vault-cli | continuity) so agents reading the index know what they\'re looking at

3. Wire capture functions to upsert index row in same operation:
   - On capture, append to file, then immediately `index.upsert_row(...)`
   - Atomic via staging area + rename (per CC2)

4. CLI subcommands:
   - `continuity capture --kind <observation|decision|general|inbox> [--project X] [--slug X] <body>`
   - `continuity index` — print INDEX.md to stdout
   - `continuity reindex` — full regeneration (walks both continuity tenant AND user-curated areas to populate the unified index)

### DoD

- `continuity capture --kind general "test entry"` appends to `_continuity/general/observations.md` AND adds/updates the row in INDEX.md
- `continuity capture --kind observation --project agent-swarm "test"` writes to `_continuity/projects/agent-swarm/observations.md`
- Attempting `continuity capture --kind narrative --project X` (a v2-era target — user-curated) returns error pointing at promotion mechanism
- `continuity index` returns the index content; index covers BOTH continuity tenant content AND user-curated content (10-projects/, 20-areas/, etc.)
- Manually editing a vault file in Obsidian, then `continuity index` shows the row's last_modified is stale; `continuity reindex` corrects it

### Validation

- Capture 10 observations across different kinds; verify each lands in the right vault location and the index reflects all
- Test concurrent appends from simulated 2-machine scenario: both should land via union merge

---

## Phase 2 — Read tools

**Goal:** Agent can lazy-read vault content via small set of tools.

**Prerequisites:** Phase 1

### Tasks

1. Implement `lib/read.py`:
   - `search(query, paths=None)` — wraps `grep -rIni <query>` over vault, returns list of `{path, line_no, line_text}`
   - `read_file(relative_path)` — reads `<vault_root>/<relative_path>`, returns content
   - `recent(days=7)` — lists files modified in last N days, sorted by mtime descending
   - `backlinks(target_path)` — finds files that reference target via `[[wikilinks]]` (uses Obsidian's standard wikilink syntax)

2. CLI subcommands:
   - `continuity search <query>` — print matches
   - `continuity read <path>` — print file content
   - `continuity recent [--days N]` — list recent
   - `continuity backlinks <path>` — list referrers

3. **Expose as MCP tools — primary agent interface from Phase 2 onward** (per locked-in decision):
   - Implement MCP server at `lib/mcp_server.py` (Python MCP SDK or equivalent)
   - Register in `<plugin>/.mcp.json` so it's discoverable by Claude Code
   - Tool names: `continuity__search`, `continuity__read`, `continuity__recent`, `continuity__backlinks`
   - Schemas: typed parameters (path, query, days, target_path) — no string escaping at agent layer
   - Lifecycle: server starts at SessionStart hook; clean shutdown at SessionEnd
   - CLI remains available for human use (`continuity search ...`); both paths invoke same `lib/read.py` functions

### DoD

- All four tools work via CLI and MCP
- Search returns matches in <1s on a vault of 1000+ files
- Backlinks correctly resolve `[[wikilink]]` and `[[wikilink|alias]]` patterns

---

## Phase 3 — SessionStart minimal protocol + project resolution

**Goal:** Agents know about vault on entry. New projects offered bootstrap.

**Prerequisites:** Phases 1, 2

### Tasks

1. Populate `hooks/sessionstart.sh`:
   - Inject minimal protocol (~6 lines, see design v3)
   - Detect cwd; if it's inside a known project path (per `<projects_dir>/<Name>/<Name>.md` frontmatter), inject project name
   - If cwd is unknown but has `.git`, prompt user once: "Bootstrap as project? (y/n/never)"
   - Record session metadata to `/tmp/continuity-session-<sid>` for SessionEnd correlation

2. Implement `lib/projects.py`:
   - `resolve_project(cwd)` → project name or None
   - `bootstrap_project(path, name=None)` → creates `<projects_dir>/<name>/{Name.md, narrative.md, decisions/}`
   - `denylist(path)` → adds to `<vault>/.continuity-denylist`

3. CLI subcommands:
   - `continuity bootstrap [path] [--name X]`
   - `continuity resolve [path]` — print project name or "unknown"

### DoD

- Fresh session in `~/.claude/plugins/agent-swarm` shows agent has access to `continuity` tools and knows the project context
- Fresh session in `~/projects/random-new-thing` prompts about bootstrap
- Denylisted paths never re-prompt

---

## Phase 4 — Capture-target inference + agent integration

**Goal:** Agents naturally route observations to the right vault location.

**Prerequisites:** Phase 3

### Tasks

1. Update `<plugin>/hooks/sessionstart.sh` to inject capture-target rules into agent context:
   ```
   When recording an observation, capture to continuity tenant:
   - Project state observation → continuity capture --kind observation --project <current>
   - Project decision draft → continuity capture --kind decision --project <current> --slug <slug>
   - Cross-cutting observation → continuity capture --kind general
   - Doesn\'t fit anywhere → continuity capture --kind inbox --slug <slug>

   NEVER write directly to user-curated locations (10-projects/<Name>/narrative.md,
   10-projects/<Name>/decisions/, 20-areas/, 30-resources/, journal/). Those receive
   continuity content only via the explicit promotion mechanism (recap-mediated, with
   user approval).
   ```

2. Optionally implement `lib/inference.py` for automated target suggestion:
   - `suggest_target(body, project_context)` → returns `{kind, ...}`
   - Heuristic: keyword matching first; LLM call as fallback if `recap_promotion_engine: llm`

3. Document the priority order and rule set in continuity README

4. **Extend MCP server to expose capture tools** (in addition to read tools from Phase 2):
   - `continuity__capture` (kind, project?, slug?, body, tags?) — single tool with kind discriminator, or
   - `continuity__capture_observation`, `continuity__capture_decision`, `continuity__capture_general`, `continuity__capture_inbox` — kind-specific tools with specific schemas
   - Recommendation: kind-specific tools — clearer schemas, better discoverability, less ambiguity at agent's tool selection step
   - Each capture tool returns the resulting file path + index update confirmation

### DoD

- In a session where the agent records an observation about agent-swarm bench infrastructure, the observation goes to `10-projects/agent-swarm/narrative.md` automatically
- Observations the agent isn't sure about land in inbox with a `[needs-sorting]` tag

---

## Phase 5 — Recap extension: promotion candidates

**Goal:** Daily recap surfaces candidates for promotion to higher-scope locations.

**Prerequisites:** Phase 4; vault-cli's existing recap infrastructure

### Tasks

1. Implement `lib/recap.py`:
   - `gather_recent_captures(days=1)` → all observations recorded in the last day across narrative/decision/journal/inbox/area
   - `detect_promotion_candidates(captures)` → LLM-driven by default (calls Claude with prompt: "Which of these look like cross-cutting principles, methodology insights, or reference facts vs project-specific?")
   - `suggest_target(observation)` → returns suggested higher-scope path
   - `propose_promotion(observation, target)` → renders the suggestion in markdown for user approval

2. Extend vault-cli's daily recap to include "Promotion candidates" section. Two candidate types surfaced:
   - **Cross-tenant elevation** (continuity-generated → user-curated): requires user approval
   - **Within-tenant generalization** (project observation → general observation): can auto-execute or user-approved per config

3. Implement `lib/promote.py`:
   - `execute_promotion(source_path, source_section, target_path, type)`:
     - Read source section content
     - Synthesize/restate at target scope (LLM call — **engine locked in as LLM, model from config**)
     - Append synthesized form to target_path with `<!-- promoted-from: <source_path>#<heading> -->` comment
     - Add `<!-- promoted-to: <target_path> -->` comment to source location
     - Update INDEX entries for both files
   - `demote(source_path, source_section)` → reverses (rare, but supported)
   - **Cross-tenant elevations only execute on explicit user approval.** Within-tenant generalizations may auto-execute when `recap_within_tenant_auto: true` (config; default false).

4. CLI: `continuity promote <source> --target <target>` for manual promotion outside the recap flow

### DoD

- Daily recap output includes "Promotion candidates" section when candidates detected
- Approved promotion creates higher-scope entry with bidirectional links
- Original location is never destructively modified
- Promoted-from / promoted-to comments visible in both files

### Risks

- **LLM cost** for daily recap with promotion detection (engine locked in as LLM per design v3 update). Mitigation: only LLM-process candidates that pass an initial heuristic filter (e.g., observations with body length > N chars, observations matching general-sounding phrases). Single LLM call per recap that batches all candidates rather than one per candidate.
- **False-positive promotions** (suggesting things that shouldn't be elevated to user-curated content). Mitigation: cross-tenant elevations require explicit user approval; nothing crosses the tenant boundary without explicit yes. Within-tenant generalization is lower-stakes and can auto-execute if user opts in.

---

## Phase 6 — Cross-machine vault sync hardening

**Goal:** Reliable cross-machine operation; no silent data loss.

**Prerequisites:** Phase 5

### Tasks

1. Implement `lib/sync.py`:
   - `pull(retry=3)` — `git pull --rebase` with retry on conflict
   - `push(blocking_seconds=10)` — push with timeout; if exceeds, write marker file
   - `sync_status()` → returns `{up_to_date, pending_push, conflicts}`

2. Wire into hooks:
   - `sessionstart.sh`: `sync.pull()` + check marker file from previous session; if present, retry push
   - `sessionend.sh`: `sync.push(blocking_seconds=10)`

3. Display sync status in SessionStart output:
   ```
   memory sync: ✓ up to date
   ```
   or
   ```
   memory sync: ⚠ pending push from previous session, retrying...
   ```

4. CLI: `continuity sync [--push-only|--pull-only]`

### DoD

- Concurrent sessions on 2 machines don't lose observations (verified by stress test)
- Lost-network scenario writes marker file; next session retries successfully
- Sync status visible to user

---

## Phase 7 — Expose PM capabilities; subsume LOGOS project-manager

**Goal:** Continuity exposes its project-management capabilities (tools, and optionally agent definitions where useful) for both the user's main Claude session and other plugins to invoke. LOGOS's project-manager role is subsumed by continuity's existing processes + any agent definitions added here.

**Note:** clarified by user across multiple turns 2026-05-03 — continuity is project management infrastructure (creates projects, owns lifecycle, captures observations, regenerates status, etc.). PM is not a separate concern from continuity; it's what continuity does. This Phase formalizes the user-facing PM surface and retires LOGOS's local agent.

### Tasks

1. **Audit which PM operations need agent personas vs are well-served by tools alone.** By Phase 7, continuity has shipped: capture, index, search, read, recent, backlinks, bootstrap, status regen, promotion detection, recap. The question is which (if any) PM operations benefit from a dedicated agent persona vs being naturally handled by the user's main Claude session using continuity's tools with appropriate prompting.

2. **For operations that benefit from a persona, add agent definitions:**
   - Likely candidates: triage of inbox items (judgment-heavy interaction), pipeline shepherding (assessing readiness across many factors), draft synthesis from accumulated observations (judgmental writing)
   - Less-likely: STATUS regen (process), search (process), capture (process)
   - Each agent gets a `<plugin>/agents/<name>.md` definition with the standard frontmatter (name, tools, description, model, max_output_chars, can_write_files)

3. **Expose all PM operations via MCP tools** so agent-swarm workflows and other consumers can invoke them:
   - `continuity__pm_status`, `continuity__pm_capture_idea`, `continuity__pm_triage`, etc.
   - These call into the existing process layer; some may also dispatch the agent personas from step 2 internally for judgment-heavy ops

4. **agent-swarm workflows that reference `pm` get rewritten** to call the appropriate continuity tools/agents rather than dispatch a non-existent `pm` agent. develop, teams-develop, experiment all need this fix.

5. **LOGOS project-manager retirement:**
   - Once continuity's PM surface is stable, LOGOS's `~/projects/LOGOS/.claude/agents/project-manager.md` is either retired or becomes a thin LOGOS-specific specialization
   - Coordinate with LOGOS work; document the migration path

### Subordinate plugin extraction — decision point at this Phase, not preemptive

If by this Phase the agentic capabilities have grown rich enough to justify their own lifecycle, optionality, or distinct user journey, **then** consider extracting them into a subordinate plugin (declared dependent on continuity; can't load without it). Likely indicators:
- The agentic layer has substantially different release cadence than the process layer
- Some users want continuity's processes without the opinionated agentic shepherding
- The agentic capability has grown enough to warrant separate testing/documentation effort

**Default if no clear signal:** keep everything in continuity. Subordinate plugin extraction adds coordination cost; only earn it when there's a real reason. The user's stated concern (2026-05-03): premature separation creates more problems than it solves.

### DoD

- PM operations with persona benefit have agent definitions in `<plugin>/agents/`
- All PM operations are MCP-exposed for cross-consumer invocation
- agent-swarm workflows referencing `pm` are updated to use continuity's tools/agents
- LOGOS's project-manager.md retired or thin shadow
- The pm-agent-missing finding in agent-swarm/open-recommendations.md is closed
- Subordinate plugin extraction decision recorded (with rationale either way)

### Risks

- **Cross-plugin agent resolution** if any persona ends up being defined: standard MCP tool invocation handles the cross-plugin case for tools; if continuity defines an agent that agent-swarm wants to dispatch by name, that's the cross-plugin case Claude Code may not handle natively. Mitigation: prefer tools over agents where the operation can be done as a tool; only define agents where the persona genuinely matters; investigate Claude Code's agent resolution before relying on it.
- **Scope drift toward overlapping responsibility.** continuity providing PM personas for all the things could grow without bound. Discipline: each persona has a well-defined operation; if there's significant overlap with another persona, consolidate.

---

## Sequencing

**Sprint 1:** CC1, CC2, CC3, CC4 + Phase 0
**Sprint 2:** Phase 1 (capture + index)
**Sprint 3:** Phase 2 + Phase 3 (read tools + SessionStart)
**Sprint 4:** Phase 4 (agent integration)
**Sprint 5:** Phase 5 (promotion via recap)
**Sprint 6:** Phase 6 (cross-machine hardening)
**Sprint 7:** Phase 7 (PM surface + LOGOS subsumption; subordinate plugin extraction decided at this point if needed)

Total: ~6 sprints (vs v2's ~8). Less surface area; less complexity per phase.

## Test plan

Per-phase DoD covers most. Integration tests:

1. **30-day absence test:** genuine 30 days; SessionStart brief should suffice
2. **Cross-machine concurrency test:** simultaneous appends on 2 machines via vault git → no data loss, no manual conflict
3. **Promotion lifecycle test:** observation captured locally → recap proposes promotion → user approves → both files have correct bidirectional links → search finds the observation via either file
4. **Index drift test:** edit vault files manually in Obsidian → next agent session validates and corrects affected rows

## Open questions / decisions log

| # | Question | Decision (2026-05-03) | Rationale |
|---|---|---|---|
| 1 | Index location | `<vault>/_continuity/INDEX.md` (continuity tenant) | Falls out of tenant model — continuity-generated lives under continuity |
| 2 | Promotion engine | LLM (model from config; default claude-opus-4-7) | User-decided 2026-05-03. Rule-based was alternative; LLM picked for richer detection |
| 3 | MCP tool exposure | **MCP from Phase 2** | User-decided 2026-05-03. Aligns with rest of MCP-heavy infrastructure (router, serena, github). CLI remains available for human use. |
| 4 | Migration from agent-swarm `MEMORY.md` | Keep as historical record; switch capture target to continuity tenant in Phase 4 | No data loss; non-destructive switch-over |

### MCP vs CLI distinction (for question 3)

**CLI exposure** means continuity is invoked as `bash /path/to/continuity capture --kind ...` — agents reach it via the Bash tool. Each invocation spawns a shell process. Inputs are command-line strings (escaping concerns for body content with quotes/newlines). Output goes to stdout. Permissions/hooks treat it like any other shell command. Implementation surface is minimal — just a Python script.

**MCP exposure** means continuity runs as an MCP server (like `mcp__router__*`, `mcp__plugin_serena__*`, etc.) and agents invoke it as `continuity__capture(kind="observation", project="agent-swarm", body="...")` — a structured tool call, not a shell command. Inputs are typed parameters (no string escaping). Lower per-call overhead (no shell process spawn). Visible in transcripts as a tool call rather than a Bash command. Implementation surface is larger — needs MCP server boilerplate, schema definitions, and lifecycle management.

**Practical comparison:**

| | CLI | MCP |
|---|---|---|
| Implementation effort | small (~50 lines of script) | moderate (~300+ lines for MCP server + schema) |
| Per-call latency | ~100ms (shell startup) | ~10ms (in-process) |
| Argument structure | strings (escape body for shell) | typed (body passed as native string) |
| Discoverability | `continuity --help` | listed in agent's tool catalog |
| Permission model | goes through Bash tool's permission/hook chain | goes through router's permission model |
| Frequency tolerance | acceptable for ~10 calls/session | acceptable for any frequency |
| Transcript visibility | Bash command lines | tool calls (cleaner) |

**Recommendation:** MCP from the start (Phase 2 onward) given the rest of your infrastructure is heavily MCP-based (router, serena, github, etc.). Agent-native invocation matches the patterns agents are already using. CLI remains available for human use (you running `continuity index` to inspect things) but agents prefer MCP. The implementation cost is real but pays back in cleaner agent integration.

If you want to defer the MCP server work, CLI-only is fine for Phase 2 — agents can use Bash to invoke. Re-add MCP exposure later. The capture/read API is the same shape either way.

## Acknowledgments

This plan supersedes the v2 implementation plan. The v2 phases for polished view regeneration, contradiction reconciliation, and within-session staleness mitigation evaporate under the lazy-read model. v2's risks R5-R13 mostly become non-issues. The plan is roughly 1/3 the surface area of v2.
