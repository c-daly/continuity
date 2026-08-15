# Continuity Synthesis & Promotion (v1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give continuity a working synthesis step: a deferred settling pass that detects concepts recurring across scope boundaries in the memory corpus and promotes each into a continuity-owned cohesive artifact written at the appropriate vault scope.

**Architecture:** A batch pass reads the whole memory corpus (scope-blind) via the existing `MemoryReadProvider`, an injectable LLM clusterer proposes cross-boundary concept clusters, a convergence gate rejects weak/duplicate clusters, a scope resolver computes the tightest subsuming vault scope, an injectable LLM drafter writes the cohesive statement, and a generalized `VaultWriteProvider` persists it as a `cont.promotion` anywhere in the vault. Additive only: memory is never edited; refinement appends a superseding promotion.

**Tech Stack:** Python 3 stdlib + PyYAML (already a dependency). LLM access via an injectable runner (subprocess `claude -p`); all LLM steps sit behind interfaces so tests are deterministic with fakes.

## Global Constraints

- **Continuity never edits memory.** The pass only reads memory and only writes continuity-owned `cont.promotion` artifacts. No memory file is ever modified.
- **Additive + append-only refinement.** Refinement writes a NEW superseding promotion; never edit an existing one.
- **Converge, not proliferate.** Re-running the pass writes zero new promotions for concepts already promoted (identical OR grown clusters -> nested-set skip). Verified by run-twice and grown-cluster tests.
- **Least-general subsuming scope; never a lazy root-dump.** Scope = longest common vault-directory prefix of the cluster's members. Root is reached only when members genuinely span everything.
- **Cross-boundary requirement.** A cluster promotes only if it spans `>= MIN_SCOPES` (default 2) distinct member subjects and has `>= MIN_INSTANCES` (default 2) members.
- **Traversal-safe writes.** Every scope/id path component is validated (reject `""`, `.`, `..`, `/`, `\`, NUL) before composing a vault path.
- **Determinism in tests.** No test invokes a real LLM or a real `claude` binary; clusterer/drafter/runner are injected fakes. One live smoke test is marked and skipped by default.

**Spec:** `docs/superpowers/plans/../specs/2026-08-15-continuity-synthesis-and-promotion-design.md` (repo) / `10-projects/continuity/2026-08-15-synthesis-and-promotion-design.md` (vault).

**Existing code this builds on (read before starting):**
- `lib/memory_read_provider.py` — `MemoryObservation(type, subject, name, description)` (frozen); `MemoryReadProvider.list(type_=None, subject=None) -> list[MemoryObservation]` (no args = whole corpus); `.available()`.
- `lib/vault_write_provider.py` — `VaultWriteProvider.write(kind, id, frontmatter, body)`, `_KIND_TO_SUBDIR`, `validate_basename(name, label)`, atomic temp-file write.
- `lib/vault_provider.py` — `VaultProvider(vault_path)`, `.vault_path`, `.list_projects()`.
- `lib/write_provider.py` — `WriteProvider` ABC.

## File Structure

- `lib/scope_resolver.py` (new) — subject -> vault-relative entity path; longest-common-prefix scope resolution.
- `lib/vault_write_provider.py` (modify) — add `cont.promotion` kind writing at `<scope>/promotions/<id>.md`, scope taken from frontmatter, traversal-safe.
- `lib/promotion.py` (new) — domain types (`SourceRef`, `Cluster`, `PromotionDraft`, `Promotion`), `Clusterer`/`Drafter` ABCs, frontmatter (de)serialization, `PromotionStore` (read existing promotions across the vault).
- `lib/synthesis_pass.py` (new) — the convergence gate + `run_synthesis(...)` orchestration.
- `lib/llm_synthesis.py` (new) — `LLMRunner` protocol + `ClaudeCliRunner`; `LLMClusterer`/`LLMDrafter` (prompt + JSON parse) behind the ABCs.
- `bin/continuity` + `lib/cli.py` (modify) — `continuity synthesize` subcommand.
- Tests: one `tests/test_<module>.py` per module.

---

### Task 1: Scope resolver

**Files:**
- Create: `lib/scope_resolver.py`
- Test: `tests/test_scope_resolver.py`

**Interfaces:**
- Produces: `subject_to_relpath(subject: str, vault_path: Path) -> Optional[str]` (vault-relative POSIX dir path, `""` for user/root, `None` if unlocatable); `resolve_scope(subjects: list[str], vault_path: Path) -> str` (longest common directory prefix; `""` = vault root).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scope_resolver.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from scope_resolver import subject_to_relpath, resolve_scope


def _vault(tmp_path):
    (tmp_path / "10-projects" / "LOGOS" / "sophia").mkdir(parents=True)
    (tmp_path / "10-projects" / "agent-swarm").mkdir(parents=True)
    return tmp_path


def test_subject_user_is_root(tmp_path):
    assert subject_to_relpath("user", _vault(tmp_path)) == ""

def test_subject_project_maps_to_dir(tmp_path):
    assert subject_to_relpath("LOGOS", _vault(tmp_path)) == "10-projects/LOGOS"

def test_subject_nested_entity_maps_to_nested_dir(tmp_path):
    assert subject_to_relpath("sophia", _vault(tmp_path)) == "10-projects/LOGOS/sophia"

def test_subject_unknown_is_none(tmp_path):
    assert subject_to_relpath("nope", _vault(tmp_path)) is None

def test_resolve_scope_same_subject(tmp_path):
    assert resolve_scope(["LOGOS", "LOGOS"], _vault(tmp_path)) == "10-projects/LOGOS"

def test_resolve_scope_parent_and_child(tmp_path):
    # LOGOS + its sub-entity sophia -> tightest common = LOGOS
    assert resolve_scope(["LOGOS", "sophia"], _vault(tmp_path)) == "10-projects/LOGOS"

def test_resolve_scope_sibling_projects(tmp_path):
    # LOGOS + agent-swarm -> common prefix is 10-projects
    assert resolve_scope(["LOGOS", "agent-swarm"], _vault(tmp_path)) == "10-projects"

def test_resolve_scope_spans_user_is_root(tmp_path):
    assert resolve_scope(["user", "LOGOS"], _vault(tmp_path)) == ""

def test_resolve_scope_unlocatable_subject_ignored(tmp_path):
    # unknown subjects do not drag scope to root; they are dropped
    assert resolve_scope(["LOGOS", "nope"], _vault(tmp_path)) == "10-projects/LOGOS"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_scope_resolver.py -q`
Expected: FAIL (`ModuleNotFoundError: scope_resolver`).

- [ ] **Step 3: Implement `lib/scope_resolver.py`**

```python
"""Scope resolution for continuity synthesis.

Maps a memory entry's `subject` to its vault-relative entity directory and
computes the least-general (tightest) scope that subsumes a set of subjects,
as the longest common directory prefix. `""` denotes the vault root (user
scope). Unlocatable subjects are dropped, never resolved to root.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

_USER_SUBJECTS = {"user"}


def subject_to_relpath(subject: str, vault_path: Path) -> Optional[str]:
    if subject in _USER_SUBJECTS:
        return ""
    projects = vault_path / "10-projects"
    if not projects.is_dir():
        return None
    # Exact directory named <subject>, searched within 10-projects (may nest).
    for cand in projects.rglob(subject):
        if cand.is_dir() and cand.name == subject:
            return cand.relative_to(vault_path).as_posix()
    return None


def resolve_scope(subjects: list[str], vault_path: Path) -> str:
    paths = []
    for s in subjects:
        rel = subject_to_relpath(s, vault_path)
        if rel is not None:
            paths.append(rel.split("/") if rel else [])
    if not paths:
        return ""
    common: list[str] = []
    for parts in zip(*paths):
        if len(set(parts)) == 1:
            common.append(parts[0])
        else:
            break
    return "/".join(common)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_scope_resolver.py -q`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/scope_resolver.py tests/test_scope_resolver.py
git commit -m "feat(synthesis): scope resolver (subject->path, longest-common-prefix)"
```

---

### Task 2: Generalize the vault write provider (write throughout)

**Files:**
- Modify: `lib/vault_write_provider.py`
- Test: `tests/test_vault_write_provider.py` (extend if present, else create)

**Interfaces:**
- Consumes: existing `VaultWriteProvider.write(kind, id, frontmatter, body)`, `validate_basename`.
- Produces: kind `cont.promotion` writes to `<vault>/<scope>/promotions/<id>.md`, where `scope` is a vault-relative POSIX dir from `frontmatter["scope"]` (`""` = vault root). Each scope component is traversal-validated. Existing kinds unchanged.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_vault_write_provider.py  (add these)
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from vault_write_provider import VaultWriteProvider


def test_promotion_writes_at_project_scope(tmp_path):
    (tmp_path / "10-projects" / "LOGOS").mkdir(parents=True)
    w = VaultWriteProvider(vault_path=tmp_path)
    w.write("cont.promotion", "concept-x",
            {"scope": "10-projects/LOGOS", "kind": "promotion"}, "body")
    assert (tmp_path / "10-projects/LOGOS/promotions/concept-x.md").is_file()

def test_promotion_writes_at_root_scope(tmp_path):
    w = VaultWriteProvider(vault_path=tmp_path)
    w.write("cont.promotion", "concept-y", {"scope": "", "kind": "promotion"}, "body")
    assert (tmp_path / "promotions/concept-y.md").is_file()

def test_promotion_creates_missing_scope_dirs(tmp_path):
    w = VaultWriteProvider(vault_path=tmp_path)
    w.write("cont.promotion", "z", {"scope": "10-projects/New", "kind": "promotion"}, "b")
    assert (tmp_path / "10-projects/New/promotions/z.md").is_file()

def test_promotion_rejects_traversal_scope(tmp_path):
    w = VaultWriteProvider(vault_path=tmp_path)
    with pytest.raises(ValueError):
        w.write("cont.promotion", "z", {"scope": "../evil", "kind": "promotion"}, "b")

def test_promotion_rejects_traversal_id(tmp_path):
    w = VaultWriteProvider(vault_path=tmp_path)
    with pytest.raises(ValueError):
        w.write("cont.promotion", "../evil", {"scope": "", "kind": "promotion"}, "b")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_vault_write_provider.py -q -k promotion`
Expected: FAIL (`Unknown kind: 'cont.promotion'`).

- [ ] **Step 3: Implement the generalization**

In `lib/vault_write_provider.py`, add a scope-driven branch. Add near `_KIND_TO_SUBDIR`:

```python
_PROMOTION_KIND = "cont.promotion"
_PROMOTION_SUBDIR = "promotions"
```

In `write()`, before the existing `project`-based resolution, handle the promotion kind:

```python
        if kind == _PROMOTION_KIND:
            target = self._resolve_promotion(id, str(frontmatter.get("scope", "")))
        else:
            project = frontmatter.get("project")
            if not project:
                raise ValueError(
                    f"VaultWriteProvider requires 'project' in frontmatter for kind {kind!r}"
                )
            target = self._resolve(kind, id, str(project))
```

Add the resolver method (validates each scope segment, so `""` -> root is fine and `..` is rejected):

```python
    def _resolve_promotion(self, id: str, scope: str) -> Path:
        validate_basename(id, "id")
        base = self.vault_path
        if scope:
            for seg in scope.split("/"):
                validate_basename(seg, "scope segment")
                base = base / seg
        return base / _PROMOTION_SUBDIR / f"{id}.md"
```

Also extend `exists()` so a promotion is recognized (needed by later idempotence): add at the top of `exists()`:

```python
        if kind == _PROMOTION_KIND:
            validate_basename(id, "id")
            return any(self.vault_path.rglob(f"{_PROMOTION_SUBDIR}/{id}.md"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_vault_write_provider.py -q`
Expected: PASS (new + existing).

- [ ] **Step 5: Commit**

```bash
git add lib/vault_write_provider.py tests/test_vault_write_provider.py
git commit -m "feat(synthesis): vault write provider writes cont.promotion throughout the vault"
```

---

### Task 3: Synthesis domain types + interfaces

**Files:**
- Create: `lib/promotion.py`
- Test: `tests/test_promotion.py`

**Interfaces:**
- Produces:
  - `SourceRef(name: str, scope: str)` (frozen dataclass).
  - `Cluster(concept: str, members: list[MemoryObservation])` with `.subjects() -> list[str]` (distinct member subjects, sorted).
  - `PromotionDraft(title: str, statement: str, consolidates: bool, justification: str)`.
  - `Promotion(id: str, scope: str, title: str, statement: str, sources: list[SourceRef], instances: int, created_at: str, supersedes: Optional[str]=None, superseded_by: Optional[str]=None)`.
  - `Clusterer` ABC: `cluster(observations: list[MemoryObservation], existing: list[Promotion]) -> list[Cluster]`.
  - `Drafter` ABC: `draft(cluster: Cluster, scope: str) -> PromotionDraft`.
  - `promotion_to_frontmatter(p: Promotion) -> dict` and `promotion_id(concept: str) -> str` (slug).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_promotion.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from memory_read_provider import MemoryObservation
from promotion import (SourceRef, Cluster, PromotionDraft, Promotion,
                       promotion_to_frontmatter, promotion_id)


def _obs(subject, name):
    return MemoryObservation(type="project", subject=subject, name=name, description="d")

def test_cluster_subjects_distinct_sorted():
    c = Cluster(concept="x", members=[_obs("b", "1"), _obs("a", "2"), _obs("b", "3")])
    assert c.subjects() == ["a", "b"]

def test_promotion_id_is_slug():
    assert promotion_id("Always Parallelize Work!") == "always-parallelize-work"

def test_frontmatter_roundtrips_core_fields():
    p = Promotion(id="c", scope="10-projects/LOGOS", title="T", statement="S",
                  sources=[SourceRef("n1", "LOGOS"), SourceRef("n2", "sophia")],
                  instances=2, created_at="2026-08-15", supersedes=None)
    fm = promotion_to_frontmatter(p)
    assert fm["kind"] == "promotion"
    assert fm["scope"] == "10-projects/LOGOS"
    assert fm["instances"] == 2
    assert {s["name"] for s in fm["sources"]} == {"n1", "n2"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_promotion.py -q`
Expected: FAIL (`ModuleNotFoundError: promotion`).

- [ ] **Step 3: Implement `lib/promotion.py`**

```python
"""Continuity synthesis domain types + interfaces.

Promotions are continuity-owned second-order artifacts consolidating scattered
first-order memory observations. LLM-facing steps (clustering, drafting) are
ABCs so the pass is testable with fakes.
"""
from __future__ import annotations

import re
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_promotion.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/promotion.py tests/test_promotion.py
git commit -m "feat(synthesis): promotion domain types + Clusterer/Drafter interfaces"
```

---

### Task 4: PromotionStore — read existing promotions

**Files:**
- Modify: `lib/promotion.py` (append `PromotionStore`)
- Test: `tests/test_promotion_store.py`

**Interfaces:**
- Produces: `PromotionStore(vault_path: Path)` with `.list() -> list[Promotion]` (parses every `**/promotions/*.md` whose frontmatter `kind == promotion` and `superseded_by` is null — i.e. live promotions).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_promotion_store.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from vault_write_provider import VaultWriteProvider
from promotion import Promotion, SourceRef, promotion_to_frontmatter, PromotionStore


def _write(vault, p):
    VaultWriteProvider(vault_path=vault).write(
        "cont.promotion", p.id, promotion_to_frontmatter(p), p.statement)

def test_store_lists_live_promotions_only(tmp_path):
    (tmp_path / "10-projects" / "LOGOS").mkdir(parents=True)
    live = Promotion(id="a", scope="10-projects/LOGOS", title="A", statement="s",
                     sources=[SourceRef("n", "LOGOS")], instances=2, created_at="2026-08-15")
    dead = Promotion(id="b", scope="", title="B", statement="s",
                     sources=[SourceRef("n", "user")], instances=2, created_at="2026-08-15",
                     superseded_by="a")
    _write(tmp_path, live)
    _write(tmp_path, dead)
    ids = {p.id for p in PromotionStore(tmp_path).list()}
    assert ids == {"a"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_promotion_store.py -q`
Expected: FAIL (`ImportError: cannot import name 'PromotionStore'`).

- [ ] **Step 3: Implement `PromotionStore` in `lib/promotion.py`**

```python
import yaml  # add to imports at top of promotion.py


class PromotionStore:
    """Reads live (non-superseded) promotions across the whole vault."""

    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path)

    def list(self) -> list["Promotion"]:
        out: list[Promotion] = []
        for f in self.vault_path.rglob("promotions/*.md"):
            fm = self._frontmatter(f)
            if fm.get("kind") != "promotion" or fm.get("superseded_by"):
                continue
            out.append(Promotion(
                id=f.stem,
                scope=str(fm.get("scope", "")),
                title=str(fm.get("title", "")),
                statement="",
                sources=[SourceRef(s.get("name", ""), s.get("scope", ""))
                         for s in fm.get("sources", []) if isinstance(s, dict)],
                instances=int(fm.get("instances", 0)),
                created_at=str(fm.get("created_at", "")),
                supersedes=fm.get("supersedes"),
                superseded_by=fm.get("superseded_by"),
            ))
        return out

    @staticmethod
    def _frontmatter(path: Path) -> dict:
        text = path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        if not m:
            return {}
        loaded = yaml.safe_load(m.group(1))
        return loaded if isinstance(loaded, dict) else {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_promotion_store.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/promotion.py tests/test_promotion_store.py
git commit -m "feat(synthesis): PromotionStore reads live promotions across the vault"
```

---

### Task 5: Convergence gate

**Files:**
- Create: `lib/synthesis_pass.py`
- Test: `tests/test_synthesis_gate.py`

**Interfaces:**
- Produces: `is_cross_boundary(cluster, min_instances=2, min_scopes=2) -> bool`; `already_covered(cluster, existing: list[Promotion]) -> bool` (True iff the cluster's member names are a subset of some live promotion's source names).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_synthesis_gate.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from memory_read_provider import MemoryObservation
from promotion import Cluster, Promotion, SourceRef
from synthesis_pass import is_cross_boundary, already_covered


def _obs(subject, name):
    return MemoryObservation(type="project", subject=subject, name=name, description="d")

def test_single_scope_is_not_cross_boundary():
    c = Cluster("x", [_obs("LOGOS", "1"), _obs("LOGOS", "2")])
    assert not is_cross_boundary(c)

def test_two_scopes_two_members_is_cross_boundary():
    c = Cluster("x", [_obs("LOGOS", "1"), _obs("agent-swarm", "2")])
    assert is_cross_boundary(c)

def test_one_member_not_cross_boundary():
    c = Cluster("x", [_obs("LOGOS", "1")])
    assert not is_cross_boundary(c)

def test_already_covered_subset_true():
    c = Cluster("x", [_obs("LOGOS", "1"), _obs("agent-swarm", "2")])
    existing = [Promotion(id="p", scope="", title="", statement="",
                          sources=[SourceRef("1", "LOGOS"), SourceRef("2", "agent-swarm"),
                                   SourceRef("3", "user")],
                          instances=3, created_at="2026-08-15")]
    assert already_covered(c, existing)

def test_grown_cluster_is_covered():
    # cluster grew (existing sources subset of members) -> covered in v1 (refinement is slice 2)
    c = Cluster("x", [_obs("LOGOS", "1"), _obs("agent-swarm", "2"), _obs("user", "9")])
    existing = [Promotion(id="p", scope="", title="", statement="",
                          sources=[SourceRef("1", "LOGOS"), SourceRef("2", "agent-swarm")],
                          instances=2, created_at="2026-08-15")]
    assert already_covered(c, existing)

def test_distinct_overlap_not_covered():
    # shares one member but neither set nests the other -> distinct concept -> promote
    c = Cluster("x", [_obs("LOGOS", "1"), _obs("user", "9")])
    existing = [Promotion(id="p", scope="", title="", statement="",
                          sources=[SourceRef("1", "LOGOS"), SourceRef("2", "agent-swarm")],
                          instances=2, created_at="2026-08-15")]
    assert not already_covered(c, existing)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_synthesis_gate.py -q`
Expected: FAIL (`ModuleNotFoundError: synthesis_pass`).

- [ ] **Step 3: Implement the gate in `lib/synthesis_pass.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_synthesis_gate.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/synthesis_pass.py tests/test_synthesis_gate.py
git commit -m "feat(synthesis): convergence gate (cross-boundary + idempotence)"
```

---

### Task 6: Settling-pass orchestration (end-to-end, fakes)

**Files:**
- Modify: `lib/synthesis_pass.py` (append `run_synthesis` + `SynthesisResult`)
- Test: `tests/test_synthesis_pass.py`

**Interfaces:**
- Consumes: `MemoryReadProvider.list()`, `Clusterer.cluster`, `Drafter.draft`, `resolve_scope`, `VaultWriteProvider.write`, `PromotionStore.list`, gate functions.
- Produces: `run_synthesis(reader, writer, store, clusterer, drafter, vault_path, today=None) -> SynthesisResult` where `SynthesisResult(written: list[str], skipped: list[str])` (`written` = promotion ids; `skipped` = concept names rejected by the gate/affirmation/already-covered).

- [ ] **Step 1: Write the failing tests** (drives happy path AND the load-bearing run-twice convergence)

```python
# tests/test_synthesis_pass.py
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from memory_read_provider import MemoryObservation
from promotion import Cluster, PromotionDraft, Clusterer, Drafter, PromotionStore
from vault_write_provider import VaultWriteProvider
from synthesis_pass import run_synthesis


class FakeReader:
    def __init__(self, obs): self._obs = obs
    def list(self, type_=None, subject=None): return list(self._obs)

class FakeClusterer(Clusterer):
    def __init__(self, clusters): self._c = clusters
    def cluster(self, observations, existing): return list(self._c)

class FakeDrafter(Drafter):
    def __init__(self, consolidates=True): self._ok = consolidates
    def draft(self, cluster, scope):
        return PromotionDraft(title=cluster.concept, statement="cohesive " + cluster.concept,
                              consolidates=self._ok, justification="j")

def _obs(subject, name):
    return MemoryObservation(type="feedback", subject=subject, name=name, description="d")

def _vault(tmp_path):
    (tmp_path / "10-projects" / "LOGOS").mkdir(parents=True)
    (tmp_path / "10-projects" / "agent-swarm").mkdir(parents=True)
    return tmp_path

def _run(vault, obs, clusters, drafter=None):
    return run_synthesis(
        reader=FakeReader(obs),
        writer=VaultWriteProvider(vault_path=vault),
        store=PromotionStore(vault),
        clusterer=FakeClusterer(clusters),
        drafter=drafter or FakeDrafter(),
        vault_path=vault,
        today=date(2026, 8, 15),
    )

def test_promotes_cross_boundary_cluster(tmp_path):
    v = _vault(tmp_path)
    obs = [_obs("LOGOS", "l1"), _obs("agent-swarm", "a1")]
    clusters = [Cluster("verify-before-claiming", obs)]
    res = _run(v, obs, clusters)
    assert res.written == ["verify-before-claiming"]
    # sibling projects -> common prefix 10-projects
    assert (v / "10-projects/promotions/verify-before-claiming.md").is_file()

def test_skips_single_scope_cluster(tmp_path):
    v = _vault(tmp_path)
    obs = [_obs("LOGOS", "l1"), _obs("LOGOS", "l2")]
    res = _run(v, obs, [Cluster("local-thing", obs)])
    assert res.written == []
    assert "local-thing" in res.skipped

def test_skips_when_drafter_says_no_consolidation(tmp_path):
    v = _vault(tmp_path)
    obs = [_obs("LOGOS", "l1"), _obs("agent-swarm", "a1")]
    res = _run(v, obs, [Cluster("restate", obs)], drafter=FakeDrafter(consolidates=False))
    assert res.written == []

def test_second_run_is_noop_convergence(tmp_path):
    v = _vault(tmp_path)
    obs = [_obs("LOGOS", "l1"), _obs("agent-swarm", "a1")]
    clusters = [Cluster("verify-before-claiming", obs)]
    _run(v, obs, clusters)
    res2 = _run(v, obs, clusters)          # identical corpus + clusters
    assert res2.written == []              # nothing re-minted

def test_grown_cluster_does_not_proliferate(tmp_path):
    v = _vault(tmp_path)
    obs1 = [_obs("LOGOS", "l1"), _obs("agent-swarm", "a1")]
    _run(v, obs1, [Cluster("verify-before-claiming", obs1)])
    grown = obs1 + [_obs("user", "u1")]
    res2 = _run(v, grown, [Cluster("verify-before-claiming", grown)])
    assert res2.written == []              # existing sources subset of grown -> covered, no duplicate

def test_memory_is_never_written(tmp_path):
    # the pass only writes under promotions/; assert no .memory path is touched
    v = _vault(tmp_path)
    obs = [_obs("LOGOS", "l1"), _obs("agent-swarm", "a1")]
    _run(v, obs, [Cluster("c", obs)])
    assert not list(v.rglob(".memory/*"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_synthesis_pass.py -q`
Expected: FAIL (`ImportError: cannot import name 'run_synthesis'`).

- [ ] **Step 3: Implement `run_synthesis` + `SynthesisResult` in `lib/synthesis_pass.py`**

```python
from dataclasses import dataclass, field  # add to imports


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
        if not is_cross_boundary(cluster):
            result.skipped.append(cluster.concept)
            continue
        if already_covered(cluster, existing):
            result.skipped.append(cluster.concept)
            continue
        scope = resolve_scope([m.subject for m in cluster.members], vault_path)
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

    return result
```

Note on `promotion_id` slugging: `Cluster.concept` here uses the concept string as both display and slug seed; the fake tests pass slug-shaped concepts so `written == [concept]`. Real clusters go through `promotion_id()` which slugs arbitrary text.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_synthesis_pass.py -q`
Expected: PASS (5 tests, including the run-twice convergence).

- [ ] **Step 5: Commit**

```bash
git add lib/synthesis_pass.py tests/test_synthesis_pass.py
git commit -m "feat(synthesis): settling-pass orchestration + convergence (run-twice no-op)"
```

---

### Task 7: LLM-backed clusterer + drafter (behind the interfaces)

**Files:**
- Create: `lib/llm_synthesis.py`
- Test: `tests/test_llm_synthesis.py`

**Interfaces:**
- Produces:
  - `LLMRunner` protocol: `complete(prompt: str) -> str`.
  - `ClaudeCliRunner(model=None)` implementing it via `subprocess.run(["claude", "-p", prompt], ...)` returning stdout (mirrors the memory recorder's `claude -p` bridge; confirm flags against `memory/lib` at implementation time — this is the sole external-CLI coupling).
  - `LLMClusterer(runner)` and `LLMDrafter(runner)` — build prompts, parse the model's JSON, map to `Cluster` / `PromotionDraft`. Both tested with a fake runner returning canned JSON; no real CLI in tests.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_synthesis.py
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from memory_read_provider import MemoryObservation
from llm_synthesis import LLMClusterer, LLMDrafter
from promotion import Cluster


class FakeRunner:
    def __init__(self, payload): self._payload = payload
    def complete(self, prompt): return self._payload

def _obs(subject, name):
    return MemoryObservation(type="feedback", subject=subject, name=name, description="d-" + name)

def test_clusterer_maps_json_to_clusters():
    obs = [_obs("LOGOS", "l1"), _obs("agent-swarm", "a1"), _obs("user", "u1")]
    payload = json.dumps({"clusters": [
        {"concept": "verify before claiming", "members": ["l1", "a1"]}]})
    clusters = LLMClusterer(FakeRunner(payload)).cluster(obs, [])
    assert len(clusters) == 1
    assert clusters[0].concept == "verify before claiming"
    assert {m.name for m in clusters[0].members} == {"l1", "a1"}

def test_clusterer_drops_unknown_member_names():
    obs = [_obs("LOGOS", "l1")]
    payload = json.dumps({"clusters": [{"concept": "c", "members": ["l1", "ghost"]}]})
    clusters = LLMClusterer(FakeRunner(payload)).cluster(obs, [])
    assert {m.name for m in clusters[0].members} == {"l1"}

def test_clusterer_tolerates_garbage_json():
    assert LLMClusterer(FakeRunner("not json")).cluster([_obs("a", "x")], []) == []

def test_drafter_maps_json_to_draft():
    payload = json.dumps({"title": "Verify First", "statement": "S",
                          "consolidates": True, "justification": "j"})
    d = LLMDrafter(FakeRunner(payload)).draft(Cluster("c", [_obs("a", "x")]), "10-projects")
    assert d.title == "Verify First" and d.consolidates is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_llm_synthesis.py -q`
Expected: FAIL (`ModuleNotFoundError: llm_synthesis`).

- [ ] **Step 3: Implement `lib/llm_synthesis.py`**

```python
"""LLM-backed clusterer + drafter, behind the promotion.Clusterer/Drafter ABCs.

The only external coupling is ClaudeCliRunner (subprocess `claude -p`). All
parsing is deterministic and unit-tested with a fake runner.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional, Protocol

sys.path.insert(0, str(Path(__file__).parent))
from memory_read_provider import MemoryObservation  # noqa: E402
from promotion import Cluster, PromotionDraft, Clusterer, Drafter, Promotion  # noqa: E402


class LLMRunner(Protocol):
    def complete(self, prompt: str) -> str: ...


class ClaudeCliRunner:
    def __init__(self, model: Optional[str] = None, timeout: int = 120):
        self.model = model
        self.timeout = timeout

    def complete(self, prompt: str) -> str:
        cmd = ["claude", "-p", prompt]
        if self.model:
            cmd += ["--model", self.model]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"claude -p failed ({proc.returncode}): {proc.stderr.strip()}")
        return proc.stdout


def _obs_line(o: MemoryObservation) -> str:
    return f"- name={o.name} | scope={o.subject} | type={o.type} | {o.description}"


class LLMClusterer(Clusterer):
    def __init__(self, runner: LLMRunner):
        self.runner = runner

    def cluster(self, observations, existing) -> list[Cluster]:
        by_name = {o.name: o for o in observations}
        prompt = _CLUSTER_PROMPT.format(
            entries="\n".join(_obs_line(o) for o in observations),
            existing="\n".join(f"- {p.title}" for p in existing) or "(none)",
        )
        try:
            data = json.loads(self.runner.complete(prompt))
        except (ValueError, RuntimeError):
            return []
        out = []
        for c in data.get("clusters", []):
            members = [by_name[n] for n in c.get("members", []) if n in by_name]
            if members:
                out.append(Cluster(concept=str(c.get("concept", "")).strip(), members=members))
        return out


class LLMDrafter(Drafter):
    def __init__(self, runner: LLMRunner):
        self.runner = runner

    def draft(self, cluster: Cluster, scope: str) -> PromotionDraft:
        prompt = _DRAFT_PROMPT.format(
            concept=cluster.concept, scope=scope or "(vault root / user)",
            members="\n".join(_obs_line(o) for o in cluster.members),
        )
        try:
            data = json.loads(self.runner.complete(prompt))
        except (ValueError, RuntimeError):
            return PromotionDraft(title=cluster.concept, statement="", consolidates=False,
                                  justification="draft failed")
        return PromotionDraft(
            title=str(data.get("title", cluster.concept)).strip(),
            statement=str(data.get("statement", "")).strip(),
            consolidates=bool(data.get("consolidates", False)),
            justification=str(data.get("justification", "")).strip(),
        )


_CLUSTER_PROMPT = """You are continuity's synthesis step. Below are first-order memory
entries from across many projects. Identify concepts that RECUR across two or more
distinct scopes (the `scope=` field). Return ONLY JSON:
{{"clusters":[{{"concept":"<short name>","members":["<name>","<name>"]}}]}}
Only group entries that express the SAME underlying idea. Ignore single-scope repeats.
Existing promotions (do not recreate these):
{existing}

Entries:
{entries}
"""

_DRAFT_PROMPT = """Consolidate these recurring memory entries about "{concept}" (scope: {scope})
into one cohesive statement. Return ONLY JSON:
{{"title":"<short>","statement":"<the refined cohesive idea>","consolidates":<true|false>,"justification":"<one line>"}}
Set consolidates=false if these do not actually share one idea (a mere restatement).

Entries:
{members}
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_llm_synthesis.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/llm_synthesis.py tests/test_llm_synthesis.py
git commit -m "feat(synthesis): LLM clusterer+drafter behind interfaces (fake-runner tested)"
```

---

### Task 8: CLI entry — `continuity synthesize`

**Files:**
- Modify: `lib/cli.py` (add a `synthesize` subcommand) and `bin/continuity` if it dispatches explicitly.
- Test: `tests/test_cli_synthesize.py`

**Interfaces:**
- Consumes: `run_synthesis`, `MemoryReadProvider`, `VaultWriteProvider`, `PromotionStore`, `LLMClusterer`, `LLMDrafter`, `ClaudeCliRunner`, `VaultProvider` (for vault_path).
- Produces: `cmd_synthesize(argv, deps=None) -> int` — wires real providers by default; `deps` lets tests inject fakes. Prints `written N, skipped M`.

- [ ] **Step 1: Read `lib/cli.py` and `bin/continuity`** to match the existing subcommand dispatch pattern (argparse vs manual). Follow whatever pattern is there.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_cli_synthesize.py
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from memory_read_provider import MemoryObservation
from promotion import Cluster, PromotionDraft, Clusterer, Drafter, PromotionStore
from vault_write_provider import VaultWriteProvider
import cli


class _Reader:
    def __init__(self, o): self._o = o
    def list(self, type_=None, subject=None): return list(self._o)
class _Clusterer(Clusterer):
    def __init__(self, c): self._c = c
    def cluster(self, obs, existing): return list(self._c)
class _Drafter(Drafter):
    def draft(self, cluster, scope):
        return PromotionDraft(cluster.concept, "s", True, "j")

def test_cmd_synthesize_writes_and_reports(tmp_path, capsys):
    (tmp_path / "10-projects" / "LOGOS").mkdir(parents=True)
    (tmp_path / "10-projects" / "agent-swarm").mkdir(parents=True)
    obs = [MemoryObservation("feedback", "LOGOS", "l1", "d"),
           MemoryObservation("feedback", "agent-swarm", "a1", "d")]
    deps = dict(reader=_Reader(obs), writer=VaultWriteProvider(vault_path=tmp_path),
                store=PromotionStore(tmp_path), clusterer=_Clusterer([Cluster("cross", obs)]),
                drafter=_Drafter(), vault_path=tmp_path, today=date(2026, 8, 15))
    rc = cli.cmd_synthesize([], deps=deps)
    assert rc == 0
    assert "written 1" in capsys.readouterr().out
    assert (tmp_path / "10-projects/promotions/cross.md").is_file()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_cli_synthesize.py -q`
Expected: FAIL (`AttributeError: module 'cli' has no attribute 'cmd_synthesize'`).

- [ ] **Step 4: Implement `cmd_synthesize` in `lib/cli.py`**

```python
def cmd_synthesize(argv, deps=None) -> int:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from synthesis_pass import run_synthesis

    if deps is None:
        from memory_read_provider import MemoryReadProvider
        from vault_write_provider import VaultWriteProvider
        from vault_provider import VaultProvider
        from promotion import PromotionStore
        from llm_synthesis import ClaudeCliRunner, LLMClusterer, LLMDrafter
        vault_path = VaultProvider().vault_path
        runner = ClaudeCliRunner()
        deps = dict(reader=MemoryReadProvider(),
                    writer=VaultWriteProvider(vault_path=vault_path),
                    store=PromotionStore(vault_path),
                    clusterer=LLMClusterer(runner), drafter=LLMDrafter(runner),
                    vault_path=vault_path, today=None)

    res = run_synthesis(**deps)
    print(f"synthesis: written {len(res.written)}, skipped {len(res.skipped)}")
    return 0
```

Then register `synthesize` in the CLI dispatch (matching the existing pattern found in Step 1), routing to `cmd_synthesize(remaining_argv)`.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_cli_synthesize.py -q`
Expected: PASS.

- [ ] **Step 6: Run the full suite + commit**

Run: `python -m pytest -q`
Expected: all green (existing 134 + the new synthesis tests).

```bash
git add lib/cli.py bin/continuity tests/test_cli_synthesize.py
git commit -m "feat(synthesis): continuity synthesize CLI entry"
```

---

## Notes for the implementer

- **Do not add embeddings, an on-the-fly flagger, or refinement-supersession logic** — all deferred to slice 2. The `supersedes`/`superseded_by` fields exist in the record and `PromotionStore` already ignores superseded promotions, but v1 never *writes* a supersession; that lands in slice 2.
- **`sys.path.insert` sibling-import pattern** is the existing continuity convention (see `resume_brief.py`); follow it, don't introduce a package.
- **Every write goes through `VaultWriteProvider`** so atomicity/traversal-safety is inherited. Never write promotion files directly.
- **Convergence is by nested-set skip, not refinement (deviation from spec v1 step 7).** v1 promotes each concept once; a later cluster nested (identical/grown/shrunk) with an existing promotion is skipped, guaranteeing no proliferation. *Refreshing* a grown promotion (writing a superseding one with more sources) is deferred to slice 2. Flag for Chris: the spec put refine in v1; this plan moves the supersession write to slice 2 to keep v1 provably convergent and lean.
- **Structural seeding simplified (deviation from spec).** The spec framed shared links/entities as a cheap seed for the LLM clusterer. v1 feeds the full corpus (scope-labeled) to the LLM and lets it group; explicit `[[ref]]`/entity seeding is deferred. At ~700-1k entries this is feasible; revisit with the slice-2 embedding index.
- After the final task, open the PR (do not merge). Continuity's bar: all reviewer comments addressed + Greptile re-reviewed to 5/5 before it is merge-ready.
