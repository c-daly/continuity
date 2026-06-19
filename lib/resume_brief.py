"""Resume-brief composer — v0 of continuity's surfacing capability.

Reads vault content for a project and composes a session-start brief.
Pure read; no writes. Other read providers (git, gh, ...) will be added
in later phases when concrete need surfaces.

As of constellation v2 T1 (2026-05-16), an optional MemoryReadProvider
is wired in: when memory is available, first-order observations are
surfaced under `## Memory observations` and continuity's interpretation
goes under a separate `## Continuity synthesis` section. When memory is
unavailable, both sections are omitted and the rest of the brief is
unaffected.
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# Sibling imports — this module sits in lib/ alongside the providers
sys.path.insert(0, str(Path(__file__).parent))
from memory_read_provider import MemoryObservation, MemoryReadProvider  # noqa: E402
from vault_provider import VaultProvider  # noqa: E402
from relevance import load_index, rank, record_surfaced  # noqa: E402


_NARRATIVE_LATEST_TRUNCATE = 1500
_NARRATIVE_PREVIOUS_TRUNCATE = 500
_DECISIONS_LOOKBACK_DAYS = 30
_DECISIONS_MAX = 5
_JOURNAL_DAYS_BACK = 3
_MEMORY_MAX_PER_SECTION = 10


def resume_brief(
    project: str,
    vault: Optional[VaultProvider] = None,
    memory: Optional[MemoryReadProvider] = None,
) -> str:
    """Compose a session-start resume brief for `project` from vault + memory.

    Sources:
    - Last 2 H2 sections from `<project>/narrative.md` (latest + previous)
    - Decisions from `<project>/decisions/` in the last 30 days (max 5)
    - Last 3 daily journal entries
    - If a memory provider is available, first-order memory observations
      with subject=`project` (raw entries; capped at 10) plus a short
      continuity-synthesis line summarizing what's there.

    Returns markdown text suitable for injection at session start.
    Length is variable but typically 200-600 words depending on content.
    """
    if vault is None:
        vault = VaultProvider()
    if memory is None:
        memory = MemoryReadProvider()

    canonical_project = vault.resolve_project(project)
    if canonical_project is None:
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

    narrative_sections = vault.get_narrative_sections(canonical_project, last_n=2)
    decisions = vault.get_decisions(
        canonical_project, since=_date_n_days_ago(_DECISIONS_LOOKBACK_DAYS)
    )
    journal = vault.get_journal_entries(days_back=_JOURNAL_DAYS_BACK)

    parts: list[str] = [f"# Resume brief: {canonical_project}", ""]

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

    observations = memory.list(subject=canonical_project)
    if observations:
        ranked = rank(observations, load_index(), date.today())[:_MEMORY_MAX_PER_SECTION]
        record_surfaced([o.name for o in ranked])

        parts.append("## Memory observations")
        for obs in ranked:
            parts.append(f"- **{obs.type}** `{obs.name}` — {obs.description}")
        parts.append("")

        parts.append("## Continuity synthesis")
        parts.append(_synthesize(ranked))
        parts.append("")

    if not (narrative_sections or decisions or observations):
        # Project-scoped content is missing. Journal entries (if any)
        # are vault-wide and were already shown above as general context.
        parts.append(
            "No project-specific content found "
            "(no narrative.md, no decisions/). "
            "Add a narrative entry or decision file to populate this brief."
        )

    return "\n".join(parts).rstrip() + "\n"


def _synthesize(observations: list[MemoryObservation]) -> str:
    """Conservative one-line synthesis over memory observations.

    Counts by type and reports the distribution. Does not invent insight —
    richer synthesis lands in later phases once there's evidence about
    what's actually useful at session start.
    """
    counts: dict[str, int] = {}
    for obs in observations:
        counts[obs.type] = counts.get(obs.type, 0) + 1
    pieces = [f"{n} {t}" for t, n in sorted(counts.items())]
    total = sum(counts.values())
    return (
        f"{total} memory observation{'s' if total != 1 else ''} for this project "
        f"({', '.join(pieces)}). Treat as first-order context; "
        "richer synthesis will arrive in later phases."
    )


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, adding a marker if truncated."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n... (truncated; see source for full)"


def _date_n_days_ago(n: int) -> str:
    """Return YYYY-MM-DD for N days ago."""
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")
