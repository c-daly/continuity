"""continuity MCP server.

Exposes continuity's composer tools via the Model Context Protocol so
Claude Code agents (and other plugins) can call them without shelling out.

Currently exposes:
- resume_brief(project) — session-start orientation brief
- record_insight(project, title, body) — write a project-scoped insight

Run via the bin/continuity-server wrapper, which sets up the path.
"""

import sys
from pathlib import Path

# Add this dir to path so siblings can be imported
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from record_insight import record_insight as _record_insight  # noqa: E402
from resume_brief import resume_brief as _resume_brief  # noqa: E402


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


if __name__ == "__main__":
    mcp.run()
