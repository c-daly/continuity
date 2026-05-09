"""Memory write provider — stub until the memory plugin lands.

Placeholder implementation of ``WriteProvider`` so configs can already
name ``write_provider: memory`` and get a clear error rather than a
silent fallback. Activated for real in Phase 2.5 once the memory
plugin exposes a write surface.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from write_provider import WriteProvider  # noqa: E402


_NOT_AVAILABLE = (
    "memory plugin not yet available; "
    "set write_provider: vault in config or install the memory plugin"
)


class MemoryWriteProvider(WriteProvider):
    """Stub that raises NotImplementedError on every call."""

    def write(
        self,
        kind: str,
        id: str,
        frontmatter: dict[str, Any],
        body: str,
    ) -> None:
        raise NotImplementedError(_NOT_AVAILABLE)

    def exists(self, kind: str, id: str) -> bool:
        raise NotImplementedError(_NOT_AVAILABLE)
