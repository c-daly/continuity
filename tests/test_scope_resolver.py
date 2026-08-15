import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from scope_resolver import subject_to_relpath, resolve_scope


def _vault(tmp_path):
    (tmp_path / "10-projects" / "LOGOS" / "sophia").mkdir(parents=True)
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
