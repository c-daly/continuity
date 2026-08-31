"""Compose and route an insight record through the configured WriteProvider.

An insight is a small generative artifact: a dated, project-scoped
markdown file with a title and freeform body. This module is the
shared core for the CLI subcommand and the MCP tool.
"""

import re
import sys
from datetime import date as _date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from config import get_write_provider  # noqa: E402
from vault_write_provider import validate_relpath  # noqa: E402
from write_provider import WriteProvider  # noqa: E402


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(title: str) -> str:
    s = _SLUG_RE.sub("-", title.lower()).strip("-")
    if not s:
        raise ValueError(f"Title {title!r} produces empty slug")
    return s


def record_insight(
    project: str,
    title: str,
    body: str,
    provider: Optional[WriteProvider] = None,
    today: Optional[_date] = None,
) -> str:
    """Write an insight artifact and return its kind:id reference.

    Args:
        project: Project name, or vault-relative path for a nested
            sub-project (``LOGOS/apollo``). Resolved via project_registry.
        title: Human-readable title; slugified into the id.
        body: Markdown body; written verbatim under the frontmatter.
        provider: Optional WriteProvider; defaults to configured selection.
        today: Optional date override (testing).

    Returns:
        ``"<kind>:<id>"`` reference string, e.g.
        ``"cont.insight:2026-05-09-some-slug"``.
    """
    # project flows to filesystem path construction in VaultWriteProvider;
    # validate up front for a clearer error than the writer-layer rejection.
    # Segment-wise, because a project may be nested (``LOGOS/apollo``).
    validate_relpath(project, "project name")
    if not title.strip():
        raise ValueError("title is required")
    if not body.strip():
        raise ValueError("body is required")

    when = today or _date.today()
    insight_id = f"{when.isoformat()}-{_slug(title)}"
    frontmatter = {
        "date": when.isoformat(),
        "project": project,
        "type": "insight",
        "title": title,
    }

    wp = provider if provider is not None else get_write_provider()
    wp.write("cont.insight", insight_id, frontmatter, body)
    return f"cont.insight:{insight_id}"
