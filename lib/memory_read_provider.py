"""Read first-order observations from the memory plugin CLI.

The memory CLI currently emits one observation per line:

    project:memory-plugin:memory-plugin-mcp-verified-2026-05-13 — ...

This provider treats that CLI as an optional read source. Missing CLI,
command failures, and malformed lines return no observations rather than
breaking resume-brief generation.
"""

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import subprocess
from typing import Optional


LOGGER = logging.getLogger(__name__)
_DEFAULT_MEMORY_BIN = Path.home() / ".claude" / "plugins" / "memory" / "bin" / "memory"
_DESCRIPTION_SEPARATOR = " — "
_DEFAULT_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class MemoryObservation:
    """One observation returned by the memory plugin."""

    type: str
    subject: str
    name: str
    description: str


class MemoryReadProvider:
    """Read observations through the memory plugin's CLI."""

    def __init__(
        self,
        memory_bin: Optional[str | Path] = None,
        env: Optional[dict[str, str]] = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.memory_bin = Path(memory_bin) if memory_bin is not None else _DEFAULT_MEMORY_BIN
        self.env = env
        self.timeout_seconds = timeout_seconds

    def available(self) -> bool:
        """Return true when the memory CLI exists at the configured path."""
        return self.memory_bin.is_file()

    def list(
        self,
        *,
        type: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> list[MemoryObservation]:
        """List memory observations, optionally filtered by type and subject."""
        if not self.available():
            return []

        args = [str(self.memory_bin), "list"]
        if type:
            args.extend(["--type", type])
        if subject:
            args.extend(["--subject", subject])

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                env=self._subprocess_env(),
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("memory list timed out after %.1f seconds", self.timeout_seconds)
            return []
        except OSError as exc:
            LOGGER.warning("memory list failed to start: %s", exc)
            return []

        if result.returncode != 0:
            stderr = result.stderr.strip()
            LOGGER.warning("memory list failed with exit code %s: %s", result.returncode, stderr)
            return []

        observations: list[MemoryObservation] = []
        for line in result.stdout.splitlines():
            observation = parse_memory_observation(line)
            if observation is not None:
                observations.append(observation)
        return observations

    def _subprocess_env(self) -> dict[str, str]:
        env = dict(os.environ if self.env is None else self.env)
        if "MEMORY_VAULT_DIR" not in env:
            vault_dir = env.get("CONTINUITY_VAULT_DIR") or env.get("VAULT_DIR")
            if vault_dir:
                env["MEMORY_VAULT_DIR"] = vault_dir
        return env


def parse_memory_observation(line: str) -> Optional[MemoryObservation]:
    """Parse one ``bin/memory list`` output line."""
    clean = line.strip()
    if not clean:
        return None

    if _DESCRIPTION_SEPARATOR not in clean:
        LOGGER.debug("skipping malformed memory line without separator: %s", clean)
        return None

    identity, description = clean.split(_DESCRIPTION_SEPARATOR, 1)
    parts = identity.split(":", 2)
    if len(parts) != 3 or not all(part.strip() for part in parts):
        LOGGER.debug("skipping malformed memory identity: %s", identity)
        return None

    return MemoryObservation(
        type=parts[0].strip(),
        subject=parts[1].strip(),
        name=parts[2].strip(),
        description=description.strip(),
    )
