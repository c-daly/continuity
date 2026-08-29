"""Capture triggers.

SessionEnd was continuity's only capture point, which is why nothing had been
recorded since 2026-06-11: a long session compacts repeatedly and may never end
cleanly, and once it has compacted the detail worth recording is gone. These
tests pin both triggers and the fact that they ask for the same artifact.
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from session_capture import pre_compact_capture, session_end_capture

HOOKS = Path(__file__).resolve().parent.parent / "hooks"


def test_pre_compact_names_its_own_trigger():
    out = pre_compact_capture({"cwd": "/home/x/projects/vault-cli"})
    assert "WRITE-BEFORE-COMPACT" in out
    assert "compacted" in out


def test_session_end_still_names_its_own_trigger():
    out = session_end_capture({"cwd": "/home/x/projects/vault-cli"})
    assert "WRITE-ON-END" in out


def test_both_triggers_request_the_same_artifact():
    """Different reason, same ask — otherwise the two paths drift and only one
    of them produces something the next session can resume from."""
    signals = {"cwd": "/home/x/projects/vault-cli"}
    for out in (pre_compact_capture(signals), session_end_capture(signals)):
        assert "record_insight" in out
        assert "project='vault-cli'" in out


def test_project_falls_back_when_signals_are_missing():
    for fn in (pre_compact_capture, session_end_capture):
        assert "<vault 10-projects basename>" in fn({})
        assert "<vault 10-projects basename>" in fn(None)


def test_pre_compact_hook_emits_a_system_message():
    """The hook is the surface Claude Code actually runs; a capture function
    nothing invokes is the bug this fixes."""
    proc = subprocess.run(
        [sys.executable, str(HOOKS / "pre-compact.py")],
        input=json.dumps({"cwd": "/home/x/projects/vault-cli"}),
        capture_output=True, text=True, check=True,
    )
    payload = json.loads(proc.stdout)
    assert "WRITE-BEFORE-COMPACT" in payload["systemMessage"]


def test_pre_compact_hook_tolerates_malformed_stdin():
    proc = subprocess.run(
        [sys.executable, str(HOOKS / "pre-compact.py")],
        input="not json", capture_output=True, text=True, check=True,
    )
    assert "systemMessage" in json.loads(proc.stdout)


def test_precompact_is_registered_as_a_hook():
    """The regression that mattered: the logic existed, nothing triggered it."""
    hooks = json.loads((HOOKS / "hooks.json").read_text())["hooks"]
    assert "PreCompact" in hooks, "PreCompact not registered"
    cmd = hooks["PreCompact"][0]["hooks"][0]["command"]
    assert "pre-compact.py" in cmd


def test_both_triggers_ask_for_the_narrative_too():
    """Narrative upkeep had no writer, no trigger and no instruction — it was
    pure session habit, which is why it lapsed. The capture request is the only
    thing that fires at the right moment, so the ask belongs here."""
    signals = {"cwd": "/home/x/projects/vault-cli"}
    for out in (pre_compact_capture(signals), session_end_capture(signals)):
        assert "narrative.md" in out
        assert "10-projects/vault-cli/narrative.md" in out
        assert "superseded" in out
        assert "updated:" in out
