"""continuity session-end capture — the plugin-side logic the SessionEnd hook
triggers.

Plugins cannot observe session lifecycle on their own; the SessionEnd hook is
the only surface that can detect session end, so it stays as the trigger. What
to *do* at that moment lives here, in the plugin — the hook just calls this and
surfaces the result. For now that is composing the write-on-end capture request
(guidance to record a project-scoped insight via ``record_insight``); this is
the seam that grows to perform richer capture from session signals.
"""

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from vault_provider import VaultProvider  # noqa: E402

_PLACEHOLDER_PROJECT = "<vault 10-projects basename>"
_PLACEHOLDER_NARRATIVE = "10-projects/<project>"


def _project_from_signals(signals: Optional[dict]) -> Optional[str]:
    cwd = (signals or {}).get("cwd")
    if not cwd:
        return None
    return Path(cwd).name or None


def _capture_target(signals: Optional[dict]) -> tuple[str, str]:
    """Resolve session signals to (project name, vault-relative project dir).

    The cwd basename is not the project name. A session runs from wherever the
    work is — ``.../vault-cli/src``, ``.../continuity/plans`` — and the basename
    of those names no project at all. That matters more than it looks: the name
    is handed to ``record_insight``, whose writer does ``mkdir(parents=True)``,
    so an invented name silently creates a duplicate project directory while the
    real narrative it should have updated goes on rotting. Resolving against the
    vault also keeps a session in a sub-project attributed to the project that
    owns it, rather than to a directory nobody has.

    Degradation is deliberate at each step: no cwd, or a cwd naming nothing in
    the vault, yields a placeholder the agent must fill in rather than a
    confidently wrong path. An unreachable vault (unset env, missing directory —
    the hook's environment is not guaranteed to carry either) is different: we
    cannot verify, so the basename hint is kept rather than discarded.
    """
    cwd = (signals or {}).get("cwd")
    try:
        resolved = VaultProvider().resolve_project_from_path(cwd) if cwd else None
    except (ValueError, OSError):
        name = _project_from_signals(signals)
        if name:
            return name, f"10-projects/{name}"
        return _PLACEHOLDER_PROJECT, _PLACEHOLDER_NARRATIVE
    if resolved is None:
        return _PLACEHOLDER_PROJECT, _PLACEHOLDER_NARRATIVE
    return resolved


def _capture_request(project: str, narrative_dir: str, banner: str, lead: str) -> str:
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
        f"  <vault>/{narrative_dir}/narrative.md\n"
        "  • append a dated section describing the as-built state\n"
        "    (newest last — the narrative readers assume append-only)\n"
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
    project, narrative_dir = _capture_target(signals)
    return _capture_request(
        project,
        narrative_dir,
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
    project, narrative_dir = _capture_target(signals)
    return _capture_request(
        project,
        narrative_dir,
        "CONTINUITY WRITE-BEFORE-COMPACT",
        "This session is about to be compacted, so the detail below is about\n"
        "to be summarised away. If it advanced a project, record a continuity\n"
        "insight now rather than waiting for session end.\n",
    )
