# continuity — project context

## Thesis

Claude Code plugin (in design phase only — no code yet) that addresses the *returning-to-a-project-after-absence* problem across all of the user's projects. Two failure modes targeted: (1) recall is slow — re-loading mental model takes hours; (2) decisions rot — *why* and alternatives fade. Two-layer memory model: append-only sources (truth-of-record) + regenerable polished views (interpretation). Cross-machine via vault git. Plugin code is shareable; data is user-configurable.

## Canonical state files (read these for project recovery)

1. `<vault>/10-projects/continuity/Continuity.md` — landing page (project frontmatter, what-it-does, phase table)
2. `<vault>/10-projects/continuity/narrative.md` — project narrative
3. `<vault>/10-projects/continuity/design-risks.md` — 19 design risks with recommendations (R1/R2 revised after extended discussion)
4. `<vault>/10-projects/continuity/plans/2026-05-03-continuity-design-v2.md` — current design (supersedes v1)
5. `<vault>/10-projects/continuity/plans/2026-05-03-implementation-plan.md` — phased build plan

## Source of truth vs vault snapshots

- **Source of truth**: `~/.claude/plugins/continuity/.claude/plans/<file>.md` (where edits happen)
- **Vault snapshots**: `<vault>/10-projects/continuity/plans/<file>.md` (mirror with snapshot-warning header)
- **Sync is manual** until continuity itself is built. After editing source-of-truth, re-copy to vault and prepend the snapshot-warning header. The snapshot files have it as their first ~5 lines.

## Memory topics (use these in observation captures)

- `continuity-design` — design decisions, conceptual reframes, trade-off resolutions
- `continuity-architecture` — two-layer model, polished view semantics, cross-machine
- `continuity-implementation` — phase progress, blocker discovery
- `polished-view-regenerator` — engine choice, contradiction policy, cadence triggers

## Project-specific protocols

- **No code yet — design phase only.** Don't begin implementation without first answering the 4 open questions in `2026-05-03-implementation-plan.md` (plugin remote, memory dir default, sync model, migration cutoff).
- **Five cross-cutting prerequisites (CC1-CC5)** must be done before Phase 0:
  - CC1: write `sync-plugin <name>` script
  - CC2: `gh auth refresh -h github.com -s delete_repo` (user-interactive)
  - CC3: WSL/Windows mount filesystem test against actual `/mnt/c/...` path
  - CC4: config schema (`config.example.yaml`)
  - CC5: `.gitattributes *.md merge=union` test for cross-machine append safety
- **Phase 1 is truly behavior-preserving** in v2 — DO NOT remove agent-swarm's `remember`/`distill`/`ctx`/`develop` skills in Phase 1. Skill removal is deferred to Phase 1.5 (audit + deprecated stubs) and Phase 1.9 (actual removal after stub stability period).
- **Memory injection is not contamination** — corrected stance from extended design review. Capture conditions per use; don't suppress. Bench writes plain files; continuity reads them. See R1/R2 in `design-risks.md` for the corrected framing.
- **Polished views are interpretation, not truth.** Mandatory provenance header (`authoritative: false`) on every polished view; explicit escape hatch to source files; readers refuse to interpret views missing the header.
