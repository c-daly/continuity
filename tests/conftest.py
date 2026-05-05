"""Pytest fixtures for continuity tests."""

import sys
from pathlib import Path

import pytest

# Add lib/ to path so tests can import vault_provider, resume_brief
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))


@pytest.fixture
def fake_vault(tmp_path):
    """Create a minimal vault structure for testing.

    Layout:
      <tmp>/vault/
        10-projects/
          test-project/
            narrative.md         (3 H2 sections, dated)
            decisions/
              2026-05-02-use-approach-x.md
              2026-04-15-old-decision.md  (>30 days old)
              not-a-decision.md           (no date prefix; should be skipped)
          empty-project/         (exists but no narrative/decisions/journal)
        journal/
          2026-05-04.md          (daily)
          2026-05-03.md          (daily)
          2026-05-02.md          (daily)
          2026-04-30.md          (daily, older)
          week-2026-18.md        (weekly, should be skipped)
    """
    vault = tmp_path / "vault"

    # Test project with full content
    project = vault / "10-projects" / "test-project"
    project.mkdir(parents=True)

    (project / "narrative.md").write_text(
        "---\n"
        "project: test-project\n"
        "---\n"
        "\n"
        "# Test Project Narrative\n"
        "\n"
        "## 2026-04-15 — kickoff\n"
        "\n"
        "Initial scoping. Decided to use approach X.\n"
        "\n"
        "## 2026-05-02 — first milestone\n"
        "\n"
        "Shipped first feature. Y is harder than expected.\n"
        "\n"
        "## 2026-05-04 — second milestone\n"
        "\n"
        "Resolved Y by switching to approach Z. "
        "Next session: revisit performance.\n"
    )

    decisions = project / "decisions"
    decisions.mkdir()
    (decisions / "2026-05-02-use-approach-x.md").write_text(
        "---\ndate: 2026-05-02\nproject: test-project\n---\n\n"
        "# Decision: use approach X\n"
    )
    (decisions / "2026-04-15-old-decision.md").write_text(
        "---\ndate: 2026-04-15\n---\n\n# Old decision\n"
    )
    (decisions / "not-a-decision.md").write_text(
        "Should be skipped — no date prefix in filename\n"
    )

    # Empty project — exists but no content
    (vault / "10-projects" / "empty-project").mkdir()

    # Journal
    journal = vault / "journal"
    journal.mkdir(parents=True)
    for date in ("2026-05-04", "2026-05-03", "2026-05-02", "2026-04-30"):
        (journal / f"{date}.md").write_text(f"# Journal {date}\n\nActivity.\n")
    (journal / "week-2026-18.md").write_text("# Weekly\nShould be skipped.\n")

    return vault
