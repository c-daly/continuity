# Promotions Are Memories — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A continuity promotion stops being a bespoke artifact in `<scope>/promotions/` and becomes an ordinary memory in `<entity>/.memory/`, written through `bin/memory write`, carrying links to the memories it consolidates.

**Architecture:** Synthesis writes promotions through `MemoryWriteProvider` so memory places, names, and indexes them. Provenance (which memories a promotion consolidates) lives in the body as a `Consolidates:` block of `[[links]]`, because `bin/memory write` has no extra-frontmatter channel. Reading provenance back is a direct scan of `.memory/*.md`, replacing `PromotionStore`. Links point promotion → sources only, so nothing mutates and append-only holds.

**Tech Stack:** Python 3.13, pytest, PyYAML, the `memory` plugin CLI (`bin/memory`).

**Spec:** `<vault>/10-projects/continuity/plans/2026-08-31-promotions-are-memories.md`

## Global Constraints

- Memory's valid types are exactly `{"user", "feedback", "project", "reference"}` (`memory/lib/memory_writer.py:20`). Continuity must not invent a fifth.
- Memory entry frontmatter requires all four of `name`, `description`, `type`, `subject` (`memory/lib/memory_reader.py:54`). A file missing any is skipped by memory's reader, not an error.
- `bin/memory write` accepts exactly `--type --name --subject --description`, body on stdin. There is no extra-frontmatter channel.
- Recall reads `MEMORY.md`, never the filesystem. A promotion not indexed there is never recalled.
- Append-only: nothing in this plan edits, overwrites, or deletes an existing memory entry.
- Vault is source of truth for specs/decisions; this repo holds the execution plan.
- Every task is TDD: failing test first, watch it fail, minimal implementation, watch it pass, commit.
- Run the full suite (`python3 -m pytest -q`) before every commit. It must stay green (244 passing at plan time).

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `lib/promotion.py` | Domain types; body format + provenance parsing; reader over `.memory/` | Modify — add 3 functions, replace `PromotionStore`, delete `promotion_to_frontmatter` |
| `lib/synthesis_pass.py` | Gate, type/subject derivation, orchestration | Modify |
| `lib/memory_write_provider.py` | Pass explicit memory fields through for `cont.promotion` | Modify |
| `lib/vault_write_provider.py` | Drop the promotion artifact path entirely | Modify — delete |
| `tests/test_promotion.py` | Body format + provenance parsing + reader | Modify |
| `tests/test_synthesis_pass.py` | Type/subject derivation, corpus filter, write path | Modify |
| `tests/test_memory_write_provider.py` | Promotion pass-through | Modify |
| `tests/test_vault_write_provider.py` | Remove promotion cases | Modify |
| `tests/test_promotion_store.py` | Superseded by the `.memory/` reader tests | Delete |
| `tests/test_synthesis_end_to_end.py` | Real `bin/memory`, real vault | Create |
| `README.md` | State the memories-go-through-memory scoping | Modify |

---

## Task 1: Promotion body format and provenance parsing

**Files:**
- Modify: `lib/promotion.py`
- Test: `tests/test_promotion.py`

**Interfaces:**
- Consumes: `SourceRef` (existing, `lib/promotion.py:21`)
- Produces:
  - `promotion_body(statement: str, sources: list[SourceRef]) -> str`
  - `parse_consolidates(body: str) -> Optional[list[str]]` — source names in file order, or `None` when the body has no `Consolidates:` block

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_promotion.py`:

```python
from promotion import SourceRef, promotion_body, parse_consolidates


def test_promotion_body_lists_sources_as_wiki_links():
    body = promotion_body(
        "Recall is activation over distilled structure, not passage retrieval.",
        [SourceRef("hcg-not-rag", "LOGOS"), SourceRef("hcg-retrieval-is-rag-without-passages", "logos")],
    )

    assert "Recall is activation over distilled structure" in body
    assert "Consolidates:" in body
    assert "- [[hcg-not-rag]]" in body
    assert "- [[hcg-retrieval-is-rag-without-passages]]" in body


def test_parse_consolidates_round_trips_the_source_names():
    """The body is the only provenance channel — bin/memory write takes no
    extra frontmatter — so the dedup gate reads its source set back from here."""
    sources = [SourceRef("a-name", "LOGOS"), SourceRef("b-name", "memory")]
    body = promotion_body("Statement.", sources)

    assert parse_consolidates(body) == ["a-name", "b-name"]


def test_parse_consolidates_returns_none_for_an_ordinary_memory():
    """Every memory now shares a directory with promotions, so 'is this a
    promotion?' is answered by the marker, not by location."""
    assert parse_consolidates("Just a normal memory body.\n\nWith [[a-link]].\n") is None


def test_parse_consolidates_tolerates_the_provenance_header():
    """MemoryWriteProvider prefixes bodies with Source/Kind/Id lines."""
    body = "Source: continuity\nKind: cont.promotion\nId: x\n\n" + promotion_body(
        "S.", [SourceRef("only-one", "LOGOS")]
    )

    assert parse_consolidates(body) == ["only-one"]


def test_parse_consolidates_ignores_links_outside_the_block():
    body = promotion_body("See [[unrelated]] for context.", [SourceRef("real-source", "LOGOS")])

    assert parse_consolidates(body) == ["real-source"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_promotion.py -q`
Expected: FAIL with `ImportError: cannot import name 'promotion_body'`

- [ ] **Step 3: Write minimal implementation**

Add to `lib/promotion.py`, after `promotion_id`:

```python
_CONSOLIDATES_MARKER = "Consolidates:"
_LINK_RE = re.compile(r"^\s*-\s*\[\[([^\]]+)\]\]\s*$")


def promotion_body(statement: str, sources: list[SourceRef]) -> str:
    """Render a promotion's body: the settled statement, then its lineage.

    `bin/memory write` accepts no extra frontmatter, so the body is the only
    channel provenance has. Links point promotion -> sources and never the
    reverse, which is what keeps memory append-only: nothing edits the
    originals.
    """
    lines = [statement.rstrip(), "", _CONSOLIDATES_MARKER]
    lines.extend(f"- [[{s.name}]]" for s in sources)
    return "\n".join(lines) + "\n"


def parse_consolidates(body: str) -> Optional[list[str]]:
    """Source names from a promotion body, or None if this is not a promotion.

    Promotions share `.memory/` with every ordinary entry, so the marker — not
    the file's location — is what identifies one. Only links inside the block
    count; a link in the prose above it is not a source.
    """
    lines = body.splitlines()
    try:
        start = next(i for i, line in enumerate(lines)
                     if line.strip() == _CONSOLIDATES_MARKER)
    except StopIteration:
        return None
    names = []
    for line in lines[start + 1:]:
        match = _LINK_RE.match(line)
        if match is None:
            if line.strip():
                break        # the block ends at the first non-link content
            continue
        names.append(match.group(1).strip())
    return names
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_promotion.py -q`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add lib/promotion.py tests/test_promotion.py
git commit -m "feat(promotion): body carries lineage as links to its sources"
```

---

## Task 2: Memory write provider passes promotion fields through

**Files:**
- Modify: `lib/memory_write_provider.py:22` (`_KIND_TO_MEMORY_TYPE`), `lib/memory_write_provider.py:121` (`_map_to_memory`)
- Test: `tests/test_memory_write_provider.py`

**Interfaces:**
- Consumes: nothing from Task 1
- Produces: `MemoryWriteProvider.write("cont.promotion", name, {"type": str, "subject": str, "description": str}, body)` writes a memory entry with those exact fields.

A promotion's type is derived per-cluster (Task 4), so it cannot come from the static `_KIND_TO_MEMORY_TYPE` map the way `cont.insight` does. The caller supplies it.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_memory_write_provider.py`:

```python
def test_promotion_passes_its_fields_through_verbatim(tmp_path, monkeypatch):
    """A promotion's type is derived from its sources, so unlike cont.insight
    it cannot come from a static kind->type map. The caller supplies all four
    memory fields and the provider passes them straight to the CLI."""
    args_file = tmp_path / "args.txt"
    memory_bin = tmp_path / "memory"
    memory_bin.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > " + str(args_file) + "\ncat > /dev/null\n"
    )
    memory_bin.chmod(0o755)
    monkeypatch.setenv("MEMORY_BIN", str(memory_bin))

    MemoryWriteProvider().write(
        "cont.promotion",
        "recall-is-activation",
        {"type": "feedback", "subject": "LOGOS", "description": "The settled statement."},
        "body",
    )

    args = args_file.read_text().split("\n")
    assert "feedback" in args
    assert "LOGOS" in args
    assert "recall-is-activation" in args
    assert "The settled statement." in args


def test_promotion_rejects_a_type_memory_will_not_accept(tmp_path, monkeypatch):
    """Fail here with a clear message rather than at the CLI boundary."""
    monkeypatch.setenv("MEMORY_BIN", str(tmp_path / "memory"))

    with pytest.raises(ValueError, match="invalid memory type"):
        MemoryWriteProvider().write(
            "cont.promotion",
            "x",
            {"type": "synthesis", "subject": "LOGOS", "description": "d"},
            "body",
        )


def test_promotion_requires_subject_and_description(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_BIN", str(tmp_path / "memory"))

    for missing in ("subject", "description"):
        fm = {"type": "project", "subject": "LOGOS", "description": "d"}
        del fm[missing]
        with pytest.raises(ValueError, match=missing):
            MemoryWriteProvider().write("cont.promotion", "x", fm, "body")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_memory_write_provider.py -q`
Expected: FAIL with `ValueError: Unknown kind: 'cont.promotion'`

- [ ] **Step 3: Write minimal implementation**

In `lib/memory_write_provider.py`, add the constant next to `_KIND_TO_MEMORY_TYPE`:

```python
_PROMOTION_KIND = "cont.promotion"
# memory owns the canonical list (memory/lib/memory_writer.py VALID_TYPES);
# mirrored here only to fail with a clear message before the CLI boundary.
_MEMORY_TYPES = {"user", "feedback", "project", "reference"}
```

Then add this branch at the top of `_map_to_memory`, before `memory_type = _memory_type_for_kind(kind)`:

```python
    if kind == _PROMOTION_KIND:
        validate_basename(id, "id")
        memory_type = str(frontmatter.get("type") or "").strip()
        if memory_type not in _MEMORY_TYPES:
            raise ValueError(
                f"invalid memory type: {memory_type!r}; "
                f"expected one of {sorted(_MEMORY_TYPES)!r}"
            )
        subject = str(frontmatter.get("subject") or "").strip()
        if not subject:
            raise ValueError("promotion requires 'subject' in frontmatter")
        description = _collapse_spaces(str(frontmatter.get("description") or ""))
        if not description:
            raise ValueError("promotion requires 'description' in frontmatter")
        validate_relpath(subject, "subject")
        return {
            "type": memory_type,
            "subject": subject.rsplit("/", 1)[-1],
            "name": id,
            "description": description,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_memory_write_provider.py -q`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add lib/memory_write_provider.py tests/test_memory_write_provider.py
git commit -m "feat(memory-bridge): pass promotion fields through to the CLI"
```

---

## Task 3: Read promotions back from `.memory/`

**Files:**
- Modify: `lib/promotion.py` (replace `PromotionStore`, lines 88-124)
- Test: `tests/test_promotion_store.py` (rewrite in place)

**Interfaces:**
- Consumes: `parse_consolidates` (Task 1)
- Produces: `MemoryPromotionStore(vault_path).list() -> list[Promotion]`

`bin/memory list` returns only `type`, `subject`, `name`, `description` — no body — so the dedup gate cannot get a promotion's source set through it. Reading the files directly is one pass over `.memory/` and needs no cross-plugin change.

- [ ] **Step 1: Write the failing tests**

Replace the contents of `tests/test_promotion_store.py`:

```python
"""Reading promotions back out of .memory/.

Promotions are ordinary memories now, so they are identified by the
Consolidates: marker in their body rather than by living in a promotions/
directory. bin/memory list does not return bodies, so this reads the files.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from promotion import MemoryPromotionStore, SourceRef, promotion_body


def _entry(vault, entity, name, body, subject="LOGOS"):
    d = vault / entity / ".memory"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"2026-08-31-{name}.md").write_text(
        f"---\nname: {name}\ndescription: d\ntype: project\nsubject: {subject}\n---\n{body}"
    )


def test_lists_promotions_and_their_sources(tmp_path):
    _entry(tmp_path, "10-projects/LOGOS", "settled-idea",
           promotion_body("S.", [SourceRef("a", "LOGOS"), SourceRef("b", "memory")]))

    promotions = MemoryPromotionStore(tmp_path).list()

    assert len(promotions) == 1
    assert promotions[0].id == "settled-idea"
    assert sorted(s.name for s in promotions[0].sources) == ["a", "b"]


def test_ignores_ordinary_memories(tmp_path):
    """The corpus is mostly first-order entries; only the marker makes a promotion."""
    _entry(tmp_path, "10-projects/LOGOS", "settled-idea",
           promotion_body("S.", [SourceRef("a", "LOGOS")]))
    _entry(tmp_path, "10-projects/LOGOS", "ordinary", "Just an observation.\n")

    assert [p.id for p in MemoryPromotionStore(tmp_path).list()] == ["settled-idea"]


def test_finds_promotions_at_every_scope(tmp_path):
    _entry(tmp_path, ".", "root-level", promotion_body("S.", [SourceRef("a", "x")]), subject="user")
    _entry(tmp_path, "10-projects/LOGOS/sophia", "sub-level",
           promotion_body("S.", [SourceRef("b", "y")]), subject="sophia")

    assert sorted(p.id for p in MemoryPromotionStore(tmp_path).list()) == [
        "root-level", "sub-level",
    ]


def test_id_strips_the_date_prefix_memory_adds(tmp_path):
    """memory names files YYYY-MM-DD-<name>.md; the promotion id is the name."""
    _entry(tmp_path, "10-projects/LOGOS", "my-concept",
           promotion_body("S.", [SourceRef("a", "LOGOS")]))

    assert MemoryPromotionStore(tmp_path).list()[0].id == "my-concept"


def test_one_unreadable_file_never_crashes_the_listing(tmp_path):
    _entry(tmp_path, "10-projects/LOGOS", "good",
           promotion_body("S.", [SourceRef("a", "LOGOS")]))
    bad = tmp_path / "10-projects/LOGOS/.memory/2026-08-31-bad.md"
    bad.write_bytes(b"---\n\xff\xfe not utf-8\n---\n")

    assert [p.id for p in MemoryPromotionStore(tmp_path).list()] == ["good"]


def test_no_memory_dirs_is_empty_not_an_error(tmp_path):
    assert MemoryPromotionStore(tmp_path).list() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_promotion_store.py -q`
Expected: FAIL with `ImportError: cannot import name 'MemoryPromotionStore'`

- [ ] **Step 3: Write minimal implementation**

In `lib/promotion.py`, delete `promotion_to_frontmatter` (lines 75-85) and the whole `PromotionStore` class (lines 88-124). Replace with:

```python
_DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")


class MemoryPromotionStore:
    """Reads live promotions from the vault's .memory/ directories.

    Promotions are ordinary memory entries, so they are found by the
    Consolidates: marker in the body rather than by a dedicated directory.
    `bin/memory list` does not return bodies, which is why this reads files
    directly instead of going through the CLI.
    """

    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path)

    def list(self) -> list[Promotion]:
        out: list[Promotion] = []
        for f in sorted(self.vault_path.rglob(".memory/*.md")):
            try:
                text = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue  # one bad file must never crash the vault-wide list
            body = text.split("---", 2)[-1] if text.startswith("---") else text
            names = parse_consolidates(body)
            if not names:
                continue
            scope = f.parent.parent.relative_to(self.vault_path).as_posix()
            out.append(Promotion(
                id=_DATE_PREFIX_RE.sub("", f.stem),
                scope="" if scope == "." else scope,
                title="",
                statement="",
                sources=[SourceRef(n, "") for n in names],
                instances=len(names),
                created_at="",
            ))
        return out
```

Remove the now-unused `yaml` import if nothing else in the module uses it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_promotion_store.py -q`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`
Expected: `tests/test_synthesis_pass.py` fails on `promotion_to_frontmatter` — that is Task 5's work. Note the failures and continue.

- [ ] **Step 6: Commit**

```bash
git add lib/promotion.py tests/test_promotion_store.py
git commit -m "feat(promotion): read promotions from .memory/ by their lineage marker"
```

---

## Task 4: Test scaffolding, plus a promotion's type and subject

**Files:**
- Modify: `lib/synthesis_pass.py`
- Test: `tests/test_synthesis_pass.py:25` (`_obs`), and new fakes at the top of the file

**Interfaces:**
- Consumes: `Cluster` (existing), `MemoryObservation.type` (`lib/memory_read_provider.py:38`)
- Produces:
  - `promotion_type(cluster: Cluster) -> str`
  - `scope_to_subject(scope: str) -> str`
  - test-only: `FakeWriter` (records `(kind, id, frontmatter, body)` in `.calls`), `FakeStore` (returns a fixed promotion list), `_obs(subject, name, type="feedback")`

**Why the scaffolding comes first:** today `tests/test_synthesis_pass.py` runs the
*real* `VaultWriteProvider` and `PromotionStore` against a temp vault. After Task 5
the writer is `MemoryWriteProvider`, which shells out to `bin/memory` — so keeping
that style would make every unit test in the file spawn subprocesses and depend on
the memory plugin. The fakes keep these tests hermetic; Task 8 is where the real
CLI gets exercised, once.

- [ ] **Step 1: Add the fakes and widen `_obs`**

In `tests/test_synthesis_pass.py`, add after `FakeDrafter`:

```python
class FakeWriter:
    """Records writes instead of shelling out. The real memory CLI is
    exercised once, in tests/test_synthesis_end_to_end.py."""
    def __init__(self): self.calls = []
    def write(self, kind, id, frontmatter, body):
        self.calls.append((kind, id, frontmatter, body))

class FakeStore:
    def __init__(self, promotions=None): self._p = list(promotions or [])
    def list(self): return list(self._p)
```

Change `_obs` to carry a type, defaulting to today's value so existing call
sites are untouched:

```python
def _obs(subject, name, type="feedback"):
    return MemoryObservation(type=type, subject=subject, name=name, description="d")
```

Point `_run` at the fakes:

```python
def _run(vault, obs, clusters, drafter=None, writer=None, store=None):
    return run_synthesis(
        reader=FakeReader(obs),
        writer=writer or FakeWriter(),
        store=store or FakeStore(),
        clusterer=FakeClusterer(clusters),
        drafter=drafter or FakeDrafter(),
        vault_path=vault,
        today=date(2026, 8, 15),
    )
```

- [ ] **Step 2: Run the suite to see what the switch breaks**

Run: `python3 -m pytest tests/test_synthesis_pass.py -q`
Expected: existing tests that assert on files written into the temp vault now
fail, because `FakeWriter` writes nothing. Convert each to assert on
`writer.calls` instead — pass an explicit `FakeWriter` into `_run` and inspect
it. Do not weaken an assertion: a test that checked a file landed at a path
should now check the `(kind, id, frontmatter)` that would place it there.

- [ ] **Step 3: Write the failing tests for the derivation helpers**

```python
from synthesis_pass import promotion_type, scope_to_subject


def test_promotion_inherits_a_unanimous_source_type():
    """A promotion over five feedback entries is feedback. Once promoted it is
    just a memory, so it takes one of memory's four existing types."""
    cluster = Cluster("c", [_obs("LOGOS", "a", "feedback"), _obs("memory", "b", "feedback")])

    assert promotion_type(cluster) == "feedback"


def test_promotion_falls_back_to_project_on_mixed_types():
    cluster = Cluster("c", [_obs("LOGOS", "a", "project"), _obs("memory", "b", "reference")])

    assert promotion_type(cluster) == "project"


def test_promotion_type_is_always_one_memory_accepts():
    """An unknown type from a malformed observation must not reach the CLI."""
    cluster = Cluster("c", [_obs("LOGOS", "a", "nonsense"), _obs("memory", "b", "nonsense")])

    assert promotion_type(cluster) == "project"


def test_scope_to_subject_maps_every_shape():
    assert scope_to_subject("") == "user"                       # vault root
    assert scope_to_subject("10-projects") == "10-projects"     # sibling projects
    assert scope_to_subject("10-projects/LOGOS") == "LOGOS"
    assert scope_to_subject("10-projects/LOGOS/sophia") == "sophia"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_synthesis_pass.py -q -k "promotion_type or scope_to_subject"`
Expected: FAIL with `ImportError: cannot import name 'promotion_type'`

- [ ] **Step 5: Write minimal implementation**

Add to `lib/synthesis_pass.py`, after the `MIN_SCOPES` constant:

```python
# memory owns the canonical list; mirrored to keep a malformed observation's
# type from reaching the CLI.
_MEMORY_TYPES = {"user", "feedback", "project", "reference"}
_DEFAULT_TYPE = "project"


def promotion_type(cluster: Cluster) -> str:
    """The type a promotion inherits from the memories it consolidates.

    Unanimous sources hand their type down; anything else falls back to
    `project`. Deterministic and free — no LLM call — and a promotion over five
    `feedback` entries reads as feedback, which is what it is.
    """
    types = {m.type for m in cluster.members}
    if len(types) == 1:
        only = types.pop()
        if only in _MEMORY_TYPES:
            return only
    return _DEFAULT_TYPE


def scope_to_subject(scope: str) -> str:
    """Map a resolved vault scope to the subject memory addresses it by.

    memory takes an entity NAME and resolves nesting itself, so the leaf is
    what it wants. The empty scope is the vault root, which memory calls
    `user`; `10-projects` is itself an addressable entity (it has its own
    .memory/), so it needs no special case.
    """
    return scope.rsplit("/", 1)[-1] if scope else "user"
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_synthesis_pass.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add lib/synthesis_pass.py tests/test_synthesis_pass.py
git commit -m "feat(synthesis): derive a promotion's memory type and subject"
```

---

## Task 5: Write promotions through the memory path

**Files:**
- Modify: `lib/synthesis_pass.py:12-13` (imports), `lib/synthesis_pass.py:78-85` (write), `lib/synthesis_pass.py:93-113` (`default_synthesis_deps`)
- Test: `tests/test_synthesis_pass.py`

**Interfaces:**
- Consumes: `promotion_body` (Task 1), `MemoryWriteProvider` promotion branch (Task 2), `MemoryPromotionStore` (Task 3), `promotion_type` / `scope_to_subject` (Task 4)
- Produces: `run_synthesis` calls `writer.write("cont.promotion", pid, {"type", "subject", "description"}, promotion_body(...))`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_synthesis_pass.py`:

```python
def test_writes_a_promotion_as_a_memory_entry(tmp_path):
    """The write carries the four fields memory requires and a body whose
    lineage links back to the sources."""
    writer = FakeWriter()
    cluster = Cluster("recall is activation", [
        _obs("LOGOS", "hcg-not-rag", "feedback"),
        _obs("sophia", "hcg-no-passages", "feedback"),
    ])
    run_synthesis(FakeReader(cluster.members), writer, FakeStore([]),
                  FakeClusterer([cluster]), FakeDrafter(consolidates=True),
                  vault_path=_vault(tmp_path), today=date(2026, 8, 31))

    kind, pid, fm, body = writer.calls[0]
    assert kind == "cont.promotion"
    assert fm["type"] == "feedback"
    assert fm["subject"] == "LOGOS"
    assert fm["description"]
    assert "- [[hcg-not-rag]]" in body
    assert "- [[hcg-no-passages]]" in body


def test_a_rejected_write_skips_the_cluster_and_the_pass_continues(tmp_path):
    """A promotion slug can now collide with any of ~700 memory names. memory
    refuses an existing location, which is correct — synthesis must treat it as
    a skipped cluster, not a failed pass."""
    class RejectingWriter:
        def __init__(self):
            self.calls = []
        def write(self, kind, id, fm, body):
            self.calls.append(id)
            if len(self.calls) == 1:
                raise RuntimeError("memory write failed: already exists")

    first = Cluster("concept one", [_obs("LOGOS", "a"), _obs("memory", "b")])
    second = Cluster("concept two", [_obs("LOGOS", "c"), _obs("memory", "d")])
    writer = RejectingWriter()

    result = run_synthesis(FakeReader(first.members + second.members), writer,
                           FakeStore([]), FakeClusterer([first, second]),
                           FakeDrafter(consolidates=True),
                           vault_path=_vault(tmp_path), today=date(2026, 8, 31))

    assert result.skipped == ["concept one"]
    assert result.written == ["concept-two"]
```

`FakeWriter`, `FakeStore` and the widened `_obs` come from Task 4. `FakeReader`, `FakeClusterer`, `FakeDrafter` and `_vault` already exist at the top of the file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_synthesis_pass.py -q`
Expected: FAIL — `promotion_to_frontmatter` no longer exists (removed in Task 3)

- [ ] **Step 3: Write minimal implementation**

In `lib/synthesis_pass.py`, change the import on lines 12-13 to:

```python
from promotion import (Cluster, Promotion, SourceRef, Clusterer, Drafter,
                       promotion_id, promotion_body)  # noqa: E402
```

Replace the write (line 83) and the `Promotion` construction above it with:

```python
            sources = [SourceRef(m.name, m.subject) for m in cluster.members]
            promo = Promotion(
                id=pid, scope=scope, title=draft.title, statement=draft.statement,
                sources=sources, instances=len(cluster.members), created_at=when,
            )
            writer.write(
                "cont.promotion",
                pid,
                {
                    "type": promotion_type(cluster),
                    "subject": scope_to_subject(scope),
                    "description": draft.statement,
                },
                promotion_body(draft.statement, sources),
            )
```

Then update `default_synthesis_deps` to wire the memory writer and the new store:

```python
    from memory_read_provider import MemoryReadProvider
    from memory_write_provider import MemoryWriteProvider
    from vault_provider import VaultProvider
    from promotion import MemoryPromotionStore
    from llm_synthesis import ClaudeCliRunner, LLMClusterer, LLMDrafter

    vault_path = VaultProvider().vault_path
    runner = ClaudeCliRunner()
    # Promotions are memories, so they always go through memory's writer —
    # that is what indexes them in MEMORY.md and makes them recallable.
    # `write_provider: memory` still governs cont.insight only.
    return dict(reader=MemoryReadProvider(),
                writer=MemoryWriteProvider(),
                store=MemoryPromotionStore(vault_path),
                clusterer=LLMClusterer(runner), drafter=LLMDrafter(runner),
                vault_path=vault_path, today=None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_synthesis_pass.py -q`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add lib/synthesis_pass.py tests/test_synthesis_pass.py
git commit -m "feat(synthesis): write promotions through memory so they are recalled"
```

---

## Task 6: Prove a promotion can itself be promoted

**Files:**
- Test: `tests/test_synthesis_pass.py`

**Interfaces:**
- Consumes: everything from Task 5. No implementation — this pins behaviour that
  must already work.

Promotions being memories is what allows synthesis to operate on its own output.
No filter keeps them out of the corpus; the gate is what prevents runaway. These
tests pin both halves, so a future "tidy-up" cannot quietly reintroduce a filter.

- [ ] **Step 1: Write the tests**

```python
def test_a_promotion_can_be_consolidated_further(tmp_path):
    """Higher-order promotion is the point of promotions being memories: a
    settled idea plus a new instance settles again, one level up."""
    settled = _obs("LOGOS", "already-settled")
    fresh = _obs("memory", "new-instance")
    writer = FakeWriter()

    run_synthesis(
        reader=FakeReader([settled, fresh]), writer=writer,
        store=FakeStore([Promotion(
            id="already-settled", scope="10-projects/LOGOS", title="", statement="",
            sources=[SourceRef("a", "LOGOS"), SourceRef("b", "memory")],
            instances=2, created_at="2026-08-30")]),
        clusterer=FakeClusterer([Cluster("broader idea", [settled, fresh])]),
        drafter=FakeDrafter(consolidates=True),
        vault_path=_vault(tmp_path), today=date(2026, 8, 31),
    )

    kind, pid, fm, body = writer.calls[0]
    assert pid == "broader-idea"
    assert "- [[already-settled]]" in body   # lineage points at the promotion
    assert "- [[new-instance]]" in body


def test_an_unchanged_promotion_is_not_reminted(tmp_path):
    """Convergence comes from the gate, not from excluding promotions: a
    re-cluster of a promotion with its own sources is already covered."""
    members = [_obs("LOGOS", "a"), _obs("memory", "b")]
    settled = _obs("LOGOS", "already-settled")
    writer = FakeWriter()

    result = run_synthesis(
        reader=FakeReader(members + [settled]), writer=writer,
        store=FakeStore([Promotion(
            id="already-settled", scope="10-projects/LOGOS", title="", statement="",
            sources=[SourceRef("a", "LOGOS"), SourceRef("b", "memory")],
            instances=2, created_at="2026-08-30")]),
        clusterer=FakeClusterer([Cluster("same idea", members + [settled])]),
        drafter=FakeDrafter(consolidates=True),
        vault_path=_vault(tmp_path), today=date(2026, 8, 31),
    )

    assert writer.calls == []
    assert result.skipped == ["same idea"]
```

- [ ] **Step 2: Run them**

Run: `python3 -m pytest tests/test_synthesis_pass.py -q -k "consolidated_further or reminted"`
Expected: PASS with no implementation change. If either fails, Task 5 is wrong —
fix there.

- [ ] **Step 3: Commit**

```bash
git add tests/test_synthesis_pass.py
git commit -m "test(synthesis): pin that promotions can themselves be promoted"
```

---

## Task 7: Delete the promotion artifact path from the vault writer

**Files:**
- Modify: `lib/vault_write_provider.py` — remove `_PROMOTION_KIND` (line 32), `_PROMOTION_SUBDIR` (line 33), the `exists()` promotion branch (lines 146-148), the `write()` promotion branch (line 111), and `_resolve_promotion` (lines 190-196)
- Test: `tests/test_vault_write_provider.py` — remove promotion cases

**Interfaces:**
- Consumes: nothing
- Produces: nothing — `VaultWriteProvider` handles `cont.insight` and `cont.decision` only

Nothing writes `cont.promotion` through the vault provider after Task 5. Leaving a second, unreachable placement path is how the two-writers-disagree bug from PR #13 happened.

- [ ] **Step 1: Write the failing test**

```python
def test_vault_provider_no_longer_accepts_promotions(fake_vault):
    """Promotions go through memory now. A second placement path that nothing
    calls is exactly how the writers came to disagree in #13."""
    wp = VaultWriteProvider(vault_path=fake_vault)

    with pytest.raises(ValueError, match="Unknown kind"):
        wp.write("cont.promotion", "x", {"scope": "10-projects/LOGOS"}, "b")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_vault_write_provider.py -q -k no_longer_accepts`
Expected: FAIL — no exception raised; the write succeeds

- [ ] **Step 3: Remove the promotion path**

Delete from `lib/vault_write_provider.py`:
- the `_PROMOTION_KIND` and `_PROMOTION_SUBDIR` constants
- the `if kind == _PROMOTION_KIND:` branch in `write()` and in `exists()`
- the `_resolve_promotion` method entirely

Delete every test in `tests/test_vault_write_provider.py` that references `cont.promotion` or `promotions/`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_vault_write_provider.py -q`
Expected: PASS

- [ ] **Step 5: Run the full suite and commit**

```bash
python3 -m pytest -q
git add lib/vault_write_provider.py tests/test_vault_write_provider.py
git commit -m "refactor(vault): drop the promotion placement path nothing calls"
```

---

## Task 8: End-to-end against a real `bin/memory`, and document the scoping

**Files:**
- Create: `tests/test_synthesis_end_to_end.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above

Every prior task uses fakes. This is the one that proves the actual outcome: a promotion lands in the right `.memory/`, reaches `MEMORY.md`, and comes back from `bin/memory list`. Without it the whole change could pass its tests and still not be recalled — which was the entire point.

- [ ] **Step 1: Write the failing test**

```python
"""Synthesis end to end against a real memory CLI.

Everything else in the suite uses fakes. The point of this change is that a
promotion becomes recallable, and recall goes through MEMORY.md — so the only
test that proves it is one that runs the real writer and reads the real index.
"""
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from memory_write_provider import MemoryWriteProvider
from promotion import Cluster, MemoryPromotionStore, SourceRef
from synthesis_pass import run_synthesis

MEMORY_BIN = Path(os.environ.get(
    "MEMORY_BIN", Path.home() / ".claude" / "plugins" / "memory" / "bin" / "memory"))

pytestmark = pytest.mark.skipif(
    not MEMORY_BIN.exists(), reason="memory plugin CLI not installed"
)


def test_promotion_lands_in_memory_and_is_recallable(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "10-projects" / "LOGOS").mkdir(parents=True)
    (vault / "10-projects" / "LOGOS" / "narrative.md").write_text("# LOGOS\n")
    monkeypatch.setenv("MEMORY_VAULT_DIR", str(vault))
    monkeypatch.setenv("CONTINUITY_VAULT_DIR", str(vault))

    members = [
        MemoryObservation(type="feedback", subject="LOGOS", name="src-one", description="d"),
        MemoryObservation(type="feedback", subject="LOGOS", name="src-two", description="d"),
    ]
    cluster = Cluster("the settled concept", members)

    result = run_synthesis(
        FakeReader(members), MemoryWriteProvider(memory_bin=MEMORY_BIN),
        MemoryPromotionStore(vault), FakeClusterer([cluster]),
        FakeDrafter(consolidates=True), vault_path=vault, today=date(2026, 8, 31),
    )

    assert result.written == ["the-settled-concept"]

    # 1. the file is where memories for that entity live
    written = list((vault / "10-projects" / "LOGOS" / ".memory").glob("*.md"))
    assert len(written) == 1
    assert written[0].name.startswith("2026-08-31-")

    # 2. it reached the index, which is what recall reads
    assert "the-settled-concept" in (vault / "MEMORY.md").read_text()

    # 3. and it comes back as an ordinary memory
    listed = subprocess.run(
        [str(MEMORY_BIN), "list", "--subject", "LOGOS"],
        capture_output=True, text=True, env={**os.environ, "MEMORY_VAULT_DIR": str(vault)},
    )
    assert "the-settled-concept" in listed.stdout

    # 4. and it is a promotion, with its lineage intact
    assert sorted(s.name for s in MemoryPromotionStore(vault).list()[0].sources) == [
        "src-one", "src-two",
    ]
```

Import `MemoryObservation` from `memory_read_provider`, and copy `FakeReader`, `FakeClusterer` and `FakeDrafter` from `tests/test_synthesis_pass.py` or import them if they are module-level there.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_synthesis_end_to_end.py -q`
Expected: FAIL (or SKIP if the memory CLI is absent — if it skips, install/point `MEMORY_BIN` before continuing; a skipped test proves nothing here)

- [ ] **Step 3: Fix whatever it surfaces**

No new implementation is planned for this task. If it fails, the defect is in Tasks 1-7 and this is the test that found it — fix there, not here.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_synthesis_end_to_end.py -q`
Expected: PASS

- [ ] **Step 5: Update the README**

In `README.md`, under `## Write providers`, add:

```markdown
Promotions are an exception to the `write_provider` setting: they always go
through the memory plugin, because a promotion *is* a memory and only memory's
writer indexes it in `MEMORY.md`, which is what every recall path reads. The
`write_provider` setting governs `cont.insight` only. This is scoping, not
drift — memories go through memory; insights keep the vault default.
```

- [ ] **Step 6: Run the full suite and commit**

```bash
python3 -m pytest -q
python3 -m ruff check lib/ tests/
git add tests/test_synthesis_end_to_end.py README.md
git commit -m "test(synthesis): prove a promotion is recallable end to end"
```

---

## Mutation checks before opening the PR

Match the bar set in PRs #12 and #13. Each mutation must fail at least one test:

| Mutation | Must fail |
|---|---|
| `promotion_body` drops the `Consolidates:` block | Task 1 round-trip, Task 3 listing |
| `parse_consolidates` returns `[]` instead of `None` for a plain memory | Task 3 `ignores_ordinary_memories` |
| `promotion_type` always returns `"project"` | Task 4 unanimous-inheritance |
| `scope_to_subject` returns the whole scope instead of the leaf | Task 4 mapping, Task 8 placement |
| A filter is added that keeps promotions out of the corpus | Task 6 `consolidated_further` |
| `run_synthesis` lets a write rejection propagate | Task 5 rejection test |

Run each by editing the source, running `python3 -m pytest -q`, confirming the expected failure, then restoring.

---

## Self-review notes

- **Spec coverage:** D1 → Task 6 (no filter; recursion pinned as working); D2 → Task 3; D3 → Task 5 (rejection test);
  D4 → Task 5 wiring + Task 8 README; D5 → Task 5 constructs `Promotion` without
  those fields and nothing persists them; D6 → `scope` derived from file location
  in Task 3; D7 → Task 5 passes `draft.statement` as the description verbatim;
  D8 → withdrawn with D1's filter; nothing to place.
- **No open questions.** Every fork is closed in the spec's Decisions section.
  If a step here looks like it needs a judgement call, that is a defect in this
  plan — stop and fix the plan rather than deciding at the keyboard.
- **Type consistency:** `promotion_body`/`parse_consolidates` (Task 1),
  `MemoryPromotionStore` (Task 3), `promotion_type`/`scope_to_subject` (Task 4),
  `FakeWriter`/`FakeStore`/`_obs(subject, name, type=...)` (Task 4) are each
  defined before first use, and `_obs` keeps its existing `(subject, name)`
  argument order.
- **Out of scope, deliberately not listed as a question:** whether the
  every-prompt surfacing hook should rank promotions above the memories they
  consolidate. That belongs to `~/.claude/hooks/surface-memory.py`, which this
  change does not touch. It is tracked as its own item, not carried here.
