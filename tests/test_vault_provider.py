"""Tests for VaultProvider — the vault read provider."""

import pytest

from vault_provider import VaultProvider


# --- construction ---

def test_explicit_vault_path(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    assert vp.vault_path == fake_vault


def test_env_var_fallback(fake_vault, monkeypatch):
    monkeypatch.setenv("CONTINUITY_VAULT_DIR", str(fake_vault))
    vp = VaultProvider()
    assert vp.vault_path == fake_vault


def test_vault_dir_env_var_fallback(fake_vault, monkeypatch):
    monkeypatch.delenv("CONTINUITY_VAULT_DIR", raising=False)
    monkeypatch.setenv("VAULT_DIR", str(fake_vault))
    vp = VaultProvider()
    assert vp.vault_path == fake_vault


def test_no_vault_path_raises(monkeypatch):
    monkeypatch.delenv("CONTINUITY_VAULT_DIR", raising=False)
    monkeypatch.delenv("VAULT_DIR", raising=False)
    with pytest.raises(ValueError, match="Vault path not provided"):
        VaultProvider()


def test_nonexistent_vault_raises(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        VaultProvider(vault_path=tmp_path / "no-such-dir")


# --- list_projects ---

def test_list_projects(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    assert vp.list_projects() == ["empty-project", "test-project"]


def test_list_projects_no_dir(tmp_path):
    vp = VaultProvider(vault_path=tmp_path)
    assert vp.list_projects() == []


# --- project_exists ---

def test_project_exists_true(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    assert vp.project_exists("test-project") is True


def test_project_exists_false(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    assert vp.project_exists("no-such-project") is False


def test_resolve_project_case_insensitive(fake_vault):
    (fake_vault / "10-projects" / "CaseProject").mkdir()
    vp = VaultProvider(vault_path=fake_vault)

    assert vp.project_exists("caseproject") is True
    assert vp.resolve_project("caseproject") == "CaseProject"
    assert vp.resolve_project("CASEPROJECT") == "CaseProject"
    assert vp.resolve_project("no-such-project") is None



# --- project_dirs / resolve_project_from_path ---

@pytest.fixture
def nested_vault(fake_vault):
    """fake_vault plus the two shapes flat resolution gets wrong: a project
    with artifact subdirectories, and a project nesting sub-projects."""
    projects = fake_vault / "10-projects"
    (projects / "test-project" / "plans").mkdir()
    (projects / "test-project" / ".memory").mkdir()
    apollo = projects / "LOGOS" / "apollo"
    apollo.mkdir(parents=True)
    (apollo / "narrative.md").write_text("# apollo\n")
    (projects / "LOGOS" / "narrative.md").write_text("# LOGOS\n")
    (projects / "LOGOS" / "decisions").mkdir()
    return fake_vault


def test_project_dirs_maps_projects_to_vault_relative_paths(nested_vault):
    dirs = VaultProvider(vault_path=nested_vault).project_dirs()

    assert dirs["test-project"] == "10-projects/test-project"
    assert dirs["LOGOS"] == "10-projects/LOGOS"
    # Nested sub-projects are projects in their own right — they carry a narrative.
    assert dirs["apollo"] == "10-projects/LOGOS/apollo"


def test_project_dirs_excludes_artifact_subdirectories(nested_vault):
    """decisions/, plans/, .memory/ are artifact directories. Treating one as a
    project sends a write into a sibling of the real project's content."""
    dirs = VaultProvider(vault_path=nested_vault).project_dirs()

    assert "plans" not in dirs
    assert "decisions" not in dirs
    assert ".memory" not in dirs


def test_resolve_project_from_path_walks_up_from_a_nested_cwd(nested_vault):
    """The bug this exists for: a session in a subdirectory of the repo.
    The basename is 'src', the project is still test-project."""
    vp = VaultProvider(vault_path=nested_vault)

    assert vp.resolve_project_from_path(
        "/home/x/projects/test-project/src"
    ) == ("test-project", "10-projects/test-project")


def test_resolve_project_from_path_prefers_the_deepest_project(nested_vault):
    """…/LOGOS/apollo is apollo's work, not LOGOS's — deepest match wins."""
    vp = VaultProvider(vault_path=nested_vault)

    assert vp.resolve_project_from_path("/home/x/LOGOS/apollo") == (
        "apollo",
        "10-projects/LOGOS/apollo",
    )


def test_resolve_project_from_path_is_case_insensitive(nested_vault):
    vp = VaultProvider(vault_path=nested_vault)

    assert vp.resolve_project_from_path("/home/x/logos")[0] == "LOGOS"


def test_resolve_project_from_path_skips_artifact_directory_names(nested_vault):
    """A cwd ending in plans/ must not resolve to some other project's plans/."""
    vp = VaultProvider(vault_path=nested_vault)

    assert vp.resolve_project_from_path(
        "/home/x/projects/test-project/plans"
    ) == ("test-project", "10-projects/test-project")


def test_resolve_project_from_path_returns_none_when_nothing_matches(nested_vault):
    """Better no answer than a confident wrong one — the caller falls back to a
    placeholder rather than naming a project directory that does not exist."""
    vp = VaultProvider(vault_path=nested_vault)

    assert vp.resolve_project_from_path("/tmp/scratch") is None
    assert vp.resolve_project_from_path("") is None

# --- get_narrative_sections ---

def test_narrative_sections_newest_first(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    sections = vp.get_narrative_sections("test-project", last_n=3)
    assert len(sections) == 3
    assert sections[0]["heading"] == "2026-05-04 — second milestone"
    assert sections[1]["heading"] == "2026-05-02 — first milestone"
    assert sections[2]["heading"] == "2026-04-15 — kickoff"
    assert "approach Z" in sections[0]["body"]


def test_narrative_sections_last_n_limit(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    sections = vp.get_narrative_sections("test-project", last_n=2)
    assert len(sections) == 2
    assert sections[0]["heading"] == "2026-05-04 — second milestone"
    assert sections[1]["heading"] == "2026-05-02 — first milestone"


def test_narrative_no_file(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    assert vp.get_narrative_sections("empty-project") == []


def test_narrative_unknown_project(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    assert vp.get_narrative_sections("nonexistent") == []


# --- get_decisions ---

def test_get_decisions_all(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    decisions = vp.get_decisions("test-project")
    # Two valid decisions; the "not-a-decision.md" file is skipped
    assert len(decisions) == 2
    assert decisions[0]["date"] == "2026-05-02"  # newest first
    assert decisions[0]["slug"] == "use-approach-x"
    assert decisions[1]["date"] == "2026-04-15"


def test_get_decisions_since(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    decisions = vp.get_decisions("test-project", since="2026-05-01")
    assert len(decisions) == 1
    assert decisions[0]["date"] == "2026-05-02"


def test_get_decisions_no_dir(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    assert vp.get_decisions("empty-project") == []


# --- get_journal_entries ---

def test_journal_entries_recent(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    entries = vp.get_journal_entries(days_back=3)
    assert len(entries) == 3
    # Newest first
    assert [e["date"] for e in entries] == ["2026-05-04", "2026-05-03", "2026-05-02"]


def test_journal_skips_weekly(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    entries = vp.get_journal_entries(days_back=10)
    dates = [e["date"] for e in entries]
    assert "week-2026-18" not in dates  # weekly file skipped
    assert all("week" not in d for d in dates)
