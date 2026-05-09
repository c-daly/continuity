"""Tests for the MemoryWriteProvider stub."""

import pytest

from memory_write_provider import MemoryWriteProvider


def test_write_raises_not_implemented():
    wp = MemoryWriteProvider()
    with pytest.raises(NotImplementedError, match="memory plugin not yet available"):
        wp.write("cont.insight", "x", {"project": "p"}, "b")


def test_exists_raises_not_implemented():
    wp = MemoryWriteProvider()
    with pytest.raises(NotImplementedError, match="memory plugin not yet available"):
        wp.exists("cont.insight", "x")
