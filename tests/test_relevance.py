# tests/test_relevance.py
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from memory_read_provider import MemoryObservation  # noqa: E402
from relevance import _age_days, score  # noqa: E402


def _obs(name, type_="project"):
    return MemoryObservation(type=type_, subject="proj", name=name, description="d")


def test_age_days_parses_name_prefix():
    assert _age_days("2026-06-01-foo", date(2026, 6, 11)) == 10


def test_age_days_undated_name_is_zero():
    assert _age_days("no-date-here", date(2026, 6, 11)) == 0


def test_durable_type_outscores_episodic_at_same_age():
    today = date(2026, 6, 30)
    old = "2026-05-01-x"  # ~60 days old
    assert score(_obs(old, "feedback"), 0, today) > score(_obs(old, "project"), 0, today)


def test_recent_outscores_old_same_type():
    today = date(2026, 6, 30)
    recent = score(_obs("2026-06-29-x", "project"), 0, today)
    old = score(_obs("2026-05-01-x", "project"), 0, today)
    assert recent > old


def test_frequency_boosts_score():
    today = date(2026, 6, 30)
    base = score(_obs("2026-06-01-x"), 0, today)
    boosted = score(_obs("2026-06-01-x"), 5, today)
    assert boosted > base


def test_unknown_type_uses_default_half_life_without_crashing():
    assert score(_obs("2026-06-29-x", "weird-type"), 0, date(2026, 6, 30)) > 0
