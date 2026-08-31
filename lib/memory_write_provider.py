"""Memory write provider — CLI-backed adapter over the memory v1 plugin.

Continuity writes second-order artifacts. Memory v1 stores four typed
entry classes, so this provider maps continuity kinds deliberately and
records provenance in the body rather than pretending synthesis is raw
observation.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).parent))
from vault_write_provider import validate_basename, validate_relpath  # noqa: E402
from write_provider import WriteProvider  # noqa: E402


_DEFAULT_MEMORY_BIN = Path.home() / ".claude" / "plugins" / "memory" / "bin" / "memory"
_DEFAULT_TIMEOUT_SECONDS = 10.0
_KIND_TO_MEMORY_TYPE = {
    "cont.insight": "project",
}


class MemoryWriteProvider(WriteProvider):
    """Write continuity artifacts through the memory plugin CLI."""

    def __init__(
        self,
        memory_bin: Optional[str | Path] = None,
        env: Optional[dict[str, str]] = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if memory_bin is None:
            env_bin = os.environ.get("MEMORY_BIN")
            memory_bin = Path(env_bin) if env_bin else _DEFAULT_MEMORY_BIN
        self.memory_bin = Path(memory_bin)
        self.env = env
        self.timeout_seconds = timeout_seconds

    def write(
        self,
        kind: str,
        id: str,
        frontmatter: dict[str, Any],
        body: str,
    ) -> None:
        mapped = _map_to_memory(kind, id, frontmatter)
        rendered = _render_body(kind, id, body)
        cmd = [
            str(self.memory_bin),
            "write",
            "--type",
            mapped["type"],
            "--name",
            mapped["name"],
            "--subject",
            mapped["subject"],
            "--description",
            mapped["description"],
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                env=self._subprocess_env(),
                input=rendered,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"memory write timed out after {self.timeout_seconds:.1f} seconds"
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"memory write failed to start: {exc}") from exc

        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            message = f"memory write failed with exit code {result.returncode}"
            if detail:
                message += f": {detail}"
            raise RuntimeError(message)

    def exists(self, kind: str, id: str) -> bool:
        memory_type = _memory_type_for_kind(kind)
        validate_basename(id, "id")
        cmd = [
            str(self.memory_bin),
            "get",
            "--name",
            id,
            "--type",
            memory_type,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                env=self._subprocess_env(),
                text=True,
                timeout=self.timeout_seconds,
            )
        except (subprocess.SubprocessError, OSError):
            return False
        return result.returncode == 0

    def _subprocess_env(self) -> dict[str, str]:
        env = dict(os.environ if self.env is None else self.env)
        if "MEMORY_VAULT_DIR" not in env:
            vault_dir = env.get("CONTINUITY_VAULT_DIR") or env.get("VAULT_DIR")
            if vault_dir:
                env["MEMORY_VAULT_DIR"] = vault_dir
        return env


def _map_to_memory(kind: str, id: str, frontmatter: dict[str, Any]) -> dict[str, str]:
    memory_type = _memory_type_for_kind(kind)
    validate_basename(id, "id")

    project = str(frontmatter.get("project") or "").strip()
    if not project:
        raise ValueError(
            f"MemoryWriteProvider requires 'project' in frontmatter for kind {kind!r}"
        )
    # memory addresses an entity by NAME and resolves nesting itself, so a
    # nested project's subject is its leaf ("apollo"), never the vault-relative
    # path ("LOGOS/apollo") — memory would take that for an unresolvable
    # subject and refuse the write.
    validate_relpath(project, "project")
    subject = project.rsplit("/", 1)[-1]

    title = _collapse_spaces(str(frontmatter.get("title") or id))
    return {
        "type": memory_type,
        "subject": subject,
        "name": id,
        "description": f"Second-order continuity insight: {title}",
    }


def _memory_type_for_kind(kind: str) -> str:
    try:
        return _KIND_TO_MEMORY_TYPE[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown kind: {kind!r}") from exc


def _render_body(kind: str, id: str, body: str) -> str:
    body_norm = body.rstrip() + "\n"
    return f"Source: continuity\nKind: {kind}\nId: {id}\n\n{body_norm}"


def _collapse_spaces(value: str) -> str:
    return " ".join(value.split())
