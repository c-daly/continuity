"""Continuity synthesis domain types + interfaces.

Promotions are continuity-owned second-order artifacts consolidating scattered
first-order memory observations. LLM-facing steps (clustering, drafting) are
ABCs so the pass is testable with fakes.
"""
from __future__ import annotations

import re
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from memory_read_provider import MemoryObservation  # noqa: E402


@dataclass(frozen=True)
class SourceRef:
    name: str
    scope: str


@dataclass
class Cluster:
    concept: str
    members: list[MemoryObservation]

    def subjects(self) -> list[str]:
        return sorted({m.subject for m in self.members})


@dataclass
class PromotionDraft:
    title: str
    statement: str
    consolidates: bool
    justification: str


@dataclass
class Promotion:
    id: str
    scope: str
    title: str
    statement: str
    sources: list[SourceRef]
    instances: int
    created_at: str
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None


class Clusterer(ABC):
    @abstractmethod
    def cluster(self, observations: list[MemoryObservation],
                existing: list[Promotion]) -> list[Cluster]:
        """Propose cross-boundary concept clusters."""


class Drafter(ABC):
    @abstractmethod
    def draft(self, cluster: Cluster, scope: str) -> PromotionDraft:
        """Draft the cohesive statement + consolidation affirmation."""


def promotion_id(concept: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", concept.lower()).strip("-")
    return (slug or "promotion")[:60]


def promotion_to_frontmatter(p: Promotion) -> dict:
    return {
        "kind": "promotion",
        "scope": p.scope,
        "title": p.title,
        "sources": [{"name": s.name, "scope": s.scope} for s in p.sources],
        "instances": p.instances,
        "created_at": p.created_at,
        "supersedes": p.supersedes,
        "superseded_by": p.superseded_by,
    }
