# continuity — project context

## Thesis

Claude Code plugin providing the **second-order synthesis** layer over memory's first-order observations and the vault's narrative content. Addresses the *returning-to-a-project-after-absence* problem (recall is slow; decisions rot) by composing resume briefs from multiple read providers and writing synthesized insights via configurable write providers.

GitHub: `c-daly/continuity`. Two-layer model: append-only sources of record (vault narratives, memory observations) + regenerable composed views (resume briefs, insights). Cross-machine via vault git.

## Current state

- **Phase 0** shipped: vault read provider + resume-brief composer + MCP server + CLI.
- **Phase 1** shipped: `WriteProvider` interface + `VaultWriteProvider` + first generative write end-to-end.
- **T1 (`MemoryReadProvider`)** shipped 2026-05-16. Resume briefs surface first-order memory observations under `## Memory observations` and a synthesis line under `## Continuity synthesis`.
- **T2 (`MemoryWriteProvider`)** shipped 2026-05-16 (opt-in via `~/.config/continuity/config.yaml`).
- **T2 framing clarified** (audit #3, 2026-05-17): the memory write path is opt-in, not the default. See narrative for the exact wording.

See `<vault>/10-projects/continuity/narrative.md` for the dated chronological state.

## Canonical state files (read these for project recovery)

1. `<vault>/10-projects/continuity/Continuity.md` — landing page / hub doc
2. `<vault>/10-projects/continuity/narrative.md` — project narrative (long; tail is current)
3. `<vault>/10-projects/constellation/2026-05-16-implementation-plan-v2.md` — current cross-plugin plan (canonical; supersedes the older per-plugin plans)
4. `<vault>/10-projects/continuity/decisions/`:
   - `2026-05-08-reader-writer-contract.md` — the cross-plugin reader/writer contract memory v1 conforms to
   - `2026-05-08-decisions-as-peer-artifact-type.md`
   - `2026-05-08-pm-owns-project-narratives.md`
   - `2026-05-08-vault-writer-stays-continuity-local.md`
5. `<vault>/10-projects/continuity/design-risks.md` — design risks with recommendations (historical reference)

## Source of truth

- **Vault is source of truth** for plans and decisions: `<vault>/10-projects/continuity/{plans,decisions}/<file>.md`. Edit there directly; no dev-tree mirror.
- The constellation v2 plan is the active cross-plugin doc. Per-plugin plans (continuity's own `plans/` dir, including the 2026-05-03 design v2) are historical references — implementation has moved past their scope.
- The repo's `.claude/` tree is gitignored; old plans in git history are historical snapshots.

## Adjacent plugins

- **`~/.claude/plugins/memory/`** — first-order observation store. continuity reads via `bin/memory list` (subprocess) and writes via `bin/memory write` (when `write_provider: memory` is configured). Memory's audit #6 (entity-locality enforcement) means continuity's writes through memory now raise on unresolved subjects rather than landing in inbox.
- **`~/projects/vault/`** — the Obsidian/PARA vault. Read directly via `lib/vault_provider.py`; write directly via `lib/vault_write_provider.py` when `write_provider: vault` (default).
- **`~/.claude/plugins/agent-swarm/`** — workflow execution. continuity does not call agent-swarm at runtime.

## Task completion protocol

> *The SessionEnd hook (`hooks/session-end.py`) now surfaces a write-on-end
> reminder to `record_insight` at session close. These steps remain the manual
> fallback until the hook also performs the narrative append + vault sync.*

Trigger: when the user signals stopping or before a clean session end.

1. Append a dated entry to `<vault>/10-projects/continuity/narrative.md` summarizing what shipped.
2. **Sync the vault.** `cd <vault> && git add 10-projects/continuity && git commit -m "continuity: <one-line summary>" && git push`. Always provide `-m`.

## Project-specific protocols

- **continuity owns *synthesis*, not first-order observation storage.** First-order memory entries (`user`/`feedback`/`project`/`reference`) belong to the memory plugin. continuity writes second-order artifacts (`cont.insight`, future `cont.pattern`, etc.) — interpretations, syntheses, surfacing.
- **The memory write path is opt-in.** Default is `VaultWriteProvider` (writes to `<vault>/10-projects/<project>/insights/<id>.md` with `type: insight` frontmatter). Set `write_provider: memory` in `~/.config/continuity/config.yaml` to route writes through memory's CLI instead. This matches the v2 plan's explicit non-goal *"Do not make memory the only write path."*
- **Two-layer principle.** Append-only sources of record + regenerable composed views. Polished views are *interpretation*, not truth. If a polished view contradicts a source-of-record entry, the source wins.
- **No agent-swarm runtime dependency.** continuity's MCP and CLI work whether or not agent-swarm is present.
- **Resume brief idempotency.** Same project + same underlying data → same output. The composer doesn't embed wall-clock timestamps; if a section is empty, it's omitted rather than printed with a placeholder.
