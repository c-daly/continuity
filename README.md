# continuity

Cross-project surfacing and second-order synthesis for Claude Code.

continuity composes information from providers (vault, memory, git, ...) to answer "what's the state of project X?" and proactively surface what's likely to be needed (resume briefs, recent decisions, second-order insights). It's the synthesis layer over memory's first-order observations and the vault's narrative content.

## Status

Phase 0, Phase 1, T1 (`MemoryReadProvider`), and T2 (`MemoryWriteProvider`) shipped. Resume briefs include memory-observation sections; `record-insight` can write `cont.insight` artifacts through memory when configured (opt-in).

See `<vault>/10-projects/continuity/narrative.md` for the dated chronological state and the constellation v2 plan (`<vault>/10-projects/constellation/2026-05-16-implementation-plan-v2.md`) for the cross-plugin execution context.

## Architecture

continuity is one plugin in a constellation. Per the v2 operating model:

| Plugin | Owns |
|---|---|
| memory | first-order durable observations; memory read/write/index policy |
| **continuity** | **second-order synthesis over memory and other providers; resume briefs; surfacing; patterns** |
| pm | project/task lifecycle |
| experiment | run/eval records, scorecards |
| Comhairle | role/model composition |
| agent-swarm | workflow execution |
| vault-cli | terminal capture, harvest, recap |

continuity is the *synthesis* layer. Memory holds first-order observations (`user`/`feedback`/`project`/`reference`). continuity composes, surfaces, interprets, and detects patterns across them. The distinction matters: continuity *writes synthesized artifacts* (insights, briefs), not raw observations.

## Surface

**CLI** (via `bin/continuity`):

```
continuity resume-brief <project>             # session-start orientation brief for <project>
continuity record-insight --project P --title T   # write a project-scoped insight (body from stdin)
```

**MCP** (via `bin/continuity-server`, FastMCP):

- `resume_brief(project)` — composes narrative (last 2 H2 sections), decisions (30d), journal entries (3d), memory observations + a `## Continuity synthesis` count line
- `record_insight(project, title, body)` — writes a `cont.insight` artifact via the configured `WriteProvider`

## Configuration

Vault path: `$CONTINUITY_VAULT_DIR` or `$VAULT_DIR` (resume-brief subprocesses also bridge to `$MEMORY_VAULT_DIR`).

Write provider (for `record-insight`): `~/.config/continuity/config.yaml`:

```yaml
write_provider: vault     # default — writes <vault>/10-projects/<project>/insights/<id>.md
# OR
write_provider: memory    # opt-in — writes via memory's bin/memory write (subject = project)
```

The memory write path is **opt-in by design** (per the constellation v2 plan's non-goal: "Do not make memory the only write path"). Vault-direct writes produce `type: insight` files visible to vault search but not indexed in memory's `MEMORY.md`. Memory writes produce `type: project` entries (with `cont.insight` provenance in the body) that *are* indexed.

## Read providers

- **`VaultProvider`** (`lib/vault_provider.py`) — reads PARA layout, narratives, decisions, journal
- **`MemoryReadProvider`** (`lib/memory_read_provider.py`) — calls `bin/memory list` from the local memory plugin install; degrades gracefully if memory is unavailable

## Write providers

- **`VaultWriteProvider`** (`lib/vault_write_provider.py`) — writes directly to PARA paths under `<vault>/10-projects/<project>/insights/`; the v1 default
- **`MemoryWriteProvider`** (`lib/memory_write_provider.py`) — bridges through `bin/memory write` with deterministic id-as-name mapping; opt-in via config

## Runtime dependencies

continuity's MCP server uses the [mcp](https://pypi.org/project/mcp/) Python package (FastMCP). Installed into a plugin-local `.venv/`.

### First-run setup

If `uv` is on `PATH`, `bin/continuity-server` auto-bootstraps `.venv`. Otherwise:

```
cd ~/.claude/plugins/continuity
python3 -m venv .venv
.venv/bin/pip install mcp 'pyyaml>=6.0'
```

The CLI (`bin/continuity ...`) and MCP server share the same venv.

## Layout

```
.claude-plugin/plugin.json   # Claude Code plugin manifest
.mcp.json                    # MCP server registration (uses ${CONTINUITY_ROOT})
hooks/hooks.json             # Claude Code hook registration (SessionEnd)
hooks/session-end.py         # write-on-end reminder to record_insight
bin/continuity               # CLI wrapper
bin/continuity-server        # MCP server wrapper
lib/cli.py                   # CLI subcommands
lib/server.py                # MCP server (FastMCP)
lib/resume_brief.py          # resume-brief composer (vault + memory)
lib/record_insight.py        # insight write workflow
lib/session_capture.py       # session-end capture logic (called by the hook)
lib/vault_provider.py        # vault read provider (PARA)
lib/vault_write_provider.py  # vault direct write provider (default)
lib/memory_read_provider.py  # memory CLI-backed read provider (T1)
lib/memory_write_provider.py # memory CLI-backed write provider (T2; opt-in)
lib/write_provider.py        # WriteProvider ABC
lib/config.py                # config resolution + provider selection
tests/                       # pytest (~106 tests)
```

Plans and decisions live in `<vault>/10-projects/continuity/`.
