"""Tests for continuity's session-end capture (the plugin-side logic the
SessionEnd hook triggers).

The hook detects session end (plugins can't observe lifecycle on their own);
this module owns *what to do* at that moment, so the hook stays a thin trigger.
"""

from session_capture import session_end_capture


def test_message_points_at_record_insight():
    msg = session_end_capture({})
    assert "mcp__plugin_continuity_continuity__record_insight" in msg
    assert "record_insight" in msg


def test_message_names_project_from_cwd_signal():
    msg = session_end_capture(
        {"cwd": "/home/x/projects/vault/10-projects/agent-swarm"})
    assert "agent-swarm" in msg


def test_tolerates_none_signals():
    assert "record_insight" in session_end_capture(None)


def test_tolerates_missing_cwd():
    # No cwd signal -> a placeholder, never a crash.
    assert "record_insight" in session_end_capture({"session_id": "abc"})
