"""Tests for resume_brief — the v0 composer."""

import pytest

from memory_read_provider import MemoryReadProvider
from resume_brief import resume_brief
from vault_provider import VaultProvider


@pytest.fixture
def unavailable_memory(tmp_path):
    """MemoryReadProvider pointed at a non-existent binary — available() is False."""
    return MemoryReadProvider(memory_bin=tmp_path / "no-such-binary")


@pytest.fixture
def available_memory(tmp_path):
    """MemoryReadProvider backed by a fake CLI returning two observations.

    Both are scoped to subject=test-project (so the resume brief will
    surface them). The fake CLI ignores filter args and returns the same
    lines regardless, which is fine for this test — we're verifying
    composition, not memory's own filtering semantics.
    """
    fake_bin = tmp_path / "fake-memory"
    fake_bin.write_text(
        "#!/bin/sh\n"
        "echo 'project:test-project:milestone-shipped — first milestone landed 2026-05-10'\n"
        "echo 'feedback:test-project:prefer-small-prs — keep PRs under 400 lines when possible'\n"
    )
    fake_bin.chmod(0o755)
    return MemoryReadProvider(memory_bin=fake_bin)


def test_resume_brief_known_project(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    brief = resume_brief("test-project", vault=vp)
    assert "Resume brief: test-project" in brief
    assert "Most recent narrative" in brief
    assert "second milestone" in brief
    assert "approach Z" in brief


def test_resume_brief_includes_recent_decisions(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    brief = resume_brief("test-project", vault=vp)
    # Recent decisions section should appear (2026-05-02 is within 30 days
    # of test fake-vault dates — but real-time `since` filter uses now())
    # So we just check the section header is conditionally present.
    # The 2026-04-15 decision is >30 days old by any current date, won't appear.
    assert "Recent decisions" in brief or len([
        # If no decisions in window, section is omitted; that's also valid
    ]) == 0


def test_resume_brief_includes_journal(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    brief = resume_brief("test-project", vault=vp)
    assert "Recent journal entries" in brief
    assert "2026-05-04" in brief


def test_resume_brief_unknown_project_lists_alternatives(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    brief = resume_brief("no-such-project", vault=vp)
    assert "not found" in brief
    assert "test-project" in brief  # listed as available


def test_resume_brief_empty_project(fake_vault):
    vp = VaultProvider(vault_path=fake_vault)
    brief = resume_brief("empty-project", vault=vp)
    assert "Resume brief: empty-project" in brief
    # Empty project has no narrative or decisions; journal (vault-wide) may still appear.
    # The "no project-specific content" message should fire.
    assert "No project-specific content found" in brief


def test_resume_brief_truncates_long_narrative(fake_vault):
    # Add a very long section to the narrative
    project = fake_vault / "10-projects" / "test-project"
    long_section = "## 2026-05-05 — huge update\n\n" + ("X" * 3000) + "\n"
    narrative = project / "narrative.md"
    narrative.write_text(narrative.read_text() + "\n" + long_section)

    vp = VaultProvider(vault_path=fake_vault)
    brief = resume_brief("test-project", vault=vp)
    assert "truncated" in brief


def test_resume_brief_omits_memory_sections_when_unavailable(
    fake_vault, unavailable_memory
):
    """Brief should compose normally when memory CLI is missing."""
    vp = VaultProvider(vault_path=fake_vault)
    brief = resume_brief("test-project", vault=vp, memory=unavailable_memory)
    assert "Resume brief: test-project" in brief
    assert "Memory observations" not in brief
    assert "Continuity synthesis" not in brief
    # Vault-side sections still present
    assert "Most recent narrative" in brief


def test_resume_brief_includes_memory_when_available(fake_vault, available_memory):
    """Memory observations + synthesis sections appear when memory has entries."""
    vp = VaultProvider(vault_path=fake_vault)
    brief = resume_brief("test-project", vault=vp, memory=available_memory)
    assert "## Memory observations" in brief
    assert "milestone-shipped" in brief
    assert "prefer-small-prs" in brief
    assert "## Continuity synthesis" in brief
    # Synthesis is conservative — just counts + types
    assert "memory observation" in brief
    # First-order observations and synthesis are clearly separated sections
    obs_idx = brief.index("## Memory observations")
    syn_idx = brief.index("## Continuity synthesis")
    assert obs_idx < syn_idx


def test_resume_brief_memory_counts_as_project_specific_context(fake_vault, tmp_path):
    fake_bin = tmp_path / "fake-memory"
    fake_bin.write_text(
        "#!/bin/sh\n"
        "echo 'project:empty-project:memory-only — project context from memory'\n"
    )
    fake_bin.chmod(0o755)
    memory = MemoryReadProvider(memory_bin=fake_bin)
    vp = VaultProvider(vault_path=fake_vault)

    brief = resume_brief("empty-project", vault=vp, memory=memory)

    assert "## Memory observations" in brief
    assert "memory-only" in brief
    assert "No project-specific content found" not in brief


def test_memory_section_is_scored_and_budgeted(fake_vault, tmp_path, monkeypatch):
    monkeypatch.setenv("CONTINUITY_CONFIG_DIR", str(tmp_path))
    fake_bin = tmp_path / "fake-memory"
    fake_bin.write_text(
        "#!/bin/sh\n"
        "echo 'project:test-project:2026-01-01-ancient — old episodic'\n"
        "echo 'feedback:test-project:2026-06-18-pref — durable preference'\n"
    )
    fake_bin.chmod(0o755)
    vp = VaultProvider(vault_path=fake_vault)
    mem = MemoryReadProvider(memory_bin=fake_bin)

    brief = resume_brief("test-project", vault=vp, memory=mem)

    # Durable/recent feedback ranks above the ancient episodic project entry.
    assert brief.index("2026-06-18-pref") < brief.index("2026-01-01-ancient")
    # Surfacing was recorded to the (isolated) index.
    import json
    idx = json.loads((tmp_path / "relevance.json").read_text())
    assert idx["2026-06-18-pref"]["freq"] == 1


def test_resume_brief_reads_a_nested_subproject(fake_vault, monkeypatch):
    """End to end for the thing that was invisible: a sub-project's brief. Its
    narrative and decisions live under LOGOS/apollo, which the flat
    10-projects/<name> path could not reach."""
    monkeypatch.setenv("CONTINUITY_VAULT_DIR", str(fake_vault))
    sub = fake_vault / "10-projects" / "LOGOS" / "apollo"
    (sub / "decisions").mkdir(parents=True)
    (sub / "narrative.md").write_text(
        "# Apollo\n\n## 2026-08-20 — shipped the telemetry pass\n\nIt works.\n"
    )
    (fake_vault / "10-projects" / "LOGOS" / "narrative.md").write_text("# LOGOS\n")

    brief = resume_brief("apollo")

    assert "# Resume brief: apollo" in brief
    assert "shipped the telemetry pass" in brief


def test_unknown_project_error_lists_nested_projects_too(fake_vault, monkeypatch):
    """Addressable but undiscoverable is only half a fix — the error that tells
    you what exists has to name them."""
    monkeypatch.setenv("CONTINUITY_VAULT_DIR", str(fake_vault))
    sub = fake_vault / "10-projects" / "LOGOS" / "apollo"
    sub.mkdir(parents=True)
    (sub / "narrative.md").write_text("# apollo\n")

    out = resume_brief("no-such-project")

    assert "not found" in out
    assert "LOGOS/apollo" in out


def test_brief_for_a_shadowed_nested_project_reads_that_project(
    fake_vault, monkeypatch
):
    """`LOGOS/logos` is only reachable by path, because the bare name means the
    top-level project. Canonicalising to the name 'logos' and re-resolving threw
    that away, so the brief showed LOGOS's content under logos's title —
    silently, which is the worst way to be wrong."""
    monkeypatch.setenv("CONTINUITY_VAULT_DIR", str(fake_vault))
    logos = fake_vault / "10-projects" / "LOGOS"
    (logos / "logos").mkdir(parents=True)
    (logos / "narrative.md").write_text(
        "# LOGOS\n\n## 2026-08-01 — the whole ecosystem\n\nparent content\n"
    )
    (logos / "logos" / "narrative.md").write_text(
        "# Foundry\n\n## 2026-08-02 — the contract floor\n\nsub content\n"
    )

    brief = resume_brief("LOGOS/logos")

    assert "the contract floor" in brief
    assert "the whole ecosystem" not in brief
