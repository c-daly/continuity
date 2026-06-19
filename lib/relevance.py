# lib/relevance.py
"""Relevance scoring + decay for memory observations (continuity-owned).

Second-order over memory's first-order entries: a per-type recency decay
(durable types persist, episodic fade) plus a mild surfaced-frequency boost.
Pure scoring is here; persistence + ranking + wiring follow.
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from memory_read_provider import MemoryObservation  # noqa: E402

# Per-type decay half-life (days). Durable types persist ~a year; episodic
# `project` entries fade in ~2 weeks unless surfaced. Tunable.
HALF_LIFE_BY_TYPE = {
    "user": 365.0,
    "feedback": 365.0,
    "reference": 90.0,
    "project": 14.0,
}
_DEFAULT_HALF_LIFE = 30.0
_FREQ_WEIGHT = 0.1


def _age_days(name: str, today: date) -> int:
    """Days between `today` and the YYYY-MM-DD prefix of `name`.

    Memory entries are named `<YYYY-MM-DD>-<slug>`. Names with no parseable
    date prefix return 0 (treated as current; not penalized).
    """
    try:
        entry_date = date.fromisoformat(name[:10])
    except ValueError:
        return 0
    return max(0, (today - entry_date).days)


def score(obs: MemoryObservation, freq: int, today: date) -> float:
    """Effective score = exp(-age / half_life(type)) + _FREQ_WEIGHT * freq."""
    half_life = HALF_LIFE_BY_TYPE.get(obs.type, _DEFAULT_HALF_LIFE)
    recency = math.exp(-_age_days(obs.name, today) / half_life)
    return recency + _FREQ_WEIGHT * freq


def index_path() -> Path:
    """Relevance index location, honoring CONTINUITY_CONFIG_DIR (test isolation)."""
    base = os.environ.get("CONTINUITY_CONFIG_DIR")
    root = Path(base) if base else Path.home() / ".config" / "continuity"
    return root / "relevance.json"


def load_index(path: Optional[Path] = None) -> dict[str, dict]:
    """Load the relevance index, or {} if absent / unreadable / malformed."""
    p = path or index_path()
    try:
        loaded = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _safe_freq(entry) -> int:
    """freq from an index entry, tolerant of corrupted / non-dict / non-int values."""
    if not isinstance(entry, dict):
        return 0
    try:
        return int(entry.get("freq", 0))
    except (TypeError, ValueError):
        return 0


def record_surfaced(
    names: list[str],
    path: Optional[Path] = None,
    today: Optional[date] = None,
) -> None:
    """Bump freq + set last_seen for each surfaced entry name (atomic write).

    Best-effort bookkeeping: malformed existing entries are reset, empty
    `names` is a no-op, and any I/O failure is swallowed so a write error
    can never abort the caller (e.g. the resume brief).
    """
    if not names:
        return
    p = path or index_path()
    when = (today or date.today()).isoformat()
    idx = load_index(p)
    for name in names:
        idx[name] = {"last_seen": when, "freq": _safe_freq(idx.get(name)) + 1}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(idx, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        return  # non-critical bookkeeping must never crash the caller


def rank(observations, index: dict, today: date) -> list[MemoryObservation]:
    """Return observations sorted by effective score, descending (stable)."""
    def _key(obs: MemoryObservation) -> float:
        return score(obs, _safe_freq(index.get(obs.name)), today)
    return sorted(observations, key=_key, reverse=True)
