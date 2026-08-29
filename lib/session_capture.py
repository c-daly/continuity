"""continuity session-end capture — the plugin-side logic the SessionEnd hook
triggers.

Plugins cannot observe session lifecycle on their own; the SessionEnd hook is
the only surface that can detect session end, so it stays as the trigger. What
to *do* at that moment lives here, in the plugin — the hook just calls this and
surfaces the result. For now that is composing the write-on-end capture request
(guidance to record a project-scoped insight via ``record_insight``); this is
the seam that grows to perform richer capture from session signals.
"""

from pathlib import Path
from typing import Optional

_PLACEHOLDER_PROJECT = "<vault 10-projects basename>"


def _project_from_signals(signals: Optional[dict]) -> Optional[str]:
    cwd = (signals or {}).get("cwd")
    if not cwd:
        return None
    return Path(cwd).name or None


def _capture_request(project: str, banner: str, lead: str) -> str:
    """Compose a capture request. Shared so every trigger asks for the same
    artifact in the same shape — only the banner and the reason differ."""
    return (
        "\n\n============================================================\n"
        f"\U0001f9ed {banner}\n"
        "============================================================\n"
        f"{lead}"
        "\n"
        "Tool: mcp__plugin_continuity_continuity__record_insight\n"
        "  (or CLI: $CONTINUITY_ROOT/bin/continuity record-insight\n"
        "           --project <p> --title <t>  # body on stdin)\n"
        "\n"
        "What to capture:\n"
        "  • What shipped / advanced this session\n"
        "  • Decisions made and their rationale\n"
        "  • Open threads and the next-session starting point\n"
        "\n"
        "Then update the project's narrative:\n"
        f"  <vault>/10-projects/{project}/narrative.md\n"
        "  • prepend a dated section describing the as-built state\n"
        "  • mark any earlier position this session reversed as superseded\n"
        "  • correct the Open threads list\n"
        "  • bump the `updated:` frontmatter field\n"
        "\n"
        "The narrative is the first thing the next session reads, and no tool\n"
        "writes it — every plugin reads it. Left alone it goes stale silently,\n"
        "which is the drift the vault is supposed to protect against.\n"
        "\n"
        "Example:\n"
        "  record_insight(\n"
        f"      project='{project}',\n"
        "      title='<short human-readable title>',\n"
        "      body='# Session Summary\\n\\n<what shipped / decisions / next>',\n"
        "  )\n"
        "============================================================"
    )


def session_end_capture(signals: Optional[dict] = None) -> str:
    """Compose continuity's session-end capture request from session signals.

    Returns the guidance surfaced to the agent so it records a continuity
    insight before the session closes. ``signals`` may carry ``cwd`` (used to
    name the current project) and ``session_id``; missing signals degrade to a
    placeholder rather than failing.
    """
    return _capture_request(
        _project_from_signals(signals) or _PLACEHOLDER_PROJECT,
        "CONTINUITY WRITE-ON-END",
        "Before ending this session, if it advanced a project, record a\n"
        "continuity insight so the next session can resume from it.\n",
    )


def pre_compact_capture(signals: Optional[dict] = None) -> str:
    """Compose the same capture request, triggered before a compaction.

    SessionEnd alone is a single fragile capture point: a long session compacts
    repeatedly and may never end cleanly, and by the time it does the detail
    worth recording has already been summarised away. Compaction is the moment
    that detail is about to be lost, which makes it the better trigger — and the
    one that actually fires in the sessions that produce the most to record.
    """
    return _capture_request(
        _project_from_signals(signals) or _PLACEHOLDER_PROJECT,
        "CONTINUITY WRITE-BEFORE-COMPACT",
        "This session is about to be compacted, so the detail below is about\n"
        "to be summarised away. If it advanced a project, record a continuity\n"
        "insight now rather than waiting for session end.\n",
    )
