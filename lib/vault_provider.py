"""Vault read provider — knows the Obsidian PARA layout.

Pure read operations. No writes. No state. Each call reads files
directly from the configured vault path.
"""

import os
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from project_registry import (  # noqa: E402
    project_dirs as _project_dirs,
    resolve as _resolve_project,
    resolve_from_path as _resolve_from_path,
)


class VaultProvider:
    """Read provider for an Obsidian vault organized in PARA layout.

    Capabilities:
    - List projects (directory names under 10-projects/)
    - Read narrative.md sections (split on H2 headings, returned newest-first)
    - Read decision files (under <project>/decisions/)
    - Read journal entries (daily files under journal/)

    Vault path resolution order:
    1. `vault_path` constructor argument (if provided)
    2. CONTINUITY_VAULT_DIR environment variable
    3. VAULT_DIR environment variable
    4. ValueError if none of the above
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

    def list_projects(self) -> list[str]:
        """Return sorted directory names under 10-projects/."""
        projects_dir = self.vault_path / "10-projects"
        if not projects_dir.is_dir():
            return []
        return sorted(p.name for p in projects_dir.iterdir() if p.is_dir())

    def project_exists(self, project: str) -> bool:
        """Return True if 10-projects/<project>/ exists, case-insensitively."""
        return self.resolve_project(project) is not None

    def resolve_project(self, project: str) -> Optional[str]:
        """Return the canonical project name for a user-supplied name or path.

        A name, not a directory — callers use it for display and as the memory
        subject, both of which want ``apollo`` rather than ``LOGOS/apollo``. Use
        ``resolve_project_dir`` to build a path.
        """
        rel = _resolve_project(project, self.vault_path)
        return rel.rsplit("/", 1)[-1] if rel else None

    def project_dirs(self) -> dict[str, str]:
        """Project name to vault-relative directory. See project_registry."""
        return _project_dirs(self.vault_path)

    def resolve_project_dir(self, project: str) -> Optional[str]:
        """Vault-relative directory for a project name or path.

        The name alone cannot express nesting, so anything building a path —
        narrative, decisions, the capture request — needs this rather than
        ``resolve_project``.
        """
        return _resolve_project(project, self.vault_path)

    def resolve_project_from_path(self, path) -> Optional[tuple[str, str]]:
        """Project owning a filesystem path. See project_registry."""
        return _resolve_from_path(path, self.vault_path)

    def get_narrative_sections(self, project: str, last_n: int = 3) -> list[dict]:
        """Read the last N H2 sections from <project>/narrative.md.

        Returns dicts with `heading` and `body` keys, newest-first
        (assumes the narrative is appended chronologically).
        Empty list if narrative.md doesn't exist or has no H2 sections.
        """
        rel = self.resolve_project_dir(project)
        if rel is None:
            return []
        narrative = self.vault_path / rel / "narrative.md"
        if not narrative.is_file():
            return []
        content = narrative.read_text()
        # Split on H2 headings — re.split keeps the captured groups,
        # so result is [preamble, heading1, body1, heading2, body2, ...]
        parts = re.split(r"^##\s+(.+?)\s*$", content, flags=re.MULTILINE)
        if len(parts) < 3:
            return []
        sections = []
        for i in range(1, len(parts) - 1, 2):
            heading = parts[i].strip()
            body = parts[i + 1].strip()
            sections.append({"heading": heading, "body": body})
        # Newest is last (append-only convention); reverse and take last_n
        return sections[-last_n:][::-1]

    def get_decisions(
        self, project: str, since: Optional[str] = None
    ) -> list[dict]:
        """Read decision files for a project.

        Returns dicts with `date`, `slug`, `path`, `content` keys,
        sorted newest-first by filename date.
        Files matching `YYYY-MM-DD-<slug>.md` only; other files ignored.
        If `since` (YYYY-MM-DD) is given, returns only decisions on or after.
        """
        rel = self.resolve_project_dir(project)
        if rel is None:
            return []
        decisions_dir = self.vault_path / rel / "decisions"
        if not decisions_dir.is_dir():
            return []
        result = []
        for f in sorted(decisions_dir.glob("*.md"), reverse=True):
            m = re.match(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$", f.name)
            if not m:
                continue
            date, slug = m.groups()
            if since and date < since:
                continue
            result.append(
                {
                    "date": date,
                    "slug": slug,
                    "path": str(f.relative_to(self.vault_path)),
                    "content": f.read_text(),
                }
            )
        return result

    def get_journal_entries(self, days_back: int = 3) -> list[dict]:
        """Return the most recent N daily journal entries.

        Daily files match `YYYY-MM-DD.md` exactly. Weekly files
        (`week-*.md`) are skipped.
        """
        journal_dir = self.vault_path / "journal"
        if not journal_dir.is_dir():
            return []
        result = []
        for f in sorted(journal_dir.glob("[0-9]*.md"), reverse=True):
            if not re.match(r"^\d{4}-\d{2}-\d{2}\.md$", f.name):
                continue
            result.append(
                {
                    "date": f.stem,
                    "path": str(f.relative_to(self.vault_path)),
                    "content": f.read_text(),
                }
            )
            if len(result) >= days_back:
                break
        return result
