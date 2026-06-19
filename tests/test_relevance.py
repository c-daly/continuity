# tests/test_relevance.py
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from memory_read_provider import MemoryObservation  # noqa: E402
from relevance import _age_days, index_path, load_index, rank, record_surfaced, score  # noqa: E402


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


def test_index_path_honors_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTINUITY_CONFIG_DIR", str(tmp_path))
    assert index_path() == tmp_path / "relevance.json"


def test_load_missing_index_is_empty(tmp_path):
    assert load_index(tmp_path / "relevance.json") == {}


def test_load_malformed_index_is_empty(tmp_path):
    p = tmp_path / "relevance.json"
    p.write_text("[1, 2, 3]")
    assert load_index(p) == {}
    p.write_text("\"just a string\"")
    assert load_index(p) == {}


def test_record_surfaced_bumps_freq_and_last_seen(tmp_path):
    p = tmp_path / "relevance.json"
    record_surfaced(["a", "b"], path=p, today=date(2026, 6, 30))
    record_surfaced(["a"], path=p, today=date(2026, 7, 1))
    idx = load_index(p)
    assert idx["a"] == {"last_seen": "2026-07-01", "freq": 2}
    assert idx["b"] == {"last_seen": "2026-06-30", "freq": 1}


def test_record_surfaced_writes_valid_json(tmp_path):
    p = tmp_path / "relevance.json"
    record_surfaced(["x"], path=p, today=date(2026, 6, 30))
    assert json.loads(p.read_text())["x"]["freq"] == 1


def test_rank_orders_by_score_desc(tmp_path):
    today = date(2026, 6, 30)
    obs = [
        MemoryObservation("project", "p", "2026-05-01-old", "d"),
        MemoryObservation("feedback", "p", "2026-05-01-pref", "d"),
        MemoryObservation("project", "p", "2026-06-29-fresh", "d"),
    ]
    ranked = rank(obs, {}, today)
    assert ranked[-1].name == "2026-05-01-old"
    assert set(o.name for o in ranked[:2]) == {"2026-05-01-pref", "2026-06-29-fresh"}


def test_rank_uses_index_freq_to_break_ties(tmp_path):
    today = date(2026, 6, 30)
    a = MemoryObservation("project", "p", "2026-06-01-a", "d")
    b = MemoryObservation("project", "p", "2026-06-01-b", "d")
    index = {"2026-06-01-b": {"last_seen": "2026-06-29", "freq": 10}}
    ranked = rank([a, b], index, today)
    assert ranked[0].name == "2026-06-01-b"


def test_record_surfaced_swallows_write_errors(tmp_path):
    # Parent is a regular file, so mkdir/write fail with OSError — which must be
    # swallowed (bookkeeping can never abort the caller, e.g. resume_brief).
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    record_surfaced(["a"], path=blocker / "relevance.json", today=date(2026, 6, 30))


def test_record_surfaced_resets_nondict_entry(tmp_path):
    p = tmp_path / "relevance.json"
    p.write_text('{"x": "not-a-dict"}')  # corrupted/hand-edited entry value
    record_surfaced(["x"], path=p, today=date(2026, 6, 30))
    assert load_index(p)["x"] == {"last_seen": "2026-06-30", "freq": 1}


def test_record_surfaced_empty_names_is_noop(tmp_path):
    p = tmp_path / "relevance.json"
    record_surfaced([], path=p, today=date(2026, 6, 30))
    assert not p.exists()


def test_rank_tolerates_nondict_index_entry(tmp_path):
    a = MemoryObservation("project", "p", "2026-06-01-a", "d")
    ranked = rank([a], {"2026-06-01-a": "garbage"}, date(2026, 6, 30))
    assert ranked == [a]  # non-dict entry -> freq 0, no crash
