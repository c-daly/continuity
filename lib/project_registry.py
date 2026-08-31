"""The single answer to "what projects exist in the vault, and where".

The vault nests sub-projects — ``10-projects/LOGOS/apollo/`` carries its own
narrative and decisions — so a project is not always a direct child of
``10-projects/``. Every consumer that maps a name or a filesystem path to a
project directory needs the same answer: the read provider, the write provider,
session capture, and synthesis scope resolution. When each answered separately
they disagreed, and the disagreements were silent — an insight filed in one
directory while the narrative it named lived in another.

Answers are vault-relative directories (``10-projects/LOGOS/apollo``), never
bare names, because a bare name cannot express nesting.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

_PROJECTS_ROOT = "10-projects"
_NARRATIVE = "narrative.md"


def _all_projects(vault_path: Path) -> list[tuple[str, str]]:
    """Every project as ``(name, vault-relative dir)``, uncollapsed.

    A project is a non-hidden direct child of ``10-projects/``, or a nested
    directory carrying its own ``narrative.md``. Artifact directories
    (``decisions/``, ``plans/``, ``insights/``, ``.memory/``) are neither, so
    they never shadow a project. Direct children come first, so callers that
    keep the first entry per name give them precedence.

    Names repeat here — two nested projects may share a leaf name — which is
    exactly what ``project_dirs`` cannot represent and ``resolve`` must detect.
    """
    root = Path(vault_path) / _PROJECTS_ROOT
    if not root.is_dir():
        return []

    direct = [
        (c.name, c.relative_to(vault_path).as_posix())
        for c in sorted(root.iterdir())
        # Dot-directories are tooling, not projects: the vault keeps
        # 10-projects/.memory, and treating it as a project makes the memory
        # store an address a stray write can land in.
        if c.is_dir() and not c.name.startswith(".")
    ]
    nested = [
        (c.name, c.relative_to(vault_path).as_posix())
        for c in sorted(root.rglob("*"))
        if c.is_dir() and (c / _NARRATIVE).is_file()
    ]
    seen = {rel for _, rel in direct}
    return direct + [(n, rel) for n, rel in nested if rel not in seen]


def project_dirs(vault_path: Path) -> dict[str, str]:
    """Map project name to its vault-relative directory.

    A direct child of ``10-projects/`` wins over a nested directory of the same
    name; among nested projects sharing a name, the first in sorted order wins.
    Use ``resolve`` when that collapse would matter — it refuses to guess.
    """
    found: dict[str, str] = {}
    for name, rel in _all_projects(Path(vault_path)):
        found.setdefault(name, rel)
    return found


def _is_safe_relpath(project: str) -> bool:
    """`project` reaches filesystem path construction in the write provider, so
    reject anything that could climb out of the projects root."""
    if not project or project.startswith("/"):
        return False
    segments = project.split("/")
    return all(seg and seg not in (".", "..") for seg in segments)


def resolve(project: str, vault_path: Path) -> Optional[str]:
    """Resolve a project name or vault-relative path to its directory.

    Resolution order, most specific claim first:

    1. a direct child of ``10-projects/`` (case-insensitive)
    2. an explicit path under ``10-projects/`` (``LOGOS/logos``)
    3. a nested leaf name that is unique (``apollo``)

    A bare name always means the top-level project, so no existing caller
    silently retargets when a nested project starts sharing its name — the
    explicit path stays available to reach the shadowed one.

    Returns None for an unknown project rather than raising: writing to a name
    the vault has never seen is how a new project starts. Raises only when a
    name is genuinely ambiguous, where guessing would file the artifact in one
    of two real projects and be plausible enough to go unnoticed.
    """
    if not _is_safe_relpath(project):
        return None
    vault_path = Path(vault_path)
    projects = _all_projects(vault_path)

    target = project.casefold()
    for name, rel in projects:
        if name.casefold() == target and rel == f"{_PROJECTS_ROOT}/{name}":
            return rel

    if "/" in project:
        # Must name a registered project, not merely an existing directory:
        # `LOGOS/decisions` is a real path but an artifact tree, and accepting
        # it would file an insight inside another project's decisions.
        rel = f"{_PROJECTS_ROOT}/{project}"
        return rel if any(r == rel for _, r in projects) else None

    nested = sorted({rel for name, rel in projects if name.casefold() == target})
    if len(nested) == 1:
        return nested[0]
    if len(nested) > 1:
        listed = "\n  ".join(nested)
        raise ValueError(
            f"Project {project!r} is ambiguous — it names several projects:\n"
            f"  {listed}\n"
            f"Pass the vault-relative path to pick one."
        )
    return None


def _work_root(path: Path) -> Optional[Path]:
    """Nearest ancestor of ``path`` (itself included) holding a ``.git``.

    ``.git`` is a file, not a directory, inside a linked worktree or a
    submodule, so this tests existence rather than directory-ness.
    """
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def resolve_from_path(path, vault_path: Path) -> Optional[tuple[str, str]]:
    """Resolve a filesystem path to the project it sits in.

    Only two directories on a path carry identity: **the one you are in**, and
    **the root of the checkout you are in**. A session's cwd is routinely a
    subdirectory (``.../vault-cli/src``) whose basename names no project, so the
    checkout root has to be consulted too.

    Everything between and above them is rejected, because a directory that
    merely shares a name with a project is coincidence: ``memory``, ``harness``
    and ``LOGOS`` all make plausible generic directory names, and
    ``/tmp/LOGOS/scratch`` is not LOGOS. Walking every ancestor would also
    collapse under a ``.git`` high in the tree — a dotfiles repo at ``~`` makes
    the whole home directory one "work tree" — which is exactly where the
    coincidences are densest.

    The cwd is checked first, so a sub-project beats its parent checkout.
    Returns ``(name, vault-relative directory)``, or None when neither matches:
    attributing to a real but wrong project is worse than answering nothing,
    being plausible enough to be acted on.
    """
    if not path:
        return None
    vault_path = Path(vault_path)
    lookup: dict[str, tuple[str, str]] = {}
    for name, rel in _all_projects(vault_path):
        # First writer wins, preserving project_dirs' direct-child precedence.
        lookup.setdefault(name.casefold(), (name, rel))

    cwd = Path(path)
    for candidate in (cwd, _work_root(cwd)):
        if candidate is None:
            continue
        match = lookup.get(candidate.name.casefold())
        if match is not None:
            return match
    return None
