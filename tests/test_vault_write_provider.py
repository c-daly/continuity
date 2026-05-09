"""Tests for VaultWriteProvider."""

from pathlib import Path

import pytest
import yaml

from vault_write_provider import VaultWriteProvider


# --- construction ---


def test_explicit_vault_path(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    assert wp.vault_path == fake_vault


def test_env_var_fallback(fake_vault, monkeypatch):
    monkeypatch.setenv("CONTINUITY_VAULT_DIR", str(fake_vault))
    wp = VaultWriteProvider()
    assert wp.vault_path == fake_vault


def test_no_vault_path_raises(monkeypatch):
    monkeypatch.delenv("CONTINUITY_VAULT_DIR", raising=False)
    monkeypatch.delenv("VAULT_DIR", raising=False)
    with pytest.raises(ValueError, match="Vault path not provided"):
        VaultWriteProvider()


def test_nonexistent_vault_raises(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        VaultWriteProvider(vault_path=tmp_path / "no-such-dir")


# --- write: path mapping ---


def test_write_insight_path(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write(
        kind="cont.insight",
        id="2026-05-09-foo",
        frontmatter={"date": "2026-05-09", "project": "test-project"},
        body="Hello.",
    )
    expected = (
        fake_vault / "10-projects" / "test-project" / "insights" / "2026-05-09-foo.md"
    )
    assert expected.is_file()


def test_write_decision_path(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write(
        kind="cont.decision",
        id="2026-05-09-bar",
        frontmatter={"date": "2026-05-09", "project": "test-project"},
        body="Decision body.",
    )
    expected = (
        fake_vault / "10-projects" / "test-project" / "decisions" / "2026-05-09-bar.md"
    )
    assert expected.is_file()


def test_write_creates_parent_dirs(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write(
        kind="cont.insight",
        id="x",
        frontmatter={"project": "brand-new-project"},
        body="b",
    )
    target = fake_vault / "10-projects" / "brand-new-project" / "insights" / "x.md"
    assert target.is_file()


# --- write: rendering ---


def test_write_frontmatter_shape(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write(
        kind="cont.insight",
        id="i1",
        frontmatter={"date": "2026-05-09", "project": "test-project", "type": "insight"},
        body="Body text.",
    )
    target = fake_vault / "10-projects" / "test-project" / "insights" / "i1.md"
    text = target.read_text()
    assert text.startswith("---\n")
    head, _, body_part = text.partition("\n---\n")
    parsed = yaml.safe_load(head[len("---\n"):])
    assert parsed == {
        "date": "2026-05-09",
        "project": "test-project",
        "type": "insight",
    }
    assert "Body text." in body_part
    assert text.endswith("\n")


def test_write_preserves_key_order(fake_vault):
    """Frontmatter key order in the file matches insertion order."""
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write(
        kind="cont.insight",
        id="ordered",
        frontmatter={"z_last": 1, "a_first": 2, "project": "test-project"},
        body="b",
    )
    target = fake_vault / "10-projects" / "test-project" / "insights" / "ordered.md"
    text = target.read_text()
    head = text.split("\n---\n", 1)[0]
    keys_in_order = [
        line.split(":", 1)[0]
        for line in head.splitlines()
        if line and not line.startswith("---")
    ]
    assert keys_in_order == ["z_last", "a_first", "project"]


# --- write: idempotency / overwrite ---


def test_write_is_idempotent_for_same_input(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    fm = {"project": "test-project", "v": 1}
    wp.write("cont.insight", "same", fm, "body")
    target = fake_vault / "10-projects" / "test-project" / "insights" / "same.md"
    first = target.read_text()
    wp.write("cont.insight", "same", fm, "body")
    assert target.read_text() == first


def test_write_overwrites_with_new_content(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write("cont.insight", "ow", {"project": "test-project"}, "first")
    wp.write("cont.insight", "ow", {"project": "test-project"}, "second")
    target = fake_vault / "10-projects" / "test-project" / "insights" / "ow.md"
    assert "second" in target.read_text()
    assert "first" not in target.read_text()


def test_write_no_temp_file_remains(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write("cont.insight", "tmp-check", {"project": "test-project"}, "x")
    parent = fake_vault / "10-projects" / "test-project" / "insights"
    leftovers = [p.name for p in parent.iterdir() if p.name.startswith(".")]
    assert leftovers == []


# --- write: error paths ---


def test_write_unknown_kind_raises(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    with pytest.raises(ValueError, match="Unknown kind"):
        wp.write("cont.bogus", "x", {"project": "p"}, "b")


def test_write_missing_project_raises(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    with pytest.raises(ValueError, match="project"):
        wp.write("cont.insight", "x", {}, "b")


# --- exists ---


def test_exists_false_when_absent(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    assert wp.exists("cont.insight", "nope") is False


def test_exists_true_after_write(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write("cont.insight", "yep", {"project": "test-project"}, "b")
    assert wp.exists("cont.insight", "yep") is True


def test_exists_finds_across_projects(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write("cont.insight", "shared", {"project": "test-project"}, "b")
    # exists() searches all project subtrees
    assert wp.exists("cont.insight", "shared") is True


def test_exists_unknown_kind_raises(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    with pytest.raises(ValueError, match="Unknown kind"):
        wp.exists("cont.bogus", "x")


def test_exists_no_projects_root(tmp_path):
    """Vault without 10-projects/ returns False rather than crashing."""
    wp = VaultWriteProvider(vault_path=tmp_path)
    assert wp.exists("cont.insight", "x") is False
