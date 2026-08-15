"""Continuity synthesis settling pass: convergence gate + orchestration."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from promotion import (Cluster, Promotion, SourceRef, PromotionDraft, PromotionStore,
                       Clusterer, Drafter, promotion_id, promotion_to_frontmatter)  # noqa: E402
from memory_read_provider import MemoryReadProvider  # noqa: E402
from vault_write_provider import VaultWriteProvider  # noqa: E402
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
        if names <= srcs or srcs <= names:
            return True
    return False
