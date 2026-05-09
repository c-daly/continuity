"""Tests for continuity config loading + WriteProvider selection."""

import pytest

from config import get_write_provider, load_config
from memory_write_provider import MemoryWriteProvider
from vault_write_provider import VaultWriteProvider


def _isolate_config(monkeypatch, cfg_dir):
    """Point continuity at an isolated config dir for the duration of a test."""
    monkeypatch.setenv("CONTINUITY_CONFIG_DIR", str(cfg_dir))


def test_load_config_missing_file_returns_empty(tmp_path, monkeypatch):
    _isolate_config(monkeypatch, tmp_path)
    assert load_config() == {}


def test_load_config_parses_yaml(tmp_path, monkeypatch):
    _isolate_config(monkeypatch, tmp_path)
    (tmp_path / "config.yaml").write_text("write_provider: memory\n")
    assert load_config() == {"write_provider": "memory"}


def test_load_config_rejects_non_mapping(tmp_path, monkeypatch):
    _isolate_config(monkeypatch, tmp_path)
    (tmp_path / "config.yaml").write_text("- just\n- a\n- list\n")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_config()


def test_default_provider_is_vault(fake_vault, tmp_path, monkeypatch):
    _isolate_config(monkeypatch, tmp_path)
    monkeypatch.setenv("CONTINUITY_VAULT_DIR", str(fake_vault))
    wp = get_write_provider()
    assert isinstance(wp, VaultWriteProvider)


def test_explicit_vault_selection(fake_vault, monkeypatch):
    monkeypatch.setenv("CONTINUITY_VAULT_DIR", str(fake_vault))
    wp = get_write_provider({"write_provider": "vault"})
    assert isinstance(wp, VaultWriteProvider)


def test_explicit_memory_selection():
    wp = get_write_provider({"write_provider": "memory"})
    assert isinstance(wp, MemoryWriteProvider)


def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown write_provider"):
        get_write_provider({"write_provider": "magic"})
