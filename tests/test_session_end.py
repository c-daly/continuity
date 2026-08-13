#!/usr/bin/env python3
"""Tests for hooks/session-end.py — continuity's write-on-end reminder.

continuity's own write-on-end mechanism (per CLAUDE.md): a SessionEnd
hook that reminds the agent to record a project-scoped insight before
the session closes, so cross-session narrative survives without relying
on the manual "Task completion protocol" stopgap.
"""

import importlib.util
import io
import json
from pathlib import Path

SESSION_END_PY = Path(__file__).parent.parent / "hooks" / "session-end.py"


def _load_session_end(name="continuity_session_end_mod"):
    spec = importlib.util.spec_from_file_location(name, SESSION_END_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_write_on_end_message_points_at_continuity_record_insight():
    # The reminder must direct the agent at continuity's own record_insight
    # tool (MCP) so the write lands in continuity's substrate, not elsewhere.
    mod = _load_session_end()
    msg = mod.build_write_on_end_message()
    assert "mcp__plugin_continuity_continuity__record_insight" in msg
    assert "record_insight" in msg


def test_main_emits_valid_system_message_json(monkeypatch, capsys):
    # main() must emit a single JSON object carrying the reminder as a
    # systemMessage, and must not crash on empty/absent stdin.
    mod = _load_session_end()
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    mod.main()
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert "systemMessage" in payload
    assert "record_insight" in payload["systemMessage"]


def test_main_tolerates_malformed_stdin(monkeypatch, capsys):
    # A hook that dies on malformed input would break session teardown;
    # main() must degrade to still emitting the reminder.
    mod = _load_session_end()
    monkeypatch.setattr("sys.stdin", io.StringIO("not json{{"))
    mod.main()
    payload = json.loads(capsys.readouterr().out.strip())
    assert "record_insight" in payload["systemMessage"]
