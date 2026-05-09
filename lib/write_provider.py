"""Write provider — abstract write surface for continuity-managed artifacts.

Symmetric counterpart to read providers. A `WriteProvider` translates
a continuity-namespaced `kind` (e.g. ``cont.insight``) plus an id,
frontmatter dict, and markdown body into a write on whatever
substrate the implementation knows about.

The 2026-05-08 cross-plugin (reader, writer) architecture promotes
this pattern across plugins; for now it lives in continuity. Multiple
implementations are expected (vault, memory-plugin, fixture for tests).
"""

from abc import ABC, abstractmethod
from typing import Any


class WriteProvider(ABC):
    """Abstract write surface.

    Implementations know how to materialize an artifact of `kind` to
    a target substrate. Callers (continuity composer, CLI subcommands,
    MCP tools) do not know or care where the bytes land.
    """

    @abstractmethod
    def write(
        self,
        kind: str,
        id: str,
        frontmatter: dict[str, Any],
        body: str,
    ) -> None:
        """Write an artifact to the target substrate.

        Args:
            kind: continuity-namespaced artifact type, e.g.
                ``"cont.insight"`` or ``"cont.decision"``. The
                implementation maps this to a concrete location.
            id: filename-safe identifier within `kind`.
            frontmatter: YAML-serializable dict; rendered as a
                frontmatter block ahead of the body.
            body: markdown body, written verbatim after the frontmatter.

        Implementations must be atomic (no partially-written file is
        ever observable on the substrate) and idempotent for identical
        inputs (re-running a write with the same arguments leaves the
        substrate in the same state).
        """

    @abstractmethod
    def exists(self, kind: str, id: str) -> bool:
        """Return True if an artifact at (kind, id) is already present."""
