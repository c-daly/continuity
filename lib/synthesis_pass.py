"""Continuity synthesis settling pass: convergence gate + orchestration."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from promotion import (Cluster, Promotion, SourceRef, Clusterer, Drafter,
                       promotion_id, promotion_to_frontmatter)  # noqa: E402
from scope_resolver import resolve_scope  # noqa: E402

MIN_INSTANCES = 2
MIN_SCOPES = 2


def is_cross_boundary(cluster: Cluster, min_instances: int = MIN_INSTANCES,
                      min_scopes: int = MIN_SCOPES) -> bool:
    return len(cluster.members) >= min_instances and len(cluster.subjects()) >= min_scopes


def already_covered(cluster: Cluster, existing: list[Promotion]) -> bool:
    """True if some live promotion covers this concept: its source set is
    nested with the cluster's members (identical, grown, or shrunk). Distinct
    concepts that merely share a member (non-nested overlap) are NOT covered,
    so they still promote. Refreshing a covered-but-grown promotion with the
    new sources is slice-2 refinement."""
    names = {m.name for m in cluster.members}
    for p in existing:
        srcs = {s.name for s in p.sources}
        if names and srcs and (names <= srcs or srcs <= names):
            return True
    return False


@dataclass
class SynthesisResult:
    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def run_synthesis(reader, writer, store, clusterer: Clusterer, drafter: Drafter,
                  vault_path: Path, today: Optional[date] = None) -> SynthesisResult:
    when = (today or date.today()).isoformat()
    observations = reader.list()
    result = SynthesisResult()
    if not observations:
        return result

    existing = store.list()
    clusters = clusterer.cluster(observations, existing)

    for cluster in clusters:
        try:
            if not is_cross_boundary(cluster):
                result.skipped.append(cluster.concept)
                continue
            if already_covered(cluster, existing):
                result.skipped.append(cluster.concept)
                continue
            scope = resolve_scope([m.subject for m in cluster.members], vault_path)
            if scope is None:
                result.skipped.append(cluster.concept)
                continue
            draft = drafter.draft(cluster, scope)
            if not draft.consolidates:
                result.skipped.append(cluster.concept)
                continue
            pid = promotion_id(cluster.concept)
            promo = Promotion(
                id=pid, scope=scope, title=draft.title, statement=draft.statement,
                sources=[SourceRef(m.name, m.subject) for m in cluster.members],
                instances=len(cluster.members), created_at=when,
            )
            writer.write("cont.promotion", pid, promotion_to_frontmatter(promo), draft.statement)
            result.written.append(pid)
            existing.append(promo)   # intra-pass convergence: later clusters see this write
        except Exception:            # best-effort: one bad cluster never aborts the pass
            result.skipped.append(cluster.concept)
            continue

    return result
