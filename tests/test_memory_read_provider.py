"""Tests for the memory CLI-backed read provider."""

from pathlib import Path

from memory_read_provider import MemoryReadProvider, parse_memory_observation


SAMPLE_LINE = (
    "project:memory-plugin:memory-plugin-mcp-verified-2026-05-13 — "
    "Memory plugin MCP server verified operational on 2026-05-13 via memory_write "
    "from an active Claude Code session."
)


def test_parse_memory_observation_sample_line():
    observation = parse_memory_observation(SAMPLE_LINE)

    assert observation is not None
    assert observation.type == "project"
    assert observation.subject == "memory-plugin"
    assert observation.name == "memory-plugin-mcp-verified-2026-05-13"
    assert observation.description.startswith("Memory plugin MCP server verified")


def test_parse_memory_observation_skips_malformed_lines():
    assert parse_memory_observation("not a memory row") is None
    assert parse_memory_observation("project:missing-description") is None
    assert parse_memory_observation("project::name — description") is None


def test_unavailable_memory_cli_returns_empty(tmp_path):
    provider = MemoryReadProvider(memory_bin=tmp_path / "missing-memory")

    assert provider.available() is False
    assert provider.list(subject="constellation") == []


def test_memory_cli_output_is_parsed(tmp_path):
    memory_bin = _write_executable(
        tmp_path / "memory",
        "#!/bin/sh\n"
        f"echo '{SAMPLE_LINE}'\n"
        "echo 'malformed row without separator'\n",
    )
    provider = MemoryReadProvider(memory_bin=memory_bin)

    observations = provider.list(subject="memory-plugin")

    assert provider.available() is True
    assert len(observations) == 1
    assert observations[0].name == "memory-plugin-mcp-verified-2026-05-13"


def test_memory_cli_filters_are_forwarded(tmp_path):
    args_file = tmp_path / "args.txt"
    memory_bin = _write_executable(
        tmp_path / "memory",
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$@\" > '{args_file}'\n"
        f"echo '{SAMPLE_LINE}'\n",
    )
    provider = MemoryReadProvider(memory_bin=memory_bin)

    provider.list(type="project", subject="memory-plugin")

    assert args_file.read_text().splitlines() == [
        "list",
        "--type",
        "project",
        "--subject",
        "memory-plugin",
    ]


def test_continuity_vault_dir_is_forwarded_to_memory_vault_dir(tmp_path):
    env_file = tmp_path / "env.txt"
    memory_bin = _write_executable(
        tmp_path / "memory",
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$MEMORY_VAULT_DIR\" > '{env_file}'\n"
        f"echo '{SAMPLE_LINE}'\n",
    )
    provider = MemoryReadProvider(
        memory_bin=memory_bin,
        env={"CONTINUITY_VAULT_DIR": "/tmp/test-vault"},
    )

    provider.list(subject="memory-plugin")

    assert env_file.read_text().strip() == "/tmp/test-vault"


def test_existing_memory_vault_dir_is_preserved(tmp_path):
    env_file = tmp_path / "env.txt"
    memory_bin = _write_executable(
        tmp_path / "memory",
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$MEMORY_VAULT_DIR\" > '{env_file}'\n"
        f"echo '{SAMPLE_LINE}'\n",
    )
    provider = MemoryReadProvider(
        memory_bin=memory_bin,
        env={
            "CONTINUITY_VAULT_DIR": "/tmp/continuity-vault",
            "MEMORY_VAULT_DIR": "/tmp/memory-vault",
        },
    )

    provider.list(subject="memory-plugin")

    assert env_file.read_text().strip() == "/tmp/memory-vault"


def test_memory_cli_failure_returns_empty(tmp_path):
    memory_bin = _write_executable(
        tmp_path / "memory",
        "#!/bin/sh\n"
        "echo 'memory unavailable' >&2\n"
        "exit 2\n",
    )
    provider = MemoryReadProvider(memory_bin=memory_bin)

    assert provider.list(subject="constellation") == []


def test_memory_cli_timeout_returns_empty(tmp_path):
    memory_bin = _write_executable(
        tmp_path / "memory",
        "#!/bin/sh\n"
        "sleep 1\n"
        f"echo '{SAMPLE_LINE}'\n",
    )
    provider = MemoryReadProvider(memory_bin=memory_bin, timeout_seconds=0.01)

    assert provider.list(subject="memory-plugin") == []


def _write_executable(path: Path, content: str) -> Path:
    path.write_text(content)
    path.chmod(0o755)
    return path
