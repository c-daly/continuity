"""Scope resolution for continuity synthesis.

Maps a memory entry's `subject` to its vault-relative entity directory and
computes the least-general (tightest) scope that subsumes a set of subjects,
as the longest common directory prefix. "" denotes the vault root (user
scope). Unlocatable subjects are dropped, never resolved to root.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

_USER_SUBJECTS = {"user"}


def subject_to_relpath(subject: str, vault_path: Path) -> Optional[str]:
    if subject in _USER_SUBJECTS:
        return ""
    projects = vault_path / "10-projects"
    if not projects.is_dir():
        return None
    # Exact directory named <subject>, searched within 10-projects (may nest).
    for cand in sorted(projects.rglob("*")):
        if cand.is_dir() and cand.name == subject:
            return cand.relative_to(vault_path).as_posix()
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
