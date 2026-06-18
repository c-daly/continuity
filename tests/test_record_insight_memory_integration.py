"""End-to-end: record_insight routed through the real memory plugin CLI."""
import os
import subprocess
from pathlib import Path

import pytest
from memory_write_provider import MemoryWriteProvider
from record_insight import record_insight

MEMORY_BIN = Path.home() / ".claude" / "plugins" / "memory" / "bin" / "memory"


def _make_vault_with_entity(root: Path, project: str) -> Path:
    """A temp vault where `project` is a known entity (satisfies audit-#6)."""
    (root / "10-projects" / project).mkdir(parents=True)
    return root


@pytest.mark.skipif(not MEMORY_BIN.is_file(), reason="memory plugin not installed")
def test_record_insight_through_memory_roundtrips(tmp_path):
    vault = _make_vault_with_entity(tmp_path / "vault", "demo-proj")
    env = dict(os.environ, MEMORY_VAULT_DIR=str(vault))
    provider = MemoryWriteProvider(memory_bin=MEMORY_BIN, env=env)

    ref = record_insight(
        "demo-proj", "Bridge smoke test", "Body of the insight.",
        provider=provider,
    )
    assert ref.startswith("cont.insight:")

    # The entry is retrievable through memory's own CLI.
    name = ref.split(":", 1)[1]
    got = subprocess.run(
        [str(MEMORY_BIN), "get", "--name", name, "--type", "project"],
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert got.returncode == 0, got.stderr
    assert "Source: continuity" in got.stdout

    # The entry physically landed in the entity's local .memory/ directory (audit-#6 placement).
    # The memory plugin writes <vault>/10-projects/<subject>/.memory/<date>-<name>.md.
    memdir = vault / "10-projects" / "demo-proj" / ".memory"
    placed = list(memdir.glob("*.md"))
    assert placed, f"no entry written under entity .memory/: {memdir}"
    assert any(name in p.name for p in placed), f"{name} not among {[p.name for p in placed]}"


@pytest.mark.skipif(not MEMORY_BIN.is_file(), reason="memory plugin not installed")
def test_unknown_project_entity_is_rejected(tmp_path):
    """audit-#6: writing for a project that is not a vault entity must fail
    loudly, not write to an inbox fallback."""
    empty_vault = tmp_path / "vault"
    (empty_vault / "10-projects").mkdir(parents=True)
    env = dict(os.environ, MEMORY_VAULT_DIR=str(empty_vault))
    provider = MemoryWriteProvider(memory_bin=MEMORY_BIN, env=env)
    with pytest.raises(RuntimeError):
        record_insight("no-such-entity", "x", "y", provider=provider)
