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
from project_registry import resolve as _resolve_project  # noqa: E402
from write_provider import WriteProvider  # noqa: E402


_KIND_TO_SUBDIR = {
    "cont.insight": "insights",
    "cont.decision": "decisions",
}

_PROMOTION_KIND = "cont.promotion"
_PROMOTION_SUBDIR = "promotions"

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



def validate_relpath(value: str, label: str) -> None:
    """Validate a vault-relative path one segment at a time.

    A project may be nested (``LOGOS/apollo``), so a single-basename check is
    too strict — but the traversal risk is unchanged, since the value still
    reaches path construction. Validating segment-wise keeps both: this is the
    pattern ``_resolve_promotion`` already applies to ``scope``.
    """
    if not value:
        raise ValueError(f"Invalid {label}: {value!r}")
    for segment in value.split("/"):
        validate_basename(segment, label)


class VaultWriteProvider(WriteProvider):
    """Write artifacts to an Obsidian PARA-organized vault.

    Path mapping (each requires ``project`` in frontmatter):
    - ``cont.insight``  → ``<vault>/<project dir>/insights/<id>.md``
    - ``cont.decision`` → ``<vault>/<project dir>/decisions/<id>.md``

    ``<project dir>`` is resolved through ``project_registry``, so a nested
    sub-project (``10-projects/LOGOS/apollo``) is addressable by name.

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
        if kind == _PROMOTION_KIND:
            target = self._resolve_promotion(id, str(frontmatter.get("scope", "")))
        else:
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
        if kind == _PROMOTION_KIND:
            validate_basename(id, "id")
            return any((d / f"{id}.md").exists() for d in self.vault_path.rglob(_PROMOTION_SUBDIR) if d.is_dir())
        if kind not in _KIND_TO_SUBDIR:
            raise ValueError(f"Unknown kind: {kind!r}")
        validate_basename(id, "id")
        subdir = _KIND_TO_SUBDIR[kind]
        projects_root = self.vault_path / "10-projects"
        if not projects_root.is_dir():
            return False
        # Project not knowable from (kind, id) alone — scan project subtrees.
        return any((d / f"{id}.md").exists() for d in projects_root.glob(f"*/{subdir}") if d.is_dir())

    def _resolve(self, kind: str, id: str, project: str) -> Path:
        if kind not in _KIND_TO_SUBDIR:
            raise ValueError(f"Unknown kind: {kind!r}")
        # Reject path-traversal attempts before anything reads the value:
        # "../../etc" or an absolute path would otherwise escape the vault root
        # via pathlib's `/` semantics. This runs FIRST because resolution below
        # answers None for a hostile path and an unknown one alike, and only one
        # of those may reach the create-a-new-project fallback.
        validate_relpath(project, "project")
        validate_basename(id, "id")
        subdir = _KIND_TO_SUBDIR[kind]
        rel = _resolve_project(project, self.vault_path)
        if rel is None:
            # An unknown BASENAME is not an error: writing to a name the vault
            # has never seen is how a new top-level project starts. An unknown
            # PATH is, because a nested project is only distinguishable from an
            # artifact directory by the narrative it carries — inventing one
            # would write into `LOGOS/decisions` as readily as `LOGOS/apollo`.
            if "/" in project:
                raise ValueError(
                    f"{project!r} is not a known project. A nested project must "
                    f"already exist (carry a narrative.md); only a top-level "
                    f"project is created by writing to it."
                )
            rel = f"10-projects/{project}"
        return self.vault_path / rel / subdir / f"{id}.md"


    def _resolve_promotion(self, id: str, scope: str) -> Path:
        validate_basename(id, "id")
        base = self.vault_path
        if scope:
            for seg in scope.split("/"):
                validate_basename(seg, "scope segment")
                base = base / seg
        return base / _PROMOTION_SUBDIR / f"{id}.md"
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
