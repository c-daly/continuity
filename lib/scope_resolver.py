"""Scope resolution for continuity synthesis.

Maps a memory entry's `subject` to its vault-relative entity directory and
computes the least-general (tightest) scope that subsumes a set of subjects,
as the longest common directory prefix. "" denotes the vault root (user
scope). Unlocatable subjects are dropped, never resolved to root.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from project_registry import resolve as _resolve_project  # noqa: E402

_USER_SUBJECTS = {"user"}


def subject_to_relpath(subject: str, vault_path: Path) -> Optional[str]:
    """Locate a subject's entity directory, or None if it has none.

    Resolution goes through ``project_registry`` rather than a bare walk for
    directories of the right name. A raw walk matched anything: a subject named
    ``plans`` or ``decisions`` resolved to some project's artifact directory,
    and a promotion scoped there is filed inside another project's content.
    """
    if subject in _USER_SUBJECTS:
        return ""
    try:
        return _resolve_project(subject, vault_path)
    except ValueError:
        # Ambiguous: several projects share the name. Unlocatable rather than
        # guessed, which resolve_scope already knows how to drop.
        return None


def resolve_scope(subjects: list[str], vault_path: Path) -> Optional[str]:
    paths = []
    for s in subjects:
        rel = subject_to_relpath(s, vault_path)
        if rel is not None:
            paths.append(rel.split("/") if rel else [])
    if not paths:
        return None
    common: list[str] = []
    for parts in zip(*paths):
        if len(set(parts)) == 1:
            common.append(parts[0])
        else:
            break
    return "/".join(common)
