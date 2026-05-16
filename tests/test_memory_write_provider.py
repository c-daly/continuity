"""Tests for the memory CLI-backed write provider."""

from pathlib import Path

import pytest

from memory_write_provider import MemoryWriteProvider


def test_write_maps_continuity_insight_to_memory_cli(tmp_path):
    args_file = tmp_path / "args.txt"
    stdin_file = tmp_path / "stdin.md"
    env_file = tmp_path / "env.txt"
    memory_bin = _write_executable(
        tmp_path / "memory",
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$@\" > '{args_file}'\n"
        f"cat > '{stdin_file}'\n"
        f"printf '%s\\n' \"$MEMORY_VAULT_DIR\" > '{env_file}'\n",
    )
    provider = MemoryWriteProvider(
        memory_bin=memory_bin,
        env={"CONTINUITY_VAULT_DIR": "/tmp/test-vault"},
    )

    provider.write(
        "cont.insight",
        "2026-05-16-use-memory-writes",
        {
            "project": "constellation",
            "title": "Use Memory Writes",
        },
        "Continuity should write through memory when configured.\n",
    )

    assert args_file.read_text().splitlines() == [
        "write",
        "--type",
        "project",
        "--name",
        "2026-05-16-use-memory-writes",
        "--subject",
        "constellation",
        "--description",
        "Second-order continuity insight: Use Memory Writes",
    ]
    assert stdin_file.read_text() == (
        "Source: continuity\n"
        "Kind: cont.insight\n"
        "Id: 2026-05-16-use-memory-writes\n"
        "\n"
        "Continuity should write through memory when configured.\n"
    )
    assert env_file.read_text().strip() == "/tmp/test-vault"


def test_write_uses_id_when_title_missing(tmp_path):
    args_file = tmp_path / "args.txt"
    memory_bin = _write_executable(
        tmp_path / "memory",
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$@\" > '{args_file}'\n"
        "cat >/dev/null\n",
    )
    provider = MemoryWriteProvider(memory_bin=memory_bin)

    provider.write("cont.insight", "insight-id", {"project": "p"}, "body")

    assert args_file.read_text().splitlines()[-1] == (
        "Second-order continuity insight: insight-id"
    )


def test_write_failure_raises_clear_error(tmp_path):
    memory_bin = _write_executable(
        tmp_path / "memory",
        "#!/bin/sh\n"
        "echo 'collision' >&2\n"
        "exit 2\n",
    )
    provider = MemoryWriteProvider(memory_bin=memory_bin)

    with pytest.raises(RuntimeError, match="memory write failed.*collision"):
        provider.write("cont.insight", "x", {"project": "p"}, "body")


def test_write_timeout_raises_clear_error(tmp_path):
    memory_bin = _write_executable(
        tmp_path / "memory",
        "#!/bin/sh\n"
        "sleep 1\n",
    )
    provider = MemoryWriteProvider(memory_bin=memory_bin, timeout_seconds=0.01)

    with pytest.raises(RuntimeError, match="timed out"):
        provider.write("cont.insight", "x", {"project": "p"}, "body")


def test_write_validates_kind_project_and_id(tmp_path):
    provider = MemoryWriteProvider(memory_bin=tmp_path / "memory")

    with pytest.raises(ValueError, match="Unknown kind"):
        provider.write("cont.unknown", "x", {"project": "p"}, "body")
    with pytest.raises(ValueError, match="project"):
        provider.write("cont.insight", "x", {}, "body")
    with pytest.raises(ValueError, match="Invalid id"):
        provider.write("cont.insight", "../x", {"project": "p"}, "body")
    with pytest.raises(ValueError, match="Invalid project"):
        provider.write("cont.insight", "x", {"project": "../p"}, "body")


def test_exists_uses_memory_get(tmp_path):
    args_file = tmp_path / "args.txt"
    memory_bin = _write_executable(
        tmp_path / "memory",
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$@\" > '{args_file}'\n"
        "exit 0\n",
    )
    provider = MemoryWriteProvider(memory_bin=memory_bin)

    assert provider.exists("cont.insight", "insight-id") is True
    assert args_file.read_text().splitlines() == [
        "get",
        "--name",
        "insight-id",
        "--type",
        "project",
    ]


def test_exists_returns_false_when_memory_get_misses_or_fails(tmp_path):
    missing_bin = _write_executable(
        tmp_path / "missing-memory",
        "#!/bin/sh\n"
        "exit 1\n",
    )
    provider = MemoryWriteProvider(memory_bin=missing_bin)
    assert provider.exists("cont.insight", "insight-id") is False

    broken_provider = MemoryWriteProvider(memory_bin=tmp_path / "no-such-memory")
    assert broken_provider.exists("cont.insight", "insight-id") is False


def test_existing_memory_vault_dir_is_preserved(tmp_path):
    env_file = tmp_path / "env.txt"
    memory_bin = _write_executable(
        tmp_path / "memory",
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$MEMORY_VAULT_DIR\" > '{env_file}'\n",
    )
    provider = MemoryWriteProvider(
        memory_bin=memory_bin,
        env={
            "CONTINUITY_VAULT_DIR": "/tmp/continuity-vault",
            "MEMORY_VAULT_DIR": "/tmp/memory-vault",
        },
    )

    provider.write("cont.insight", "insight-id", {"project": "p"}, "body")

    assert env_file.read_text().strip() == "/tmp/memory-vault"


def _write_executable(path: Path, content: str) -> Path:
    path.write_text(content)
    path.chmod(0o755)
    return path
