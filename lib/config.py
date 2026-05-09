"""Continuity configuration.

Reads ``~/.config/continuity/config.yaml`` (or ``$CONTINUITY_CONFIG_DIR``)
and resolves a ``WriteProvider`` instance for the configured target.

Schema (all fields optional):

.. code:: yaml

    write_provider: vault   # or "memory"; default "vault"

Vault path resolution is delegated to the underlying provider, which
honors ``CONTINUITY_VAULT_DIR`` then ``VAULT_DIR``.
"""

import os
import sys
from pathlib import Path
from typing import Any, Optional

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from memory_write_provider import MemoryWriteProvider  # noqa: E402
from vault_write_provider import VaultWriteProvider  # noqa: E402
from write_provider import WriteProvider  # noqa: E402


_DEFAULT_WRITE_PROVIDER = "vault"
_KNOWN_WRITE_PROVIDERS = {"vault", "memory"}


def _config_dir() -> Path:
    env = os.environ.get("CONTINUITY_CONFIG_DIR")
    if env:
        return Path(env)
    return Path.home() / ".config" / "continuity"


def load_config() -> dict[str, Any]:
    """Return the parsed config dict, or an empty dict if the file is absent."""
    cfg_path = _config_dir() / "config.yaml"
    if not cfg_path.is_file():
        return {}
    with cfg_path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Continuity config at {cfg_path} must be a mapping")
    return loaded


def get_write_provider(config: Optional[dict[str, Any]] = None) -> WriteProvider:
    """Resolve and instantiate the configured WriteProvider."""
    cfg = config if config is not None else load_config()
    name = cfg.get("write_provider", _DEFAULT_WRITE_PROVIDER)
    if name not in _KNOWN_WRITE_PROVIDERS:
        raise ValueError(
            f"Unknown write_provider {name!r}; "
            f"expected one of {sorted(_KNOWN_WRITE_PROVIDERS)}"
        )
    if name == "vault":
        return VaultWriteProvider()
    return MemoryWriteProvider()
