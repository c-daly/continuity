"""Memory read provider — CLI-backed adapter over the memory v1 plugin.

Calls `bin/memory list` from the local memory plugin install and parses the
one-line-per-entry output into `MemoryObservation` records. Designed to be
optional: if the memory plugin or its CLI is unavailable, callers can detect
this via `available()` and degrade gracefully.

Format captured 2026-05-16 from memory v1 (c-daly/memory @ 53da17b) is one
entry per line:

    <type>:<subject>:<name> — <description>

Sample fixtures live at tests/fixtures/memory_list_sample.txt.

If the memory plugin ever adds `--format json` (see constellation plan v2,
T1.0), the parser here should switch to it and drop line parsing. Until
then, malformed lines are skipped with a debug warning rather than failing
the whole list call.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


_DEFAULT_MEMORY_BIN = Path.home() / ".claude" / "plugins" / "memory" / "bin" / "memory"
_SEPARATOR = " — "  # em-dash with surrounding spaces; see module docstring


@dataclass(frozen=True)
class MemoryObservation:
    """A single first-order memory entry as returned by `memory list`."""

    type: str
    subject: str
    name: str
    description: str


class MemoryReadProvider:
    """Read adapter over the memory v1 plugin's `bin/memory list` CLI.

    Memory binary resolution order:
    1. `memory_bin` constructor argument (if provided)
    2. MEMORY_BIN environment variable
    3. ~/.claude/plugins/memory/bin/memory (default install path)

    The provider does not raise on memory unavailability — call sites should
    check `available()` first or accept an empty list from `list()`.
    """

    def __init__(self, memory_bin: Optional[Path] = None):
        if memory_bin is None:
            env_bin = os.environ.get("MEMORY_BIN")
            memory_bin = Path(env_bin) if env_bin else _DEFAULT_MEMORY_BIN
        self.memory_bin = Path(memory_bin)

    def available(self) -> bool:
        """True if the memory binary exists and is executable."""
        return self.memory_bin.exists() and os.access(self.memory_bin, os.X_OK)

    def list(
        self,
        type_: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> list[MemoryObservation]:
        """Return parsed memory entries, optionally filtered by type/subject.

        Returns [] on any subprocess failure or empty output. Malformed lines
        are skipped silently (they would surface as debug warnings in a logged
        environment, but resume-brief callers should not crash on a single
        bad bullet).
        """
        cmd = [str(self.memory_bin), "list"]
        if type_ is not None:
            cmd.extend(["--type", type_])
        if subject is not None:
            cmd.extend(["--subject", subject])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.SubprocessError, OSError):
            return []

        if result.returncode != 0:
            return []

        return _parse_list_output(result.stdout)


def _parse_list_output(text: str) -> list[MemoryObservation]:
    """Parse `bin/memory list` output. One entry per non-empty line."""
    observations: list[MemoryObservation] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        obs = _parse_line(line)
        if obs is not None:
            observations.append(obs)
    return observations


def _parse_line(line: str) -> Optional[MemoryObservation]:
    """Parse a single `<type>:<subject>:<name> — <description>` line.

    Returns None on malformed input rather than raising — callers want to
    skip noise, not abort the whole list.
    """
    if _SEPARATOR not in line:
        return None
    head, description = line.split(_SEPARATOR, 1)
    parts = head.split(":", 2)
    if len(parts) != 3:
        return None
    type_, subject, name = parts
    if not (type_ and subject and name):
        return None
    return MemoryObservation(
        type=type_,
        subject=subject,
        name=name,
        description=description.strip(),
    )
