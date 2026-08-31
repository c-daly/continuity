"""The one answer to 'what projects exist and where'.

The vault nests sub-projects (`10-projects/LOGOS/apollo/`), each with its own
narrative and decisions. Every consumer that maps a name or a path to a project
directory — the read provider, the write provider, capture, synthesis scope —
used to answer that question its own way, and disagreed. These tests pin the
shared answer.
"""

import pytest

from project_registry import project_dirs, resolve, resolve_from_path


@pytest.fixture
def vault(tmp_path):
    """A vault with the shapes that make resolution hard: artifact
    subdirectories, nested sub-projects, and a nested leaf whose name collides
    with a top-level project (the real vault has LOGOS and LOGOS/logos)."""
    projects = tmp_path / "10-projects"
    for name in ("test-project", "agent-swarm"):
        (projects / name).mkdir(parents=True)
        (projects / name / "narrative.md").write_text(f"# {name}\n")
    (projects / "test-project" / "plans").mkdir()
    (projects / "test-project" / "decisions").mkdir()
    (projects / "test-project" / ".memory").mkdir()

    for sub in ("apollo", "logos"):
        d = projects / "LOGOS" / sub
        d.mkdir(parents=True)
        (d / "narrative.md").write_text(f"# {sub}\n")
    (projects / "LOGOS" / "narrative.md").write_text("# LOGOS\n")
    (projects / "LOGOS" / "decisions").mkdir()
    return tmp_path


@pytest.fixture
def checkout(tmp_path):
    """Build a real work tree — resolution reads the filesystem to find the
    checkout root, so a string literal exercises a path no session takes."""
    def _make(name, subdirs=(), git=True):
        root = tmp_path / "code" / name
        root.mkdir(parents=True, exist_ok=True)
        if git:
            (root / ".git").mkdir(exist_ok=True)
        for sub in subdirs:
            (root / sub).mkdir(parents=True, exist_ok=True)
        return root
    return _make


# --- project_dirs ---

def test_project_dirs_includes_direct_children_and_nested_subprojects(vault):
    dirs = project_dirs(vault)

    assert dirs["test-project"] == "10-projects/test-project"
    assert dirs["LOGOS"] == "10-projects/LOGOS"
    assert dirs["apollo"] == "10-projects/LOGOS/apollo"


def test_project_dirs_excludes_artifact_subdirectories(vault):
    """decisions/, plans/ and .memory/ are artifact directories. Treating one as
    a project files an insight in a sibling of the real project's content."""
    dirs = project_dirs(vault)

    assert "plans" not in dirs
    assert "decisions" not in dirs
    assert ".memory" not in dirs


def test_project_dirs_excludes_dot_directories_at_the_root(vault):
    """The real vault keeps 10-projects/.memory — a memory store, not a project.
    Every direct child counting as a project made it addressable, so a stray
    write could land in the store."""
    (vault / "10-projects" / ".memory").mkdir()
    (vault / "10-projects" / ".obsidian").mkdir()
    dirs = project_dirs(vault)

    assert ".memory" not in dirs
    assert ".obsidian" not in dirs
    assert resolve(".memory", vault) is None


def test_project_dirs_is_empty_without_a_projects_root(tmp_path):
    assert project_dirs(tmp_path) == {}


# --- resolve ---

def test_resolve_direct_child(vault):
    assert resolve("test-project", vault) == "10-projects/test-project"


def test_resolve_is_case_insensitive(vault):
    assert resolve("TEST-PROJECT", vault) == "10-projects/test-project"


def test_resolve_a_unique_nested_leaf_name(vault):
    """apollo names exactly one project, so it needs no path."""
    assert resolve("apollo", vault) == "10-projects/LOGOS/apollo"


def test_resolve_prefers_the_top_level_project_over_a_nested_leaf(vault):
    """The real vault has LOGOS and LOGOS/logos. A bare name always means the
    top-level project, so no existing caller silently retargets."""
    assert resolve("logos", vault) == "10-projects/LOGOS"


def test_resolve_reaches_a_shadowed_nested_project_by_path(vault):
    """…which leaves the explicit path as the only way to the nested one."""
    assert resolve("LOGOS/logos", vault) == "10-projects/LOGOS/logos"


def test_resolve_an_explicit_path(vault):
    assert resolve("LOGOS/apollo", vault) == "10-projects/LOGOS/apollo"


def test_resolve_unknown_project_is_none(vault):
    """None, not an error: record_insight starts a new project by writing to
    a name the vault has never seen."""
    assert resolve("brand-new-thing", vault) is None
    assert resolve("", vault) is None


def test_resolve_ambiguous_nested_leaf_raises_and_names_the_candidates(vault):
    """Two nested projects share a leaf name and neither is top-level. Guessing
    would file the insight in one of two real projects — worse than refusing,
    because it is plausible enough to go unnoticed."""
    for parent in ("agent-swarm", "test-project"):
        d = vault / "10-projects" / parent / "shared-name"
        d.mkdir()
        (d / "narrative.md").write_text("# shared\n")

    with pytest.raises(ValueError) as exc:
        resolve("shared-name", vault)
    assert "agent-swarm/shared-name" in str(exc.value)
    assert "test-project/shared-name" in str(exc.value)


def test_resolve_rejects_path_traversal(vault):
    """`project` reaches filesystem path construction in the write provider."""
    for hostile in ("../../etc", "/etc/passwd", "LOGOS/../../../etc", ".."):
        assert resolve(hostile, vault) is None


# --- resolve_from_path ---

def test_resolve_from_path_walks_up_from_a_nested_cwd(vault, checkout):
    repo = checkout("test-project", subdirs=["src/deep"])

    assert resolve_from_path(repo / "src" / "deep", vault) == (
        "test-project",
        "10-projects/test-project",
    )


def test_resolve_from_path_gives_a_subproject_its_own_directory(vault, checkout):
    """Now that the write path can address it, a session in LOGOS/apollo is
    attributed to apollo rather than collapsed onto its parent."""
    repo = checkout("LOGOS", subdirs=["apollo"])

    assert resolve_from_path(repo / "apollo", vault) == (
        "apollo",
        "10-projects/LOGOS/apollo",
    )


def test_resolve_from_path_ignores_a_coincidental_ancestor(vault, tmp_path):
    """/tmp/LOGOS/scratch is not LOGOS."""
    stray = tmp_path / "scratch" / "LOGOS" / "unrelated"
    stray.mkdir(parents=True)

    assert resolve_from_path(stray, vault) is None


def test_resolve_from_path_survives_a_git_repo_high_in_the_tree(vault, tmp_path):
    """A dotfiles repo at ~ makes the whole home directory one work tree."""
    (tmp_path / ".git").mkdir()
    stray = tmp_path / "LOGOS" / "notes" / "scratch"
    stray.mkdir(parents=True)

    assert resolve_from_path(stray, vault) is None


def test_resolve_from_path_accepts_a_bare_project_directory(vault, checkout):
    """Not every project is a checkout; the cwd's own name is still evidence."""
    assert resolve_from_path(checkout("apollo", git=False), vault) == (
        "apollo",
        "10-projects/LOGOS/apollo",
    )


def test_resolve_from_path_returns_none_when_nothing_matches(vault, tmp_path):
    assert resolve_from_path(tmp_path / "scratch", vault) is None
    assert resolve_from_path("", vault) is None


def test_resolve_rejects_an_explicit_path_to_an_artifact_directory(vault):
    """The explicit-path branch accepted anything that was a directory, which
    skipped the discriminator entirely: LOGOS/decisions is a real directory but
    not a project, and writing there puts an insight inside another project's
    decisions tree."""
    assert resolve("LOGOS/decisions", vault) is None
    assert resolve("test-project/plans", vault) is None
    assert resolve("test-project/.memory", vault) is None


def test_resolve_still_accepts_an_explicit_path_to_a_real_project(vault):
    assert resolve("LOGOS/apollo", vault) == "10-projects/LOGOS/apollo"
