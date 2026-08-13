#!/usr/bin/env python3
"""Tests for hooks/session-end.py — continuity's write-on-end trigger.

The hook is a thin trigger: it reads session signals and delegates to
lib/session_capture.session_end_capture. These tests assert the delegation and
robustness; the message contents themselves are covered in test_session_capture.
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


def test_hook_delegates_to_session_end_capture(monkeypatch, capsys):
    mod = _load_session_end()
    signals = {"cwd": "/home/x/projects/vault/10-projects/agent-swarm"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(signals)))
    mod.main()
    payload = json.loads(capsys.readouterr().out.strip())
    assert "systemMessage" in payload
    # capture logic ran (record_insight guidance) and the cwd signal flowed through
    assert "record_insight" in payload["systemMessage"]
    assert "agent-swarm" in payload["systemMessage"]


def test_hook_tolerates_malformed_stdin(monkeypatch, capsys):
    mod = _load_session_end()
    monkeypatch.setattr("sys.stdin", io.StringIO("not json{{"))
    mod.main()
    payload = json.loads(capsys.readouterr().out.strip())
    assert "record_insight" in payload["systemMessage"]


def test_hook_tolerates_non_dict_stdin(monkeypatch, capsys):
    mod = _load_session_end()
    monkeypatch.setattr("sys.stdin", io.StringIO("[1, 2, 3]"))
    mod.main()
    payload = json.loads(capsys.readouterr().out.strip())
    assert "record_insight" in payload["systemMessage"]
