# lib/relevance.py
"""Relevance scoring + decay for memory observations (continuity-owned).

Second-order over memory's first-order entries: a per-type recency decay
(durable types persist, episodic fade) plus a mild surfaced-frequency boost.
Pure scoring is here; persistence + ranking + wiring follow.
"""
from __future__ import annotations

import math
import sys
from datetime import date
from pathlib import Path

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
