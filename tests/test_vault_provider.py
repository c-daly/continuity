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


# --- registry delegation ---
#
# The resolution rules themselves live in tests/test_project_registry.py, which
# is where the logic lives. These only pin that VaultProvider forwards to it —
# a provider answering the question its own way is the bug the registry exists
# to prevent.

def test_project_dirs_delegates_to_the_registry(fake_vault):
    (fake_vault / "10-projects" / "LOGOS" / "apollo").mkdir(parents=True)
    (fake_vault / "10-projects" / "LOGOS" / "apollo" / "narrative.md").write_text("#\n")
    dirs = VaultProvider(vault_path=fake_vault).project_dirs()

    assert dirs["test-project"] == "10-projects/test-project"
    assert dirs["apollo"] == "10-projects/LOGOS/apollo"


def test_resolve_project_from_path_delegates_to_the_registry(fake_vault, tmp_path):
    repo = tmp_path / "code" / "test-project"
    (repo / ".git").mkdir(parents=True)
    (repo / "src").mkdir()

    assert VaultProvider(vault_path=fake_vault).resolve_project_from_path(
        repo / "src"
    ) == ("test-project", "10-projects/test-project")


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


# --- nested sub-projects are addressable ---

@pytest.fixture
def subproject_vault(fake_vault):
    """A sub-project with its own narrative and decisions, the shape the real
    vault uses for LOGOS/apollo."""
    sub = fake_vault / "10-projects" / "LOGOS" / "apollo"
    (sub / "decisions").mkdir(parents=True)
    (sub / "narrative.md").write_text(
        "# Apollo\n\n## 2026-08-01 — first\n\nStarted.\n"
        "\n## 2026-08-20 — second\n\nShipped the thing.\n"
    )
    (sub / "decisions" / "2026-08-19-use-approach-q.md").write_text(
        "---\ndate: 2026-08-19\nproject: apollo\n---\n\n# Decision: approach Q\n"
    )
    (fake_vault / "10-projects" / "LOGOS" / "narrative.md").write_text("# LOGOS\n")
    return fake_vault


def test_narrative_reads_a_nested_subproject(subproject_vault):
    """apollo's narrative was invisible: get_narrative_sections built
    10-projects/apollo/narrative.md, a path nothing has."""
    vp = VaultProvider(vault_path=subproject_vault)
    sections = vp.get_narrative_sections("apollo")

    assert [s["heading"] for s in sections] == [
        "2026-08-20 — second",
        "2026-08-01 — first",
    ]


def test_decisions_read_from_a_nested_subproject(subproject_vault):
    vp = VaultProvider(vault_path=subproject_vault)

    assert len(vp.get_decisions("apollo")) == 1


def test_project_exists_for_a_nested_subproject(subproject_vault):
    vp = VaultProvider(vault_path=subproject_vault)

    assert vp.project_exists("apollo") is True
    assert vp.resolve_project("apollo") == "apollo"


def test_resolve_project_dir_returns_the_vault_relative_path(subproject_vault):
    """The name alone cannot express nesting, so callers that build paths need
    the directory, not the name."""
    vp = VaultProvider(vault_path=subproject_vault)

    assert vp.resolve_project_dir("apollo") == "10-projects/LOGOS/apollo"
    assert vp.resolve_project_dir("test-project") == "10-projects/test-project"
    assert vp.resolve_project_dir("nope") is None
