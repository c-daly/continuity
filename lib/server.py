"""continuity MCP server.

Exposes continuity's composer tools via the Model Context Protocol so
Claude Code agents (and other plugins) can call them without shelling out.

Currently exposes:
- resume_brief(project) — session-start orientation brief
- record_insight(project, title, body) — write a project-scoped insight
- synthesize() — run the synthesis pass over recorded observations

Run via the bin/continuity-server wrapper, which sets up the path.
"""

import sys
from pathlib import Path

# Add this dir to path so siblings can be imported
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from record_insight import record_insight as _record_insight  # noqa: E402
from resume_brief import resume_brief as _resume_brief  # noqa: E402
from synthesis_pass import (  # noqa: E402
    default_synthesis_deps as _default_synthesis_deps,
    run_synthesis as _run_synthesis,
)


mcp = FastMCP("continuity")


@mcp.tool()
def resume_brief(project: str) -> str:
    """Compose a session-start resume brief for the given project.

    Reads the project's narrative.md last sections, recent decisions
    (last 30 days), and recent journal entries from the configured
    vault. Returns markdown text suitable for context injection.

    The vault path is resolved from the CONTINUITY_VAULT_DIR or
    VAULT_DIR environment variable.

    Args:
        project: Project name (basename under <vault>/10-projects/)
    """
    return _resume_brief(project)


@mcp.tool()
def record_insight(project: str, title: str, body: str) -> str:
    """Record a project-scoped insight via the configured WriteProvider.

    Composes a frontmatter-tagged markdown file (date, project,
    type=insight, title) and routes it through whichever
    WriteProvider is named in ``~/.config/continuity/config.yaml``
    (default: vault).

    Args:
        project: Project name (basename under <vault>/10-projects/).
        title: Human-readable title; slugified into the filename.
        body: Markdown body content.

    Returns:
        ``"<kind>:<id>"`` reference string for the written artifact.
    """
    return _record_insight(project=project, title=title, body=body)


@mcp.tool()
def synthesize() -> str:
    """Run the synthesis pass: cluster recorded observations into cross-boundary
    concepts, draft promotions, and write the new ones to the vault.

    Existing promotions are read first and passed to the clusterer, so re-running
    converges rather than duplicating. Clusters that do not cross a boundary are
    skipped and named in the result.

    This is the same pass as ``continuity synthesize`` on the CLI. It is exposed
    here because the CLI was previously its only entry point — no hook and no
    tool called it — so the pass shipped but never ran.

    Returns:
        A summary naming what was written and what was skipped.
    """
    res = _run_synthesis(**_default_synthesis_deps())
    written = ", ".join(res.written) or "none"
    skipped = ", ".join(res.skipped) or "none"
    return (
        f"synthesis: {len(res.written)} written, {len(res.skipped)} skipped\n"
        f"  written: {written}\n"
        f"  skipped: {skipped}"
    )


if __name__ == "__main__":
    mcp.run()
