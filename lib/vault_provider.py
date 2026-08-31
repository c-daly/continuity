"""Vault read provider — knows the Obsidian PARA layout.

Pure read operations. No writes. No state. Each call reads files
directly from the configured vault path.
"""

import os
import re
from pathlib import Path
from typing import Optional


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
        """Return the canonical project directory name for a user-supplied name."""
        projects_dir = self.vault_path / "10-projects"
        exact = projects_dir / project
        if exact.is_dir():
            return exact.name

        if not projects_dir.is_dir():
            return None

        target = project.casefold()
        for candidate in projects_dir.iterdir():
            if candidate.is_dir() and candidate.name.casefold() == target:
                return candidate.name
        return None

    def project_dirs(self) -> dict[str, str]:
        """Map project name to its vault-relative directory.

        A project is a direct child of ``10-projects/``, or a nested directory
        carrying its own ``narrative.md`` — the vault nests sub-projects
        (``10-projects/LOGOS/apollo/``) and each has a narrative of its own.
        Artifact directories (``decisions/``, ``plans/``, ``insights/``,
        ``.memory/``) are neither, so they never shadow a project.

        A direct child wins over a nested directory of the same name.
        """
        projects_dir = self.vault_path / "10-projects"
        if not projects_dir.is_dir():
            return {}

        found: dict[str, str] = {}
        for child in sorted(projects_dir.iterdir()):
            if child.is_dir():
                found.setdefault(child.name, child.relative_to(self.vault_path).as_posix())
        for cand in sorted(projects_dir.rglob("*")):
            if cand.is_dir() and (cand / "narrative.md").is_file():
                found.setdefault(cand.name, cand.relative_to(self.vault_path).as_posix())
        return found

    @staticmethod
    def _work_root(path: Path) -> Optional[Path]:
        """Nearest ancestor of ``path`` (itself included) holding a ``.git``.

        ``.git`` is a file, not a directory, inside a linked worktree or a
        submodule, so this tests existence rather than directory-ness.
        """
        for candidate in (path, *path.parents):
            if (candidate / ".git").exists():
                return candidate
        return None

    def resolve_project_from_path(self, path) -> Optional[tuple[str, str]]:
        """Resolve a filesystem path to the project it sits in.

        Only two directories on the path carry identity: **the one you are in**,
        and **the root of the checkout you are in**. A session's cwd is not
        reliably the project directory — it is routinely a subdirectory
        (``.../vault-cli/src``) whose basename names no project at all — so the
        checkout root has to be consulted too.

        Everything between and above them is rejected, because a directory that
        merely shares a name with a project is coincidence: ``memory``,
        ``harness`` and ``LOGOS`` all make plausible generic directory names, and
        ``/tmp/LOGOS/scratch`` is not LOGOS. Walking every ancestor would also
        collapse under a ``.git`` high in the tree — a dotfiles repo at ``~``
        makes the whole home directory one "work tree" — which is exactly when
        the coincidences multiply.

        Returns ``(canonical name, vault-relative directory)``, or None when
        neither matches: attributing to a real but wrong project is worse than
        answering nothing, being plausible enough to be acted on.

        The answer is always an **addressable** project — a direct child of
        ``10-projects/``. Sub-project directories are recognised, so a session
        in ``LOGOS/apollo`` is attributed rather than lost, but the answer is
        the top-level project owning them. Callers write through providers that
        address a project by a single basename, so returning ``apollo`` would
        file the insight in a fresh flat ``10-projects/apollo/`` while the
        narrative it names lives under ``LOGOS/`` — one session split across two
        trees, one of them invented. Addressing sub-projects end to end needs
        the write path to take a nested project first.
        """
        if not path:
            return None
        lookup: dict[str, tuple[str, str]] = {}
        for name, rel in self.project_dirs().items():
            segments = rel.split("/")
            # Collapse to the top-level project: <projects-root>/<name>.
            top = (segments[1], "/".join(segments[:2]))
            # First writer wins, preserving project_dirs' direct-child precedence.
            lookup.setdefault(name.casefold(), top)

        cwd = Path(path)
        root = self._work_root(cwd)
        for candidate in (cwd, root):
            if candidate is None:
                continue
            match = lookup.get(candidate.name.casefold())
            if match is not None:
                return match
        return None

    def get_narrative_sections(self, project: str, last_n: int = 3) -> list[dict]:
        """Read the last N H2 sections from <project>/narrative.md.

        Returns dicts with `heading` and `body` keys, newest-first
        (assumes the narrative is appended chronologically).
        Empty list if narrative.md doesn't exist or has no H2 sections.
        """
        narrative = self.vault_path / "10-projects" / project / "narrative.md"
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
        decisions_dir = self.vault_path / "10-projects" / project / "decisions"
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
