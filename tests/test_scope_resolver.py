import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from scope_resolver import subject_to_relpath, resolve_scope


def _vault(tmp_path):
    sophia = tmp_path / "10-projects" / "LOGOS" / "sophia"
    sophia.mkdir(parents=True)
    # A nested project is one that carries its own narrative — that is what
    # separates LOGOS/sophia from LOGOS/decisions. Every sub-project in the real
    # vault has one.
    (sophia / "narrative.md").write_text("# sophia\n")
    (tmp_path / "10-projects" / "agent-swarm").mkdir(parents=True)
    return tmp_path


def test_subject_user_is_root(tmp_path):
    assert subject_to_relpath("user", _vault(tmp_path)) == ""

def test_subject_project_maps_to_dir(tmp_path):
    assert subject_to_relpath("LOGOS", _vault(tmp_path)) == "10-projects/LOGOS"

def test_subject_nested_entity_maps_to_nested_dir(tmp_path):
    assert subject_to_relpath("sophia", _vault(tmp_path)) == "10-projects/LOGOS/sophia"

def test_subject_unknown_is_none(tmp_path):
    assert subject_to_relpath("nope", _vault(tmp_path)) is None

def test_resolve_scope_same_subject(tmp_path):
    assert resolve_scope(["LOGOS", "LOGOS"], _vault(tmp_path)) == "10-projects/LOGOS"

def test_resolve_scope_parent_and_child(tmp_path):
    # LOGOS + its sub-entity sophia -> tightest common = LOGOS
    assert resolve_scope(["LOGOS", "sophia"], _vault(tmp_path)) == "10-projects/LOGOS"

def test_resolve_scope_sibling_projects(tmp_path):
    # LOGOS + agent-swarm -> common prefix is 10-projects
    assert resolve_scope(["LOGOS", "agent-swarm"], _vault(tmp_path)) == "10-projects"

def test_resolve_scope_spans_user_is_root(tmp_path):
    assert resolve_scope(["user", "LOGOS"], _vault(tmp_path)) == ""

def test_resolve_scope_unlocatable_subject_ignored(tmp_path):
    # unknown subjects do not drag scope to root; they are dropped
    assert resolve_scope(["LOGOS", "nope"], _vault(tmp_path)) == "10-projects/LOGOS"

def test_resolve_scope_all_unlocatable_is_none(tmp_path):
    assert resolve_scope(["nope", "ghost"], _vault(tmp_path)) is None


def test_resolve_scope_no_projects_dir_is_none(tmp_path):
    assert resolve_scope(["LOGOS"], tmp_path) is None


def test_resolve_scope_three_subjects(tmp_path):
    v = _vault(tmp_path)
    (v / "10-projects" / "LOGOS" / "hermes").mkdir(parents=True, exist_ok=True)
    assert resolve_scope(["LOGOS", "sophia", "hermes"], v) == "10-projects/LOGOS"


def test_subject_with_glob_metachar_is_literal(tmp_path):
    assert subject_to_relpath("a*b", _vault(tmp_path)) is None


def _vault_with_artifacts(tmp_path):
    v = _vault(tmp_path)
    (v / "10-projects" / "LOGOS" / "decisions").mkdir()
    (v / "10-projects" / "agent-swarm" / "plans").mkdir()
    (v / "10-projects" / "agent-swarm" / ".memory").mkdir()
    return v


def test_artifact_directory_is_not_an_entity(tmp_path):
    """The raw rglob matched any directory name, so a subject called 'plans' or
    'decisions' resolved to some project's artifact directory — and a promotion
    scoped there is filed inside another project's content."""
    v = _vault_with_artifacts(tmp_path)

    assert subject_to_relpath("plans", v) is None
    assert subject_to_relpath("decisions", v) is None
    assert subject_to_relpath(".memory", v) is None


def test_artifact_directory_does_not_drag_a_scope_into_a_project(tmp_path):
    """resolve_scope drops unlocatable subjects, so an artifact name must be
    unlocatable — otherwise it pulls the common prefix into one project."""
    v = _vault_with_artifacts(tmp_path)

    assert resolve_scope(["LOGOS", "plans"], v) == "10-projects/LOGOS"


def test_real_projects_still_resolve(tmp_path):
    v = _vault_with_artifacts(tmp_path)

    assert subject_to_relpath("LOGOS", v) == "10-projects/LOGOS"
    assert subject_to_relpath("sophia", v) == "10-projects/LOGOS/sophia"
    assert subject_to_relpath("agent-swarm", v) == "10-projects/agent-swarm"
