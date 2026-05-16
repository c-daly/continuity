"""Resume-brief composer — v0 of continuity's surfacing capability.

Reads vault content for a project and composes a session-start brief.
Pure read; no writes. Vault content is the canonical source; memory is
an optional first-order observation source when the memory plugin CLI is
available.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Sibling import — this module sits in lib/ alongside vault_provider.py
sys.path.insert(0, str(Path(__file__).parent))
from memory_read_provider import MemoryReadProvider  # noqa: E402
from vault_provider import VaultProvider  # noqa: E402


_NARRATIVE_LATEST_TRUNCATE = 1500
_NARRATIVE_PREVIOUS_TRUNCATE = 500
_DECISIONS_LOOKBACK_DAYS = 30
_DECISIONS_MAX = 5
_JOURNAL_DAYS_BACK = 3


def resume_brief(
    project: str,
    vault: Optional[VaultProvider] = None,
    memory: Optional[MemoryReadProvider] = None,
) -> str:
    """Compose a session-start resume brief for `project` from vault content.

    Sources:
    - Last 2 H2 sections from `<project>/narrative.md` (latest + previous)
    - Decisions from `<project>/decisions/` in the last 30 days (max 5)
    - Last 3 daily journal entries
    - First-order memory observations for `project`, if memory is available

    Returns markdown text suitable for injection at session start.
    Length is variable but typically 200-600 words depending on content.
    """
    if vault is None:
        vault = VaultProvider()
    if memory is None:
        memory = MemoryReadProvider()

    if not vault.project_exists(project):
        available = vault.list_projects()
        if available:
            return (
                f"Project '{project}' not found under {vault.vault_path}/10-projects/.\n"
                f"Available projects: {', '.join(available)}"
            )
        return (
            f"Project '{project}' not found. "
            f"No projects found under {vault.vault_path}/10-projects/."
        )

    narrative_sections = vault.get_narrative_sections(project, last_n=2)
    decisions = vault.get_decisions(
        project, since=_date_n_days_ago(_DECISIONS_LOOKBACK_DAYS)
    )
    journal = vault.get_journal_entries(days_back=_JOURNAL_DAYS_BACK)
    memory_observations = memory.list(subject=project)

    parts: list[str] = [f"# Resume brief: {project}", ""]

    if narrative_sections:
        parts.append("## Most recent narrative")
        latest = narrative_sections[0]
        parts.append(f"### {latest['heading']}")
        parts.append(_truncate(latest["body"], _NARRATIVE_LATEST_TRUNCATE))
        parts.append("")
        if len(narrative_sections) > 1:
            previous = narrative_sections[1]
            parts.append(f"### Previous: {previous['heading']}")
            parts.append(_truncate(previous["body"], _NARRATIVE_PREVIOUS_TRUNCATE))
            parts.append("")

    if decisions:
        parts.append(f"## Recent decisions (last {_DECISIONS_LOOKBACK_DAYS} days)")
        for d in decisions[:_DECISIONS_MAX]:
            parts.append(f"- **{d['date']}** — `{d['slug']}` ({d['path']})")
        parts.append("")

    if journal:
        parts.append(f"## Recent journal entries (last {_JOURNAL_DAYS_BACK} days)")
        for j in journal:
            parts.append(f"- {j['date']} ({j['path']})")
        parts.append("")

    if memory_observations:
        parts.append("## Memory observations")
        for observation in memory_observations:
            parts.append(
                f"- `{observation.type}:{observation.subject}` "
                f"**{observation.name}** — {observation.description}"
            )
        parts.append("")

    if not (narrative_sections or decisions):
        # Project-scoped content is missing. Journal entries (if any)
        # are vault-wide and were already shown above as general context.
        parts.append(
            "No project-specific content found "
            "(no narrative.md, no decisions/). "
            "Add a narrative entry or decision file to populate this brief."
        )

    return "\n".join(parts).rstrip() + "\n"


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, adding a marker if truncated."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n... (truncated; see source for full)"


def _date_n_days_ago(n: int) -> str:
    """Return YYYY-MM-DD for N days ago."""
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")
