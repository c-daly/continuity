---
date: 2026-05-03
status: draft
type: implementation-plan
companion-to: 2026-05-03-continuity-design-v2.md
---

# Continuity — Implementation Plan

Phased build plan for the continuity plugin per design v2 (2026-05-03). Each phase: prerequisites, concrete tasks (with file paths), definition of done (DoD), validation, risks.

## Phase ordering rationale

The original v1 design phased 0–7 with Phase 1 being "auto-memory takeover (behavior-preserving migration)" — but Phase 1 included removing agent-swarm skills (`remember`/`distill`/`ctx`/`develop`), which is *not* behavior-preserving. v2 splits this:

- **Phase 1 (true zero-behavior-change)**: continuity's memory layer added *alongside* agent-swarm's; nothing removed
- **Phase 1.5 (dependency audit + skill-removal preparation)**: enumerate all references to `remember`/`distill`/`ctx`/`develop`; wrap them as deprecated stubs that proxy to continuity equivalents
- **Phase 1.9 (skill removal — actual breaking change)**: only after at least one full agent-swarm release runs cleanly with deprecated stubs; remove the skills definitively

This sequencing prevents the silent-breakage failure mode that was the most likely outcome of v1's combined Phase 1.

## Cross-cutting prerequisites (apply to every phase)

These must be done before Phase 0 so they don't bite later:

### CC1. Plugin cache sync workflow

Skills load from `~/.claude/plugins/cache/<plugin>/<version>/skills/<name>/SKILL.md`, NOT from dev path. Edits to dev don't propagate.

**Task:** write `~/.claude/bin/sync-plugin <plugin>` script:
```bash
#!/bin/bash
PLUGIN="$1"
DEV="$HOME/.claude/plugins/$PLUGIN"
CACHE_BASE="$HOME/.claude/plugins/cache/fearsidhe-plugins/$PLUGIN"
LATEST_VERSION=$(ls "$CACHE_BASE" | sort -V | tail -1)
CACHE="$CACHE_BASE/$LATEST_VERSION"
rsync -av --delete "$DEV/" "$CACHE/"
```

Document in user's CLAUDE.md: "After editing any plugin in dev path, run `sync-plugin <name>` before testing in a new session."

**DoD:** script exists, executable, documented. Successfully syncs continuity dev → cache.

### CC2. gh auth scope refresh (user-interactive)

`nuke-and-recreate.sh` and similar repo-management scripts need `delete_repo` scope. User must run interactively:
```
gh auth refresh -h github.com -s delete_repo
```

**DoD:** `gh auth status | grep delete_repo` returns the scope. **Cannot be done by Claude — must be user.**

### CC3. WSL/Windows mount filesystem testing

If vault on `/mnt/c/...`, atomic writes / file locking semantics differ from native Linux. Test the planned flow on the actual mount before committing to it.

**Task:** test script `test-vault-fs.sh`:
```bash
VAULT="$1"  # e.g. /mnt/c/Users/cddal/Obsidian/vault
cd "$VAULT"
# Test 1: concurrent appends
( for i in {1..20}; do echo "A$i" >> /tmp/test-source.md; done ) &
( for i in {1..20}; do echo "B$i" >> /tmp/test-source.md; done ) &
wait
# Should have 40 lines, no truncation
wc -l /tmp/test-source.md
# Test 2: rename atomicity
echo "v1" > /tmp/test-rename
mv /tmp/test-rename "$VAULT/40-archive/test-rename" || echo "RENAME FAILED"
# Test 3: file locking (flock)
flock /tmp/test-lock -c "echo locked" || echo "FLOCK FAILED"
```

**DoD:** test-vault-fs.sh runs cleanly against the user's actual vault path; any failures inform the staging-then-mv strategy below.

---

## Phase 0 — Plugin scaffolding

**Goal:** create empty plugin structure that doesn't change any behavior.

**Prerequisites:** CC1 (sync script), CC3 (filesystem test passes or fallback documented)

**Tasks:**

1. Create `~/.claude/plugins/continuity/` (already exists — verify structure)
2. Initialize git repo: `cd ~/.claude/plugins/continuity && git init && git remote add origin <user's choice — private until ready>`
3. Add to `~/.claude/installed_plugins.json`
4. Create directory skeleton:
   ```
   continuity/
   ├── .claude/plans/                       (already has design docs)
   ├── README.md                            (new — describe plugin, link to design doc)
   ├── config.example.yaml                  (new — see CC4 below)
   ├── lib/                                 (new, empty)
   │   ├── __init__.py
   │   ├── memory/                          (placeholder — Phase 1)
   │   ├── projects/                        (placeholder — Phase 2-3)
   │   └── sync/                            (placeholder — Phase 1)
   ├── hooks/
   │   ├── hooks.json                       (declares SessionStart, SessionEnd; bodies stub)
   │   └── sessionstart.sh                  (stub: exits 0, no behavior)
   │   └── sessionend.sh                    (stub: exits 0, no behavior)
   ├── data/                                (new)
   │   ├── mcp-capabilities.yaml            (new — see design doc section)
   │   └── no-bootstrap.list                (new — denylist for projects)
   └── bin/                                 (new — CLI tools)
       └── continuity                       (entry point; sub-commands stubbed)
   ```
5. Place design v2 + this implementation plan in `.claude/plans/` (already there)
6. Add `.gitignore`: `.config/`, `*.pyc`, `__pycache__/`

### CC4. Config schema

`config.example.yaml` (default values):
```yaml
memory_dir: ~/.continuity-memory   # safe default OUTSIDE vault for fresh installs
projects_root: ~/.continuity-projects
journal_dir: ~/.continuity-journal
machine_tag: "$(hostname)"
contradiction_policy: latest-wins  # latest-wins | both-surface | llm-arbitrated-always
regenerator_engine:
  template: v1
  llm:
    enabled: true
    model: claude-opus-4-7
    trigger: contradictions-only  # contradictions-only | always | never
sync:
  push_timeout_seconds: 10
  pull_retry_count: 3
  marker_file: .pending-push
```

User overrides at `~/.config/continuity/config.yaml`.

**DoD:**
- `~/.claude/plugins/continuity/` has full directory skeleton
- `installed_plugins.json` includes continuity
- Starting a new claude session shows continuity's hooks loaded but emits no behavior
- `continuity --help` (the CLI stub) prints usage
- Sync script (CC1) successfully syncs continuity to cache; new session sees scaffolded files

**Validation:**
- `find ~/.claude/plugins/continuity -type f` matches expected skeleton
- New session log shows `sessionstart.sh` was invoked but exited 0
- Memory under `~/.continuity-memory` (or wherever config points) is unchanged

**Risks:**
- Adding to `installed_plugins.json` might cause Claude Code to fail-load if hook syntax is wrong. **Mitigation:** test in disposable session before committing.

---

## Phase 1 — Auto-memory takeover (truly behavior-preserving)

**Goal:** continuity's two-layer memory model lives alongside agent-swarm's existing memory, capturing observations into both. **No agent-swarm skills are removed.** No user-visible behavior change.

**Prerequisites:** Phase 0 complete

### Tasks

1. **Implement config loader** at `lib/config.py`. Reads `~/.config/continuity/config.yaml`, falls back to `<plugin>/config.example.yaml`.

2. **Implement source file writer** at `lib/memory/source.py`:
   - `append_observation(topic, body, machine_tag, project=None, protocol_version=1)`
   - Format: H2 heading `## <iso8601 ts> — <machine-tag>[ — project:<name>]`
   - Atomic write via staging + `mv` (per CC3 testing)
   - Creates source file with proper frontmatter if not exists
   - Sets `.gitattributes` `*.md merge=union` on first write to a sources/ dir

3. **Implement protocol_version handling**:
   - Source file frontmatter includes `protocol_version: 1`
   - Reader checks version; if major version mismatch, refuses + logs

4. **Implement project context tagging**:
   - Auto-detect project from cwd (Phase 2's bootstrap.py provides resolution; for Phase 1, just use heuristic: nearest ancestor dir with `.git`)
   - Tag goes into observation heading

5. **Implement polished view regenerator (template engine)** at `lib/memory/regenerate.py`:
   - Template-driven section ordering, recency-N selection
   - Detects contradictions (multiple observations on same predicate); for Phase 1, use `latest-wins` policy only (LLM path deferred to later iteration)
   - Writes provenance header to every polished view
   - Refuses to regenerate views with mismatched protocol_version

6. **Implement Stop hook polished regen** at `hooks/sessionend.sh`:
   - Identifies sources modified during the just-ended session (via mtime comparison vs SessionStart timestamp recorded in `/tmp/continuity-session-<sid>`)
   - Regenerates polished view for each modified source
   - Logs to `<memory_dir>/.regen-log`

7. **Implement SessionStart freshness check** at `hooks/sessionstart.sh`:
   - Records session start timestamp
   - Compares polished `generated_at` vs source max mtime
   - If sources newer (cross-machine sync recently pulled), regenerates stale polished views before next steps
   - Sync status indicator output (per design)

8. **Auto-memory protocol injection (additive)**:
   - Append to system prompt / context: "Continuity memory layer is available. Read `<memory_dir>/polished/<topic>.md` for current state. Polished is interpretation, not truth — drill into `sources/<topic>.md` for trajectory or contradictions. When recording durable observations, append a new section to the appropriate source file."
   - Does NOT replace agent-swarm's existing protocol injection
   - Both can run; agents may see redundancy but no breakage

9. **Implement `continuity memory hash` and `snapshot/restore` CLI commands**:
   - `continuity memory hash` → SHA256 of concatenated source files (deterministic order)
   - `continuity memory snapshot <name>` → git tag in vault: `continuity-snap-<name>-<ts>`
   - `continuity memory restore <name>` → `git checkout <tag> -- <memory_dir>/sources/`
   - These are the *primitives* that benchmarks will use (R1)

10. **Implement `CONTINUITY_MEMORY` env var honor**:
    - SessionStart hook reads `os.environ.get('CONTINUITY_MEMORY', 'on')`
    - `on`: full behavior
    - `read-only`: inject for reads, but write paths short-circuit (no append, no regen)
    - `off`: no protocol injection, no regen, no writes

11. **Migration of existing agent-swarm memory**:
    - Read `~/.claude/projects/-home-fearsidhe--claude-plugins-agent-swarm/memory/*.md`
    - For each existing entry, append to corresponding `<memory_dir>/sources/<topic>.md` with a single retrospective heading: `## YYYY-MM-DD — migration` (date = file's mtime)
    - Generate initial polished views from migrated sources
    - **DO NOT remove agent-swarm's memory files** — leave them in place; agent-swarm continues to read its own memory; continuity ALSO has the data
    - Document: "Phase 1 creates redundancy. Phase 1.9 removes the duplication after dependency audit."

### CC5. .gitattributes setup test

Test the union merge driver works:
```bash
cd /tmp && rm -rf gitattr-test && mkdir gitattr-test && cd gitattr-test
git init; mkdir sources
echo '*.md merge=union' > sources/.gitattributes
git add sources/.gitattributes
echo "## A1" > sources/test.md && git add sources && git commit -m baseline
git branch alt; git checkout alt
echo "## B1 (alt branch)" >> sources/test.md && git commit -am alt
git checkout main
echo "## A2 (main branch)" >> sources/test.md && git commit -am main
git merge alt && cat sources/test.md
# Expected: file contains A1, A2, B1 (or A1, B1, A2) — no conflict markers
```

If this fails: investigate filesystem behavior on the user's `/mnt/c/...` path. Falls back to per-machine staging if needed.

### DoD

- New session shows continuity's protocol injection in addition to agent-swarm's
- Recording an observation creates a new H2 section in `<memory_dir>/sources/<topic>.md` with proper format
- Stop hook regenerates `<memory_dir>/polished/<topic>.md` for any source modified that session
- Polished view starts with valid provenance frontmatter
- `continuity memory hash` returns deterministic SHA256
- `CONTINUITY_MEMORY=off` suppresses all continuity behavior in that session
- All existing agent-swarm memory entries are visible in continuity's source files (migration successful)
- `.gitattributes` merge=union test passes
- WSL/Windows mount filesystem test (CC3) passes

### Validation

- Manually record 3 observations on the same predicate across 2 simulated machines (manual `git checkout` of fake branches); confirm union merge produces all 3 in chronological order
- Run a benchmark capturing memory hash before and after a session; verify hash changes when observations are added
- Smoke-test agent-swarm's existing `/remember` skill still works (not yet removed; should function via existing path)

### Risks

- **Redundancy in protocol injection** could confuse agents (two slightly different memory protocols). **Mitigation:** continuity's injection prefixes itself "(continuity memory layer)" to disambiguate; agent-swarm's existing injection unchanged.
- **WSL/Windows mount atomicity** could corrupt sources on concurrent writes. **Mitigation:** CC3 testing identifies whether staging is needed; if yes, add staging path to lib/memory/source.py before this phase ships.
- **Migration of existing memory might lose nuance** (flat entries → single migration heading). **Mitigation:** preserve original files in agent-swarm's directory until Phase 1.9; recovery is `cp` away.

---

## Phase 1.5 — Dependency audit + skill stub wrapping

**Goal:** identify every reference to agent-swarm's `remember`/`distill`/`ctx`/`develop` skills; replace each skill with a deprecated stub that proxies to continuity equivalents (where applicable) or warns and exits.

**Prerequisites:** Phase 1 deployed and stable for ≥1 week

### Tasks

1. **Run dependency audit:**
   ```bash
   cd ~/.claude
   grep -rn 'agent-swarm:remember\|agent-swarm:distill\|agent-swarm:ctx\|agent-swarm:develop' \
     --include='*.md' --include='*.py' --include='*.sh' --include='*.yaml' \
     plugins/ skills/ docs/ projects/
   grep -rn '\bremember\b\|\bdistill\b\|\bctx\b\|\bdevelop\b' \
     plugins/agent-swarm/skills/ plugins/agent-swarm/lib/ plugins/agent-swarm/config/
   ```
2. **Document every reference** in `<plugin>/docs/dependencies.md` with: file path, line, what it does, replacement plan
3. **For each skill:**
   - Replace `~/.claude/plugins/agent-swarm/skills/<name>/SKILL.md` with a deprecated stub:
     - Frontmatter: `description: "DEPRECATED — proxies to continuity. Will be removed in agent-swarm vX.Y."`
     - Body: redirects agent to use continuity's equivalent (e.g., `continuity memory append <topic>` for `remember`); or, if no equivalent, exits with explanation
4. **Sync stubs to cache** via `sync-plugin agent-swarm`
5. **Smoke-test all skills still respond** (they should redirect, not error)

### DoD

- `<plugin>/docs/dependencies.md` exists, enumerates all references
- Stubbed skills exist at original paths; invoking each prints deprecation notice
- No reference in the codebase invokes the original skill behavior (all are now indirected through continuity)

### Validation

- Manually invoke each deprecated skill in a fresh session; confirm it prints deprecation notice
- Search for new dependencies a week later (drift check)

### Risks

- **Dependencies in muscle memory** (user types `/agent-swarm:remember` reflexively). **Mitigation:** stubs work — the skill responds with "use `continuity memory append` instead, or invoke `continuity memory append <topic>` now to record this observation." Friction, not breakage.

---

## Phase 1.9 — Skill removal (actual breaking change)

**Goal:** definitively remove agent-swarm's `remember`/`distill`/`ctx`/`develop` skills and their underlying code.

**Prerequisites:** Phase 1.5 stubs deployed for ≥2 weeks; no user complaints; dependency audit re-run shows no new references.

### Tasks

1. Delete `~/.claude/plugins/agent-swarm/skills/{remember,distill,ctx,develop}/`
2. Remove related code in `~/.claude/plugins/agent-swarm/lib/protocol_assembly.py` (whatever section currently injects auto-memory)
3. Remove `~/.claude/projects/-home-fearsidhe--claude-plugins-agent-swarm/memory/` (after backing up to `<memory_dir>/sources/migrated-from-agent-swarm-2026-XX-XX/`)
4. Bump agent-swarm version (semantic — this is a breaking change)
5. Update agent-swarm CHANGELOG with the breaking-change notice
6. Sync to cache

### DoD

- Skills truly gone
- No tests fail
- Continuity's memory layer is sole source of memory behavior

### Validation

- Fresh agent-swarm install + fresh continuity install on a clean machine produces working memory behavior end-to-end
- All workflows that previously used agent-swarm memory still work

### Risks

- **Hidden dependencies surface late.** Mitigation: 2-week stub period in 1.5 should catch most; if anything emerges, restore deprecated stub temporarily.

---

## Phase 2 — Project bootstrap script (manual invocation)

**Goal:** `continuity bootstrap [<path>] [<name>]` creates project scaffolding in vault. Manual only — no auto-invocation yet.

**Prerequisites:** Phase 1 complete

### Tasks

1. Implement `lib/projects/bootstrap.py`:
   - Determines project name: explicit arg, else basename of cwd, else basename of git remote
   - Detection signal: `.git`, `.serena/`, `package.json`, `pyproject.toml`, `Cargo.toml`, etc.
   - Creates:
     - `<projects_root>/<Name>/<Name>.md` with frontmatter
     - `<projects_root>/<Name>/narrative.md` (stub with preserve markers)
     - `<projects_root>/<Name>/decisions/`
     - `<projects_root>/<Name>/.pending/`
     - Journal-line append
2. Bootstrap CLI: `continuity bootstrap [path] [--name X]`
3. Smoke-test by bootstrapping 1-2 real projects

### DoD

- Bootstrapping a new project creates all expected vault files
- Idempotent: re-bootstrapping doesn't overwrite

### Validation

- Bootstrap an existing project; verify vault content matches naming algorithm
- Check that `<Name>.md` is queryable via Dataview

---

## Phase 3 — SessionStart project resolution + resume-brief

**Goal:** Headline UX feature. SessionStart resolves the project from cwd, generates a resume-brief, injects it into the session.

**Prerequisites:** Phase 2 complete

### Tasks

1. Implement `lib/projects/resolve.py`: cwd → project name + state lookup
2. Implement first-time prompt: if no project resolved, prompt user to bootstrap or denylist
3. Implement resume-brief generator at `lib/projects/resume_brief.py`:
   - Reads `<Name>.md`, `narrative.md`, recent journal entries, recent commits
   - Optionally enriches via MCP servers (github for PRs, serena for symbol summary) per `mcp-capabilities.yaml` fallbacks
   - Composes 200-400 word brief
4. Inject resume-brief at SessionStart (above auto-memory protocol)
5. Implement project-rename auto-detection (timestamp + dir-mtime correlation)

### DoD

- New session in a known project shows resume-brief
- New session in unknown directory prompts: "Bootstrap as project? (y/n/never)"
- Renaming a project's directory triggers reconciliation, not duplicate creation

### Validation

- 30-day acceptance test: walk away from a project for 30 days; on return, the resume-brief should let user start work without external research

---

## Phase 4 — PM agent generalization

**Goal:** Generalize LOGOS-bound project-manager agent into a per-project STATUS regen capability.

**Prerequisites:** Phase 3 complete

### Tasks

1. Extract project-manager skill from LOGOS to `<plugin>/skills/pm/`
2. Parameterize: project root + state files location read from continuity config
3. STATUS regen respects `<!-- preserve-start -->` markers (per design)
4. Wire to nightly cron for active projects only

### DoD

- Any active project can have STATUS regenerated
- Hand-edited sections survive regeneration
- Dormant/archived projects are skipped

---

## Phase 5 — Stop hook + .pending/ queue (gated on consumer design)

**Goal:** Stop hook drafts decisions/observations to `.pending/`. **Gated:** producer (.pending/ writes) ships only with consumer design defined.

**Prerequisites:** Phase 4; consumer design (how next session reads/acts on .pending/) explicitly drafted

### Tasks

1. Define consumer semantics first:
   - First read consumes? Or read-and-mark-handled?
   - What if multiple machines start sessions concurrently — does each see and act on the same draft?
   - Lock semantics
2. Only after consumer is designed, implement producer (Stop hook .pending/ writes)
3. Implement consumer (SessionStart .pending/ read)

### DoD

- Drafts written by Machine A are seen and processed (not duplicated, not lost) by Machine B
- Concurrency case handled (lockfile or fingerprint-based dedup)

### Risks

- **Producer-without-consumer trap:** ship producer too early and the queue accumulates undelivered drafts. **Mitigation:** literally don't ship producer until consumer is implemented.

---

## Phase 6 — Recap extensions

**Goal:** Daily/weekly recaps include continuity-captured observations.

**Prerequisites:** Phase 5

### Tasks

1. Modify vault-cli's daily recap to include `<memory_dir>/sources/*.md` modified that day
2. Weekly rollup includes per-topic observation diff (week-over-week)

### DoD

- Daily journal entry now includes "memory captures" section
- Weekly rollup shows topic-level evolution

---

## Phase 7 — Deep transcript harvest

**Goal:** Per-session deep harvest with session_machine metadata.

**Prerequisites:** Phase 6

### Tasks

1. Extend `vault harvest --deep` to extract per-session memory observations + correlate with session metadata
2. Cross-machine session traceability via session_machine field

### DoD

- A user looking at any historical session can see what observations were recorded, on which machine, in which project context

---

## Recommended sequencing

**Sprint 1 (week 1):** CC1 (sync script), CC3 (filesystem test), Phase 0
**Sprint 2 (weeks 2-3):** Phase 1 (truly behavior-preserving)
**Sprint 3 (week 4):** Phase 2 + Phase 3 (the user-visible payoff lands)
**Sprint 4 (weeks 5-6):** Phase 1.5 (dependency audit, stubs) — runs in parallel with Phase 4 work
**Sprint 5 (week 7):** Phase 4
**Sprint 6 (week 8):** Phase 1.9 (skill removal — only if 1.5 has been stable for ≥2 weeks)
**Later:** Phases 5–7 as bandwidth permits

**Key principle:** Phase 1 ships truly without behavior change. Phases 2–3 deliver the user-visible value. Then dependency cleanup + Phase 4. Skill removal last.

---

## Test plan

Each phase has its own DoD + validation, but cross-phase integration tests:

1. **30-day absence test** (Phase 3 acceptance): genuine 30 days away → SessionStart brief sufficient to resume work
2. **Cross-machine concurrency test** (Phase 1 + CC5): simultaneous appends from 2 machines via vault git → no data loss, no manual conflicts
3. **Memory-dependent benchmark test** (R1 / capture-as-data): run agent-swarm bench with memory state captured per run; verify run records show memory state hash, allowing analyst to compare runs at same vs different memory states
4. **Schema upgrade test** (R19): write source files with `protocol_version: 1`, then bump to v2 with deliberate breaking change; verify v1-only readers refuse + log; verify migration path
5. **WSL/Windows-mount stress test** (CC3): all phases verified against actual `/mnt/c/...` vault path

---

## Open questions for user before Phase 0

1. **Plugin remote** — public from day one (open-source), or private until ready? Affects git init step in Phase 0.
2. **Memory dir default** — outside vault (safer for fresh installs) or inside vault (closer to real config)? config.example.yaml ships one; user picks the other in their config.yaml.
3. **Sync model** — vault git for everything (current default), or evaluate alternative for memory specifically (e.g., dedicated private repo)? The design accommodates either.
4. **Migration cutoff** — when migrating agent-swarm's existing memory to continuity sources, do we preserve full history (one migration entry per existing line) or collapse (one summary entry per topic)? Affects Phase 1.

These can be answered before starting Phase 0; defaults are picked in config.example.yaml if no answer.

---

## Acknowledgments

This implementation plan is the actionable companion to design v2 (2026-05-03). It incorporates the 19 risks identified in the 2026-05-03 design review (see `<vault>/10-projects/continuity/design-risks.md`) — most prominently:

- **R1/R2** (capture as data, not contamination) → bench tools use `continuity memory hash/snapshot` primitives; no benchmark-aware logic in continuity
- **R3** (bench coupling) → bench writes plain files, continuity reads them
- **R4** (skill removal isn't behavior-preserving) → split into Phase 1, 1.5, 1.9 to prevent silent breakage
- **R5/R6** (regenerator semantics) → hybrid template+LLM with explicit boundary; `latest-wins` default contradiction policy
- **R7** (within-session staleness) → SessionStart freshness check + read-time append-of-recent
- **R8/R13** (cross-machine first-session staleness, regen cadence) → three-trigger regeneration model
- **R9** (git merge driver) → `.gitattributes *.md merge=union` set in Phase 1; tested via CC5
- **R10** (cross-machine context drift) → per-project polished views; observation tagging
- **R11** (provenance headers) → mandatory polished view header with `authoritative: false`
- **R12** (project lifecycle automation destroying hand-edits) → preserve markers respected by all regenerators
- **R14** (vault sync atomicity) → blocking push with retry, marker file, lockfile coordination
- **R15** (WSL/Windows mount semantics) → CC3 test before any Phase implementation; staging fallback if needed
- **R16** (.pending/ consumer first) → Phase 5 explicitly gated on consumer design
- **R17** (preserve markers) → see R12
- **R18** (optional integrations explicit fallbacks) → mcp-capabilities.yaml has `fallback_when_absent` per server
- **R19** (protocol versioning) → `protocol_version: N` in source frontmatter; readers refuse mismatched major version
