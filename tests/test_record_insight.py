"""Tests for record_insight composer + CLI integration."""

import io
from datetime import date
from pathlib import Path

import pytest

import cli
from record_insight import _slug, record_insight
from vault_write_provider import VaultWriteProvider


# --- slug ---


def test_slug_basic():
    assert _slug("Hello World") == "hello-world"


def test_slug_collapses_punctuation():
    assert _slug("It's complicated, sort of!") == "it-s-complicated-sort-of"


def test_slug_unicode_collapses_to_dashes():
    # Non-ASCII chars are non-alphanumeric in our regex → collapsed to dashes
    assert _slug("café déjà vu") == "caf-d-j-vu"


def test_slug_empty_raises():
    with pytest.raises(ValueError, match="empty slug"):
        _slug("!!!")


# --- record_insight ---


def test_record_insight_writes_file(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    ref = record_insight(
        project="test-project",
        title="A Useful Lesson",
        body="The body.",
        provider=wp,
        today=date(2026, 5, 9),
    )
    assert ref == "cont.insight:2026-05-09-a-useful-lesson"
    target = (
        fake_vault
        / "10-projects"
        / "test-project"
        / "insights"
        / "2026-05-09-a-useful-lesson.md"
    )
    assert target.is_file()
    text = target.read_text()
    assert "title: A Useful Lesson" in text
    assert "type: insight" in text
    assert "project: test-project" in text
    assert "The body." in text


def test_record_insight_validates_inputs(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    with pytest.raises(ValueError, match="project"):
        record_insight(project="", title="t", body="b", provider=wp)
    with pytest.raises(ValueError, match="title"):
        record_insight(project="p", title="   ", body="b", provider=wp)
    with pytest.raises(ValueError, match="body"):
        record_insight(project="p", title="t", body="", provider=wp)


# --- CLI integration ---


def test_cli_record_insight(fake_vault, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CONTINUITY_VAULT_DIR", str(fake_vault))
    monkeypatch.setenv("CONTINUITY_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(
        "sys.argv",
        ["continuity", "record-insight", "--project", "test-project", "--title", "Cli Path"],
    )
    monkeypatch.setattr("sys.stdin", io.StringIO("Body via stdin.\n"))
    rc = cli.main()
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("cont.insight:")
    target_dir = fake_vault / "10-projects" / "test-project" / "insights"
    written = list(target_dir.glob("*-cli-path.md"))
    assert len(written) == 1
    text = written[0].read_text()
    assert "Body via stdin." in text
