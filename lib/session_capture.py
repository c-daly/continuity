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


def session_end_capture(signals: Optional[dict] = None) -> str:
    """Compose continuity's session-end capture request from session signals.

    Returns the guidance surfaced to the agent so it records a continuity
    insight before the session closes. ``signals`` may carry ``cwd`` (used to
    name the current project) and ``session_id``; missing signals degrade to a
    placeholder rather than failing.
    """
    project = _project_from_signals(signals) or _PLACEHOLDER_PROJECT
    return (
        "\n\n============================================================\n"
        "\U0001f9ed CONTINUITY WRITE-ON-END\n"
        "============================================================\n"
        "Before ending this session, if it advanced a project, record a\n"
        "continuity insight so the next session can resume from it.\n"
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
        "Example:\n"
        "  record_insight(\n"
        f"      project='{project}',\n"
        "      title='<short human-readable title>',\n"
        "      body='# Session Summary\\n\\n<what shipped / decisions / next>',\n"
        "  )\n"
        "============================================================"
    )
