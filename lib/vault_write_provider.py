"""Vault write provider — translates continuity-namespaced kinds into
PARA-organized vault paths.

Symmetric to ``vault_provider.VaultProvider`` (read). Each supported
kind requires ``project`` in frontmatter; the project name selects
the ``10-projects/<project>/`` subtree, and the kind selects the
subdirectory within it.

Per the 2026-05-07 ``vault_writer-stays-continuity-local`` decision,
this implementation is owned by continuity until a second consumer
emerges; promotion to a shared layer happens at Phase 2 entry.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from write_provider import WriteProvider  # noqa: E402


_KIND_TO_SUBDIR = {
    "cont.insight": "insights",
    "cont.decision": "decisions",
}

_FORBIDDEN_BASENAMES = {"", ".", ".."}
_FORBIDDEN_BASENAME_CHARS = ("/", "\\", "\x00")


def validate_basename(name: str, label: str) -> None:
    """Reject anything that isn't a single safe path component.

    The vault writer composes file paths from caller-supplied
    ``project`` and ``id`` values; without this check, traversal
    segments or absolute paths could escape the vault root via
    pathlib's ``/`` semantics. Rejecting backslash too keeps cross-
    machine vault sync (Linux ↔ Windows) safe.
    """
    if name in _FORBIDDEN_BASENAMES or any(
        ch in name for ch in _FORBIDDEN_BASENAME_CHARS
    ):
        raise ValueError(f"Invalid {label}: {name!r}")


class VaultWriteProvider(WriteProvider):
    """Write artifacts to an Obsidian PARA-organized vault.

    Path mapping (each requires ``project`` in frontmatter):
    - ``cont.insight``  → ``<vault>/10-projects/<project>/insights/<id>.md``
    - ``cont.decision`` → ``<vault>/10-projects/<project>/decisions/<id>.md``

    Vault path resolution mirrors ``VaultProvider``:
    1. ``vault_path`` constructor argument
    2. ``CONTINUITY_VAULT_DIR`` environment variable
    3. ``VAULT_DIR`` environment variable
    4. ``ValueError`` if none of the above
    """

    def __init__(self, vault_path: Optional[Path] = None):
        if vault_path is None:
            env_path = (
                os.environ.get("CONTINUITY_VAULT_DIR")
                or os.environ.get("VAULT_DIR")
            )
            if not env_path:
                raise ValueError(
                    "Vault path not provided and neither "
                    "CONTINUITY_VAULT_DIR nor VAULT_DIR is set"
                )
            vault_path = Path(env_path)
        self.vault_path = Path(vault_path)
        if not self.vault_path.is_dir():
            raise ValueError(
                f"Vault path does not exist or is not a directory: {self.vault_path}"
            )

    def write(
        self,
        kind: str,
        id: str,
        frontmatter: dict[str, Any],
        body: str,
    ) -> None:
        project = frontmatter.get("project")
        if not project:
            raise ValueError(
                f"VaultWriteProvider requires 'project' in frontmatter for kind {kind!r}"
            )
        target = self._resolve(kind, id, str(project))
        target.parent.mkdir(parents=True, exist_ok=True)

        rendered = self._render(frontmatter, body)
        # Atomic write: materialize fully in a sibling temp file, then rename.
        # Same-directory rename is atomic on POSIX and on NTFS via os.replace.
        # NamedTemporaryFile owns the descriptor lifecycle even if writing raises.
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{id}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as f:
            f.write(rendered)
            tmp_path = f.name
        try:
            os.replace(tmp_path, target)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise

    def exists(self, kind: str, id: str) -> bool:
        if kind not in _KIND_TO_SUBDIR:
            raise ValueError(f"Unknown kind: {kind!r}")
        validate_basename(id, "id")
        subdir = _KIND_TO_SUBDIR[kind]
        projects_root = self.vault_path / "10-projects"
        if not projects_root.is_dir():
            return False
        # Project not knowable from (kind, id) alone — scan project subtrees.
        return any(projects_root.glob(f"*/{subdir}/{id}.md"))

    def _resolve(self, kind: str, id: str, project: str) -> Path:
        if kind not in _KIND_TO_SUBDIR:
            raise ValueError(f"Unknown kind: {kind!r}")
        # Reject path-traversal attempts: project and id must be plain
        # single-component names. Without this, "../../etc" or absolute paths
        # would escape the vault root via pathlib's `/` semantics.
        validate_basename(project, "project")
        validate_basename(id, "id")
        subdir = _KIND_TO_SUBDIR[kind]
        return self.vault_path / "10-projects" / project / subdir / f"{id}.md"

    @staticmethod
    def _render(frontmatter: dict[str, Any], body: str) -> str:
        fm_yaml = yaml.safe_dump(
            frontmatter,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        ).rstrip()
        body_norm = body.rstrip() + "\n"
        return f"---\n{fm_yaml}\n---\n\n{body_norm}"
