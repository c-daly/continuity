#!/usr/bin/env python3
"""Session End Hook — continuity write-on-end reminder.

continuity's own write-on-end mechanism. At session end this emits a
prominent reminder that the agent should record a project-scoped
continuity insight capturing what advanced this session, so the next
session can resume from it.

This is the hook the CLAUDE.md "Task completion protocol" flags as the
thing that supersedes the manual stopgap: instead of relying on the
agent remembering to append a narrative entry, the SessionEnd hook
prompts for a ``record_insight`` write before the session closes.

Claude Code discovers this via ``hooks/hooks.json`` and runs it with the
session payload on stdin. The reminder is surfaced through the
``systemMessage`` field of the emitted JSON.
"""

import json
import sys


def build_write_on_end_message() -> str:
    """Return the end-of-session reminder to record a continuity insight."""
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
        "      project='<vault 10-projects basename>',\n"
        "      title='<short human-readable title>',\n"
        "      body='# Session Summary\\n\\n<what shipped / decisions / next>',\n"
        "  )\n"
        "============================================================"
    )


def main() -> None:
    """Read the session payload (if any) and emit the write-on-end reminder.

    The payload is not currently required, but is consumed so the hook
    degrades gracefully on empty or malformed stdin rather than breaking
    session teardown.
    """
    try:
        json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        pass

    print(json.dumps({"systemMessage": build_write_on_end_message()}))


if __name__ == "__main__":
    main()
