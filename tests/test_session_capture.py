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

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from session_capture import pre_compact_capture, session_end_capture

HOOKS = Path(__file__).resolve().parent.parent / "hooks"


@pytest.fixture(autouse=True)
def capture_vault(tmp_path, monkeypatch):
    """A vault to resolve session cwds against, carrying the shapes a cwd
    basename gets wrong: a project with artifact subdirectories, and a project
    nesting a sub-project. Autouse so no test reads the developer's real vault
    and passes by coincidence."""
    projects = tmp_path / "capture-vault" / "10-projects"
    (projects / "vault-cli" / "plans").mkdir(parents=True)
    (projects / "vault-cli" / "narrative.md").write_text("# vault-cli\n")
    apollo = projects / "LOGOS" / "apollo"
    apollo.mkdir(parents=True)
    (apollo / "narrative.md").write_text("# apollo\n")
    (projects / "LOGOS" / "narrative.md").write_text("# LOGOS\n")

    monkeypatch.setenv("CONTINUITY_VAULT_DIR", str(projects.parent))
    monkeypatch.delenv("VAULT_DIR", raising=False)
    return projects.parent


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


def test_nested_cwd_still_names_the_canonical_project(capture_vault):
    """A session run from a subdirectory of the repo. The cwd basename is
    'src', which names no project — the capture request must still point at
    vault-cli, or it sends the insight (and the narrative edit) somewhere the
    real project's content is not."""
    signals = {"cwd": "/home/x/projects/vault-cli/src"}
    for out in (pre_compact_capture(signals), session_end_capture(signals)):
        assert "project='vault-cli'" in out
        assert "10-projects/vault-cli/narrative.md" in out
        assert "10-projects/src" not in out


def test_artifact_subdirectory_does_not_become_the_project(capture_vault):
    """plans/ and decisions/ exist inside projects across the vault; a cwd
    ending in one must resolve to its project, not to some other project's
    plans directory."""
    signals = {"cwd": "/home/x/projects/vault-cli/plans"}
    out = session_end_capture(signals)
    assert "project='vault-cli'" in out
    assert "10-projects/vault-cli/narrative.md" in out


def test_nested_subproject_gets_its_own_narrative(capture_vault):
    """The vault nests sub-projects, each with its own narrative. A flat
    10-projects/<basename> template cannot express that path at all."""
    out = session_end_capture({"cwd": "/home/x/code/LOGOS/apollo"})
    assert "project='apollo'" in out
    assert "10-projects/LOGOS/apollo/narrative.md" in out


def test_unknown_cwd_gets_a_placeholder_not_a_fabricated_path(capture_vault):
    """record_insight creates <project>/insights/ on write, so an invented
    project name silently makes a duplicate project directory while the real
    narrative stays stale. A placeholder the agent must fill in is the honest
    answer when the cwd names nothing in the vault."""
    out = session_end_capture({"cwd": "/tmp/scratch"})
    assert "<vault 10-projects basename>" in out
    assert "10-projects/scratch" not in out


def test_falls_back_to_the_basename_when_the_vault_is_unreachable(monkeypatch):
    """No vault configured in the hook's environment means we cannot verify —
    keep the basename hint rather than dropping to a placeholder."""
    monkeypatch.delenv("CONTINUITY_VAULT_DIR", raising=False)
    monkeypatch.delenv("VAULT_DIR", raising=False)
    out = session_end_capture({"cwd": "/home/x/projects/vault-cli"})
    assert "project='vault-cli'" in out
    assert "10-projects/vault-cli/narrative.md" in out


def test_guidance_matches_the_narrative_reader_convention(capture_vault):
    """VaultProvider.get_narrative_sections does sections[-last_n:][::-1] — the
    narrative is append-only, newest last. Telling the agent to *prepend* would
    put the newest section at the top, so the resume brief would surface the
    project's three oldest sections as its current state. The guidance and the
    reader have to agree or the brief silently rots."""
    for out in (
        pre_compact_capture({"cwd": "/home/x/projects/vault-cli"}),
        session_end_capture({"cwd": "/home/x/projects/vault-cli"}),
    ):
        assert "prepend" not in out
        assert "append a dated section" in out
