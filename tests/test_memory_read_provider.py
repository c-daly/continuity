"""Tests for memory_read_provider — parser, provider, availability."""

from pathlib import Path

import pytest

from memory_read_provider import (
    MemoryObservation,
    MemoryReadProvider,
    _parse_line,
    _parse_list_output,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "memory_list_sample.txt"


# ----- parser unit tests -----


def test_parse_line_well_formed():
    line = (
        "project:memory-plugin:memory-plugin-mcp-verified-2026-05-13 "
        "— Memory plugin MCP server verified operational on 2026-05-13."
    )
    obs = _parse_line(line)
    assert obs == MemoryObservation(
        type="project",
        subject="memory-plugin",
        name="memory-plugin-mcp-verified-2026-05-13",
        description="Memory plugin MCP server verified operational on 2026-05-13.",
    )


def test_parse_line_without_separator_returns_none():
    assert _parse_line("not a memory line at all") is None


def test_parse_line_missing_colons_returns_none():
    assert _parse_line("type-only — description here") is None


def test_parse_line_empty_field_returns_none():
    # Empty subject between two colons
    assert _parse_line("project::name — description") is None


def test_parse_line_strips_description_whitespace():
    line = "feedback:project:slug —    spaced description   "
    obs = _parse_line(line)
    assert obs is not None
    assert obs.description == "spaced description"


def test_parse_list_output_skips_blanks_and_malformed():
    text = (
        "project:p:n — first\n"
        "\n"
        "malformed line\n"
        "feedback:p:n2 — second\n"
        "   \n"
    )
    observations = _parse_list_output(text)
    assert len(observations) == 2
    assert observations[0].name == "n"
    assert observations[1].type == "feedback"


def test_parse_list_output_handles_fixture_file():
    """Round-trip the captured fixture so format drift surfaces in CI."""
    text = FIXTURE_PATH.read_text()
    observations = _parse_list_output(text)
    assert len(observations) == 5
    types = {o.type for o in observations}
    assert types == {"project", "feedback", "user", "reference"}


# ----- provider behavior tests -----


def test_available_false_when_binary_missing(tmp_path):
    missing = tmp_path / "no-such-memory-binary"
    provider = MemoryReadProvider(memory_bin=missing)
    assert provider.available() is False


def test_available_true_when_binary_responds(tmp_path):
    fake_bin = tmp_path / "fake-memory"
    fake_bin.write_text("#!/bin/sh\nexit 0\n")
    fake_bin.chmod(0o755)
    provider = MemoryReadProvider(memory_bin=fake_bin)
    assert provider.available() is True


def test_list_returns_parsed_observations(tmp_path):
    fake_bin = tmp_path / "fake-memory"
    fake_bin.write_text(
        "#!/bin/sh\n"
        "echo 'project:demo:entry-1 — first entry'\n"
        "echo 'feedback:demo:entry-2 — second entry'\n"
    )
    fake_bin.chmod(0o755)
    provider = MemoryReadProvider(memory_bin=fake_bin)
    observations = provider.list()
    assert len(observations) == 2
    assert observations[0].name == "entry-1"
    assert observations[1].type == "feedback"


def test_list_returns_empty_when_binary_missing(tmp_path):
    provider = MemoryReadProvider(memory_bin=tmp_path / "nope")
    assert provider.list() == []


def test_list_returns_empty_when_binary_errors(tmp_path):
    fake_bin = tmp_path / "fake-memory"
    fake_bin.write_text("#!/bin/sh\nexit 2\n")
    fake_bin.chmod(0o755)
    provider = MemoryReadProvider(memory_bin=fake_bin)
    assert provider.list() == []


def test_list_passes_filter_arguments(tmp_path):
    """Verify --type and --subject get forwarded; echo back via fake CLI."""
    fake_bin = tmp_path / "fake-memory"
    # Fake CLI prints its args one per line as a fake "observation," so the
    # parser will reject them and the test just confirms invocation shape.
    capture = tmp_path / "captured-args.txt"
    fake_bin.write_text(
        "#!/bin/sh\n"
        f"echo \"$@\" > {capture}\n"
        "echo 'project:demo:entry — body'\n"
    )
    fake_bin.chmod(0o755)
    provider = MemoryReadProvider(memory_bin=fake_bin)
    provider.list(type="feedback", subject="demo")
    args = capture.read_text().strip().split()
    assert args == ["list", "--type", "feedback", "--subject", "demo"]


def test_default_memory_bin_path_used_when_env_unset(monkeypatch):
    monkeypatch.delenv("MEMORY_BIN", raising=False)
    provider = MemoryReadProvider()
    assert provider.memory_bin.name == "memory"
    assert "memory" in str(provider.memory_bin)


def test_env_var_overrides_default(monkeypatch, tmp_path):
    custom = tmp_path / "custom-memory"
    monkeypatch.setenv("MEMORY_BIN", str(custom))
    provider = MemoryReadProvider()
    assert provider.memory_bin == custom
