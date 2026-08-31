"""Capture triggers.

SessionEnd was continuity's only capture point, which is why nothing had been
recorded since 2026-06-11: a long session compacts repeatedly and may never end
cleanly, and once it has compacted the detail worth recording is gone. These
tests pin both triggers and the fact that they ask for the same artifact.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from session_capture import pre_compact_capture, session_end_capture
from vault_write_provider import validate_basename

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


@pytest.fixture
def checkout(tmp_path):
    """Build a work tree at <tmp>/code/<name>, returning its root. Real
    directories, not string literals: the resolver reads the filesystem to find
    the work-tree root, so a made-up path exercises a code path no session
    takes."""
    def _make(name, subdirs=(), git=True):
        root = tmp_path / "code" / name
        root.mkdir(parents=True, exist_ok=True)
        if git:
            (root / ".git").mkdir(exist_ok=True)
        for sub in subdirs:
            (root / sub).mkdir(parents=True, exist_ok=True)
        return root
    return _make


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


def test_nested_cwd_still_names_the_canonical_project(capture_vault, checkout):
    """A session run from a subdirectory of the repo. The cwd basename is
    'src', which names no project — the capture request must still point at
    vault-cli, or it sends the insight (and the narrative edit) somewhere the
    real project's content is not."""
    signals = {"cwd": str(checkout("vault-cli", subdirs=["src"]) / "src")}
    for out in (pre_compact_capture(signals), session_end_capture(signals)):
        assert "project='vault-cli'" in out
        assert "10-projects/vault-cli/narrative.md" in out
        assert "10-projects/src" not in out


def test_artifact_subdirectory_does_not_become_the_project(capture_vault, checkout):
    """plans/ and decisions/ exist inside projects across the vault; a cwd
    ending in one must resolve to its project, not to some other project's
    plans directory."""
    signals = {"cwd": str(checkout("vault-cli", subdirs=["plans"]) / "plans")}
    out = session_end_capture(signals)
    assert "project='vault-cli'" in out
    assert "10-projects/vault-cli/narrative.md" in out


def test_a_subproject_capture_lands_in_one_tree(capture_vault, checkout):
    """A session in a sub-project is attributed to the project that owns it,
    and the insight and the narrative name the same tree.

    'apollo' is the truer answer, but record_insight addresses a project by a
    single basename under 10-projects/, so it would file the insight in a fresh
    flat 10-projects/apollo/ while the narrative sat under LOGOS/apollo/ — one
    session split across two trees, one of them invented. Precision that the
    write path cannot honour is worse than the coarser true answer."""
    out = session_end_capture(
        {"cwd": str(checkout("LOGOS", subdirs=["apollo"]) / "apollo")}
    )
    assert "project='LOGOS'" in out
    assert "10-projects/LOGOS/narrative.md" in out
    assert "10-projects/apollo" not in out


def test_unknown_cwd_gets_a_placeholder_not_a_fabricated_path(capture_vault, tmp_path):
    """record_insight creates <project>/insights/ on write, so an invented
    project name silently makes a duplicate project directory while the real
    narrative stays stale. A placeholder the agent must fill in is the honest
    answer when the cwd names nothing in the vault."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    out = session_end_capture({"cwd": str(scratch)})
    assert "<vault 10-projects basename>" in out
    assert "10-projects/scratch" not in out


def test_a_coincidental_path_component_does_not_claim_the_project(
    capture_vault, tmp_path
):
    """/tmp/LOGOS/notes is not LOGOS. Recording there would put this session's
    insight in LOGOS's tree and send the agent to edit LOGOS's narrative —
    corrupting two projects' records at once instead of neither."""
    stray = tmp_path / "LOGOS" / "notes"
    stray.mkdir(parents=True)
    out = session_end_capture({"cwd": str(stray)})
    assert "<vault 10-projects basename>" in out
    assert "LOGOS" not in out


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


def test_the_emitted_project_is_one_the_write_path_can_address(
    capture_vault, checkout, tmp_path
):
    """The insight and the narrative must name the same tree, and the writer has
    to be able to reach it. record_insight passes the project through
    validate_basename and joins it as a single segment under 10-projects/, so
    any name the guidance emits has to survive that and match the narrative
    directory it names in the same breath. Nothing else holds the two halves of
    the capture request together."""
    scratch = tmp_path / "elsewhere"
    scratch.mkdir()
    cwds = [
        checkout("vault-cli", subdirs=["src"]) / "src",
        checkout("LOGOS", subdirs=["apollo"]) / "apollo",
        checkout("vault-cli"),
        scratch,
    ]
    for cwd in cwds:
        out = session_end_capture({"cwd": str(cwd)})
        project = re.search(r"project='([^']*)'", out).group(1)
        narrative = re.search(r"<vault>/(\S+)/narrative\.md", out).group(1)
        if project == "<vault 10-projects basename>":
            continue
        validate_basename(project, "project")  # raises if the writer would reject
        assert narrative == f"10-projects/{project}", (
            f"{cwd}: insight goes to 10-projects/{project}, narrative to {narrative}"
        )
