"""Tests for record_insight composer + CLI integration."""

import io
from datetime import date

import pytest

import cli
from memory_write_provider import MemoryWriteProvider
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


def test_cli_record_insight_with_memory_provider(tmp_path, monkeypatch, capsys):
    args_file = tmp_path / "memory-args.txt"
    stdin_file = tmp_path / "memory-stdin.md"
    memory_bin = tmp_path / "memory"
    memory_bin.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$@\" > '{args_file}'\n"
        f"cat > '{stdin_file}'\n"
    )
    memory_bin.chmod(0o755)
    (tmp_path / "config.yaml").write_text("write_provider: memory\n")

    monkeypatch.setenv("CONTINUITY_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MEMORY_BIN", str(memory_bin))
    monkeypatch.setattr(
        "sys.argv",
        [
            "continuity",
            "record-insight",
            "--project",
            "constellation",
            "--title",
            "Memory Path",
        ],
    )
    monkeypatch.setattr("sys.stdin", io.StringIO("Body via memory provider.\n"))

    rc = cli.main()

    assert rc == 0
    assert capsys.readouterr().out.strip().startswith("cont.insight:")
    args = args_file.read_text().splitlines()
    assert args[:7] == [
        "write",
        "--type",
        "project",
        "--name",
        args[4],
        "--subject",
        "constellation",
    ]
    assert args[-1] == "Second-order continuity insight: Memory Path"
    assert "Source: continuity" in stdin_file.read_text()
    assert "Body via memory provider." in stdin_file.read_text()


def test_cli_record_insight_reports_memory_provider_errors(tmp_path, monkeypatch, capsys):
    memory_bin = tmp_path / "memory"
    memory_bin.write_text(
        "#!/bin/sh\n"
        "echo 'memory entry already exists at <project:x>' >&2\n"
        "exit 1\n"
    )
    memory_bin.chmod(0o755)
    (tmp_path / "config.yaml").write_text("write_provider: memory\n")

    monkeypatch.setenv("CONTINUITY_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MEMORY_BIN", str(memory_bin))
    monkeypatch.setattr(
        "sys.argv",
        [
            "continuity",
            "record-insight",
            "--project",
            "constellation",
            "--title",
            "Collision Path",
        ],
    )
    monkeypatch.setattr("sys.stdin", io.StringIO("Body.\n"))

    rc = cli.main()

    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "error: memory write failed with exit code 1" in captured.err
    assert "memory entry already exists" in captured.err
    assert "Traceback" not in captured.err


def test_record_insight_vault_and_memory_semantic_parity(fake_vault, tmp_path):
    memory_args = tmp_path / "memory-args.txt"
    memory_body = tmp_path / "memory-body.md"
    memory_bin = tmp_path / "memory"
    memory_bin.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$@\" > '{memory_args}'\n"
        f"cat > '{memory_body}'\n"
    )
    memory_bin.chmod(0o755)
    today = date(2026, 5, 9)
    title = "A Useful Lesson"
    body = "The body."

    vault_ref = record_insight(
        project="test-project",
        title=title,
        body=body,
        provider=VaultWriteProvider(vault_path=fake_vault),
        today=today,
    )
    memory_ref = record_insight(
        project="test-project",
        title=title,
        body=body,
        provider=MemoryWriteProvider(memory_bin=memory_bin),
        today=today,
    )

    assert memory_ref == vault_ref
    _, insight_id = memory_ref.split(":", 1)
    vault_text = (
        fake_vault
        / "10-projects"
        / "test-project"
        / "insights"
        / f"{insight_id}.md"
    ).read_text()
    args = memory_args.read_text().splitlines()
    assert "project: test-project" in vault_text
    assert "title: A Useful Lesson" in vault_text
    assert "type: insight" in vault_text
    assert args == [
        "write",
        "--type",
        "project",
        "--name",
        insight_id,
        "--subject",
        "test-project",
        "--description",
        "Second-order continuity insight: A Useful Lesson",
    ]
    assert "Kind: cont.insight" in memory_body.read_text()
    assert f"Id: {insight_id}" in memory_body.read_text()
    assert body in memory_body.read_text()


def test_record_insight_rejects_traversal_in_project(fake_vault):
    """`nested/path` is gone from this list on purpose — a project may be nested
    now, so validation is segment-wise rather than separator-forbidding."""
    wp = VaultWriteProvider(vault_path=fake_vault)
    for bad in ["..", "../escape", "/abs/path", "LOGOS/../../etc", "a//b"]:
        with pytest.raises(ValueError, match="Invalid project name"):
            record_insight(project=bad, title="t", body="b", provider=wp)


def test_record_insight_into_a_nested_subproject(fake_vault):
    """record_insight validated a single basename, so a nested project was
    rejected before the writer ever saw it."""
    sub = fake_vault / "10-projects" / "LOGOS" / "apollo"
    sub.mkdir(parents=True)
    (sub / "narrative.md").write_text("# apollo\n")
    provider = VaultWriteProvider(vault_path=fake_vault)

    ref = record_insight(
        project="apollo", title="A Thing", body="b",
        provider=provider, today=date(2026, 8, 31),
    )

    assert ref == "cont.insight:2026-08-31-a-thing"
    assert (sub / "insights" / "2026-08-31-a-thing.md").is_file()


def test_record_insight_still_rejects_traversal(fake_vault):
    provider = VaultWriteProvider(vault_path=fake_vault)
    for hostile in ("../../etc", "/etc", "LOGOS/../../../etc"):
        with pytest.raises(ValueError):
            record_insight(project=hostile, title="t", body="b", provider=provider)
