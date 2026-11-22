# Promotion Implementation Plan

> **Status (2026-11-22): superseded, not executed.** Memory's 2026-09-05 correction (memory PR #11) rejected the memory half of this plan: there is no `--promotes` flag, no index omission and no `get` fallback. Memory instead persists caller-supplied frontmatter through `--field KEY=VALUE` and never interprets it (memory narrative, 2026-09-05: "Continuity writes `promotes: <name>` through this like any other field."). Tasks 1 to 3 are withdrawn. Tasks 4 to 8 were written against the flag and need re-planning against `--field promotes=<name>` before any of them is run.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-scope a memory that was recorded at too specific a level, by writing the same claim at the level where it applies, tagged so queries return the new one and an agent can still reach the original.

**Architecture:** Continuity judges the scope and writes the promoted memory through `bin/memory write --promotes <original>`. The tag lands in the new entry's frontmatter — never on the original, which keeps append-only intact. Memory honours the tag by leaving promoted-away entries out of `MEMORY.md`, so every query surface skips them at once, while `memory get` still returns them so the link works.

**Tech Stack:** Python 3.13, pytest, PyYAML. Two repos: `~/.claude/plugins/memory` and `~/.claude/plugins/continuity`.

**Spec:** `<vault>/10-projects/continuity/plans/2026-08-31-promotions-are-memories.md`

## Global Constraints

- **Append-only is absolute.** No task edits, moves, or deletes an existing entry file. The tag goes on the *created* memory and points at the original.
- `MEMORY.md` is a regenerable index, not a source of record — rewriting it is not an append-only violation. The entry files are the record.
- Memory's valid types stay exactly `{"user", "feedback", "project", "reference"}`. No new type.
- Entry frontmatter requires `name`, `description`, `type`, `subject` (`memory/lib/memory_reader.py:54`). `promotes` is a fifth, optional field.
- `index.rebuild_from_scan` reads **frontmatter only**, by design, for per-file cost. The tag must therefore be frontmatter, never body.
- A promoted-away entry stays retrievable by `memory get`. Only *queries* skip it.
- Every task is TDD: failing test first, watch it fail, minimal implementation, watch it pass, commit.
- Run that repo's full suite before every commit. Memory and continuity are both green at plan time (continuity: 244).

## Repo split

| Part | Repo | Tasks |
|---|---|---|
| A. The tag | `memory` | 1, 2, 3 |
| B. Promotions are written as memories | `continuity` | 4, 5 |
| C. The promotion sweep | `continuity` | 6, 7, 8 |

Part A lands first: continuity cannot pass `--promotes` until memory accepts it.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `memory/lib/memory_writer.py` | Accept and render `promotes` | Modify |
| `memory/lib/cli.py` | `--promotes` flag | Modify |
| `memory/lib/index.py` | Omit promoted-away entries from the index | Modify |
| `memory/tests/test_memory_writer.py` | Tag round-trip | Modify |
| `memory/tests/test_index.py` | Omission, rebuild, `get` still works | Modify |
| `continuity/lib/memory_write_provider.py` | Pass promotion fields + tag through | Modify |
| `continuity/lib/promotion.py` | Drop the bespoke artifact; keep domain types | Modify |
| `continuity/lib/vault_write_provider.py` | Delete the `cont.promotion` path | Modify |
| `continuity/lib/scope_judgement.py` | "Is this filed too narrowly?" | Create |
| `continuity/lib/promotion_sweep.py` | Walk the corpus, promote what is mis-scoped | Create |
| `continuity/lib/synthesis_pass.py` | Merge path writes through the memory path | Modify |

---

# Part A — memory: the tag

## Task 1: `promotes` frontmatter and `--promotes` flag

**Files:**
- Modify: `memory/lib/memory_writer.py:28` (`write` signature), the frontmatter rendering below it
- Modify: `memory/lib/cli.py:206` (the `write` subparser)
- Test: `memory/tests/test_memory_writer.py`

**Interfaces:**
- Produces: `write(name, description, type, subject, body, provider=None, promotes: str | None = None) -> str`, rendering `promotes: <name>` into frontmatter when given.

- [ ] **Step 1: Write the failing tests**

```python
def test_write_records_the_promotes_tag_in_frontmatter(tmp_vault):
    """The tag goes on the entry being created and names the entry it
    relocates. It must be frontmatter: index.rebuild_from_scan reads only the
    frontmatter head, by design, so a body marker would be invisible to it."""
    path = write(
        name="tabs-are-four-spaces", description="A general coding preference.",
        type="feedback", subject="user", body="Body.",
        promotes="logos-tabs-are-four-spaces",
    )

    text = (tmp_vault / path).read_text()
    assert "promotes: logos-tabs-are-four-spaces" in text.split("---")[1]


def test_write_without_promotes_emits_no_tag(tmp_vault):
    """An ordinary memory is unchanged — no empty or null field."""
    path = write(name="plain", description="d", type="project",
                 subject="user", body="Body.")

    assert "promotes" not in (tmp_vault / path).read_text()


def test_promotes_must_name_something(tmp_vault):
    for bad in ("", "   "):
        with pytest.raises(ValueError, match="promotes"):
            write(name="x", description="d", type="project", subject="user",
                  body="b", promotes=bad)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_memory_writer.py -q -k promotes`
Expected: FAIL with `TypeError: write() got an unexpected keyword argument 'promotes'`

- [ ] **Step 3: Write minimal implementation**

In `memory/lib/memory_writer.py`, add the parameter and validate it beside the existing checks:

```python
def write(
    name: str,
    description: str,
    type: str,
    subject: str,
    body: str,
    provider: Provider | None = None,
    promotes: str | None = None,
) -> str:
```

After the existing `subject` validation:

```python
    if promotes is not None and not promotes.strip():
        raise ValueError("promotes must name an entry, or be omitted")
```

Add the field to the rendered frontmatter, after `subject`, only when present:

```python
    if promotes is not None:
        frontmatter_lines.append(f"promotes: {promotes.strip()}")
```

(Match the surrounding rendering style — if frontmatter is built by `yaml.safe_dump` from a dict, add the key to that dict under the same condition instead.)

In `memory/lib/cli.py`, on the `write` subparser:

```python
    p_write.add_argument(
        "--promotes",
        default=None,
        help="name of the entry this one relocates; queries skip that entry",
    )
```

and pass `promotes=args.promotes` through to `write(...)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_memory_writer.py -q`
Expected: PASS

- [ ] **Step 5: Full suite and commit**

```bash
python3 -m pytest -q
git add lib/memory_writer.py lib/cli.py tests/test_memory_writer.py
git commit -m "feat(writer): record a promotes tag on the entry that relocates another"
```

---

## Task 2: The index omits promoted-away entries

**Files:**
- Modify: `memory/lib/index.py` — `rebuild_from_scan`, and `append`
- Test: `memory/tests/test_index.py`

**Interfaces:**
- Consumes: the `promotes` frontmatter from Task 1
- Produces: `MEMORY.md` contains no line for any entry named by a live `promotes` tag

`MEMORY.md` is the query surface — `bin/memory list` reads it, and so does the every-prompt surfacing hook. Filtering here makes every query skip the relocated entry at once. It is a regenerable index, so rewriting it is not an append-only concern; the entry file is untouched.

- [ ] **Step 1: Write the failing tests**

```python
def test_rebuild_omits_an_entry_that_has_been_promoted_away(tmp_vault):
    """The promoted-away original is not a current answer, so it does not
    belong in the index every query reads."""
    _entry(tmp_vault, "10-projects/LOGOS", "logos-tabs", type="feedback",
           subject="LOGOS")
    _entry(tmp_vault, ".", "tabs-are-four-spaces", type="feedback",
           subject="user", promotes="logos-tabs")

    rebuild_from_scan(tmp_vault)

    index_text = (tmp_vault / "MEMORY.md").read_text()
    assert "tabs-are-four-spaces" in index_text
    assert "logos-tabs" not in index_text


def test_rebuild_keeps_entries_nothing_promotes(tmp_vault):
    _entry(tmp_vault, "10-projects/LOGOS", "untouched", type="project",
           subject="LOGOS")

    rebuild_from_scan(tmp_vault)

    assert "untouched" in (tmp_vault / "MEMORY.md").read_text()


def test_the_promoted_away_file_is_never_modified(tmp_vault):
    """Append-only: the original keeps its bytes. Only the index changes."""
    original = _entry(tmp_vault, "10-projects/LOGOS", "logos-tabs",
                      type="feedback", subject="LOGOS")
    before = original.read_bytes()
    _entry(tmp_vault, ".", "tabs-are-four-spaces", type="feedback",
           subject="user", promotes="logos-tabs")

    rebuild_from_scan(tmp_vault)

    assert original.read_bytes() == before


def test_append_drops_the_line_for_what_the_new_entry_promotes(tmp_vault):
    """Writing a promotion takes effect immediately, without a rebuild."""
    _entry(tmp_vault, "10-projects/LOGOS", "logos-tabs", type="feedback",
           subject="LOGOS")
    rebuild_from_scan(tmp_vault)
    assert "logos-tabs" in (tmp_vault / "MEMORY.md").read_text()

    append(tmp_vault, name="tabs-are-four-spaces", type="feedback",
           subject="user", path=".memory/2026-09-03-tabs-are-four-spaces.md",
           description="d", promotes="logos-tabs")

    index_text = (tmp_vault / "MEMORY.md").read_text()
    assert "tabs-are-four-spaces" in index_text
    assert "logos-tabs" not in index_text
```

`_entry` is a helper writing a valid entry file and returning its path; extend the existing one in this file with an optional `promotes` kwarg, or add it if absent.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_index.py -q -k "promot"`
Expected: FAIL — `logos-tabs` is still in the index

- [ ] **Step 3: Write minimal implementation**

In `rebuild_from_scan`, collect entries first, then drop the promoted-away ones before writing. Where the loop currently appends to `entries`, also record the tag:

```python
        promoted_away: set[str] = set()
        # ... inside the existing per-file loop, after `fm` is parsed:
        promotes = fm.get("promotes")
        if promotes:
            promoted_away.add(str(promotes).strip())
```

Then, immediately before the index is rendered:

```python
        # An entry that something else has relocated is not a current answer,
        # so it is left out of the index every query reads. The file itself is
        # untouched, and `memory get` still returns it by name — that is how a
        # promotion's tag stays followable back to the original.
        entries = [e for e in entries if e.name not in promoted_away]
```

In `append`, add the parameter and drop the superseded line:

```python
def append(
    vault_root: Path,
    name: str,
    type: str,
    subject: str,
    path: str,
    description: str,
    promotes: str | None = None,
) -> None:
```

Inside the lock, after the new bullet is composed and before the file is written, filter existing lines:

```python
        if promotes:
            target = promotes.strip()
            lines = [
                ln for ln in lines
                if not _bullet_names(ln, target)
            ]
```

where `_bullet_names(line, name)` returns True when a bullet line is the index entry for `name` — match on the `|<name>]]` segment the existing `_format_bullet` emits, so a substring of a longer name cannot match.

Have `memory_writer.write` pass `promotes` through to `index.append`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_index.py -q`
Expected: PASS

- [ ] **Step 5: Full suite and commit**

```bash
python3 -m pytest -q
git add lib/index.py lib/memory_writer.py tests/test_index.py
git commit -m "feat(index): leave promoted-away entries out of the query surface"
```

---

## Task 3: A promoted-away entry is still reachable

**Files:**
- Test only: `memory/tests/test_memory_reader.py`

**Interfaces:**
- Consumes: Tasks 1 and 2. No implementation expected.

The point of putting the tag on the promotion rather than the original is that the original survives intact and reachable. `list` is a query and skips it; `get` is a direct retrieval by name and must not.

- [ ] **Step 1: Write the tests**

```python
def test_get_still_returns_a_promoted_away_entry(tmp_vault):
    """This is how an agent follows a promotion's tag back to the original.
    If get() filtered too, the tag would point at nothing."""
    _entry(tmp_vault, "10-projects/LOGOS", "logos-tabs", type="feedback",
           subject="LOGOS")
    _entry(tmp_vault, ".", "tabs-are-four-spaces", type="feedback",
           subject="user", promotes="logos-tabs")
    rebuild_from_scan(tmp_vault)

    assert get("logos-tabs", "feedback") is not None


def test_list_does_not_return_a_promoted_away_entry(tmp_vault):
    _entry(tmp_vault, "10-projects/LOGOS", "logos-tabs", type="feedback",
           subject="LOGOS")
    _entry(tmp_vault, ".", "tabs-are-four-spaces", type="feedback",
           subject="user", promotes="logos-tabs")
    rebuild_from_scan(tmp_vault)

    assert [e.name for e in list(type="feedback")] == ["tabs-are-four-spaces"]
```

- [ ] **Step 2: Run them**

Run: `python3 -m pytest tests/test_memory_reader.py -q -k promoted`
Expected: PASS with no implementation change. `get` reads the file by name and does not consult the index; `list` reads the index, which Task 2 filtered. If `get` fails, Task 2 filtered too aggressively — fix there.

- [ ] **Step 3: Commit**

```bash
git add tests/test_memory_reader.py
git commit -m "test(reader): a promoted-away entry leaves queries but stays retrievable"
```

---

# Part B — continuity: promotions are written as memories

## Task 4: The write provider passes promotion fields and the tag

**Files:**
- Modify: `continuity/lib/memory_write_provider.py:22` (`_KIND_TO_MEMORY_TYPE`), `:121` (`_map_to_memory`), and the `cmd` list in `write`
- Test: `continuity/tests/test_memory_write_provider.py`

**Interfaces:**
- Produces: `MemoryWriteProvider.write("cont.promotion", name, {"type", "subject", "description", "promotes"}, body)` invokes `bin/memory write` with all five.

A promotion's type is derived per-case, so unlike `cont.insight` it cannot come from the static kind→type map. The caller supplies every field.

- [ ] **Step 1: Write the failing tests**

```python
def _recording_memory_bin(tmp_path, args_file):
    memory_bin = tmp_path / "memory"
    memory_bin.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > " + str(args_file) + "\ncat > /dev/null\n"
    )
    memory_bin.chmod(0o755)
    return memory_bin


def test_promotion_passes_its_fields_and_tag_through(tmp_path, monkeypatch):
    args_file = tmp_path / "args.txt"
    monkeypatch.setenv("MEMORY_BIN", str(_recording_memory_bin(tmp_path, args_file)))

    MemoryWriteProvider().write(
        "cont.promotion", "tabs-are-four-spaces",
        {"type": "feedback", "subject": "user",
         "description": "A general coding preference.",
         "promotes": "logos-tabs"},
        "body",
    )

    args = args_file.read_text().split("\n")
    assert "feedback" in args and "user" in args
    assert "--promotes" in args and "logos-tabs" in args


def test_promotion_without_a_tag_sends_no_promotes_flag(tmp_path, monkeypatch):
    """A merge writes a new claim that relocates nothing in particular."""
    args_file = tmp_path / "args.txt"
    monkeypatch.setenv("MEMORY_BIN", str(_recording_memory_bin(tmp_path, args_file)))

    MemoryWriteProvider().write(
        "cont.promotion", "merged", {"type": "project", "subject": "LOGOS",
                                     "description": "d"}, "body")

    assert "--promotes" not in args_file.read_text().split("\n")


def test_promotion_rejects_a_type_memory_will_not_accept(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_BIN", str(tmp_path / "memory"))

    with pytest.raises(ValueError, match="invalid memory type"):
        MemoryWriteProvider().write(
            "cont.promotion", "x",
            {"type": "synthesis", "subject": "LOGOS", "description": "d"}, "b")


def test_promotion_requires_subject_and_description(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_BIN", str(tmp_path / "memory"))

    for missing in ("subject", "description"):
        fm = {"type": "project", "subject": "LOGOS", "description": "d"}
        del fm[missing]
        with pytest.raises(ValueError, match=missing):
            MemoryWriteProvider().write("cont.promotion", "x", fm, "b")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_memory_write_provider.py -q -k promotion`
Expected: FAIL with `ValueError: Unknown kind: 'cont.promotion'`

- [ ] **Step 3: Write minimal implementation**

Add beside `_KIND_TO_MEMORY_TYPE`:

```python
_PROMOTION_KIND = "cont.promotion"
# memory owns the canonical list (memory/lib/memory_writer.py VALID_TYPES);
# mirrored here only to fail clearly before the CLI boundary.
_MEMORY_TYPES = {"user", "feedback", "project", "reference"}
```

At the top of `_map_to_memory`:

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
        mapped = {
            "type": memory_type,
            "subject": subject.rsplit("/", 1)[-1],
            "name": id,
            "description": description,
        }
        promotes = str(frontmatter.get("promotes") or "").strip()
        if promotes:
            validate_basename(promotes, "promotes")
            mapped["promotes"] = promotes
        return mapped
```

In `write`, append the flag when the mapping carries it:

```python
        if mapped.get("promotes"):
            cmd += ["--promotes", mapped["promotes"]]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_memory_write_provider.py -q`
Expected: PASS

- [ ] **Step 5: Full suite and commit**

```bash
python3 -m pytest -q
git add lib/memory_write_provider.py tests/test_memory_write_provider.py
git commit -m "feat(memory-bridge): write a promotion, tag included"
```

---

## Task 5: The merge path writes through the memory path

**Files:**
- Modify: `continuity/lib/synthesis_pass.py:12-13`, `:78-85`, `:93-113`
- Modify: `continuity/lib/promotion.py` — delete `promotion_to_frontmatter` and `PromotionStore`
- Modify: `continuity/lib/vault_write_provider.py` — delete `_PROMOTION_KIND`, `_PROMOTION_SUBDIR`, `_resolve_promotion`, and both promotion branches
- Test: `continuity/tests/test_synthesis_pass.py`, `tests/test_vault_write_provider.py`; delete `tests/test_promotion_store.py`

**Interfaces:**
- Consumes: Task 4
- Produces: `run_synthesis(reader, writer, clusterer, drafter, vault_path, today=None)` — the `store` parameter is gone

The merge path currently writes to `<scope>/promotions/`, where nothing can recall it. Its output is a memory too, so it goes the same way. Existing promotions are read back through `reader.list()` like anything else, so the bespoke store has no job left.

- [ ] **Step 1: Write the failing tests**

Add the fakes the file lacks (it currently uses the real providers against a temp vault, which would spawn subprocesses once the writer is `MemoryWriteProvider`):

```python
class FakeWriter:
    def __init__(self): self.calls = []
    def write(self, kind, id, frontmatter, body):
        self.calls.append((kind, id, frontmatter, body))
```

Widen `_obs` to carry a type, keeping its existing `(subject, name)` order so current call sites are untouched:

```python
def _obs(subject, name, type="feedback"):
    return MemoryObservation(type=type, subject=subject, name=name, description="d")
```

Then:

```python
def test_merge_writes_its_result_as_a_memory(tmp_path):
    writer = FakeWriter()
    cluster = Cluster("recall is activation", [
        _obs("LOGOS", "hcg-not-rag"), _obs("sophia", "hcg-no-passages")])

    run_synthesis(FakeReader(cluster.members), writer, FakeClusterer([cluster]),
                  FakeDrafter(consolidates=True), vault_path=_vault(tmp_path),
                  today=date(2026, 9, 3))

    kind, pid, fm, body = writer.calls[0]
    assert kind == "cont.promotion"
    assert fm["type"] == "feedback"        # unanimous source type inherited
    assert fm["subject"] == "LOGOS"        # leaf of the resolved scope
    assert fm["description"]


def test_a_rejected_write_skips_that_cluster_and_the_pass_continues(tmp_path):
    """A name can collide with any existing memory. memory refuses an occupied
    location, which is correct — the pass skips and carries on."""
    class RejectingWriter:
        def __init__(self): self.calls = []
        def write(self, kind, id, fm, body):
            self.calls.append(id)
            if len(self.calls) == 1:
                raise RuntimeError("memory write failed: already exists")

    first = Cluster("concept one", [_obs("LOGOS", "a"), _obs("memory", "b")])
    second = Cluster("concept two", [_obs("LOGOS", "c"), _obs("memory", "d")])

    result = run_synthesis(FakeReader(first.members + second.members),
                           RejectingWriter(), FakeClusterer([first, second]),
                           FakeDrafter(consolidates=True),
                           vault_path=_vault(tmp_path), today=date(2026, 9, 3))

    assert result.skipped == ["concept one"]
    assert result.written == ["concept-two"]
```

And in `tests/test_vault_write_provider.py`:

```python
def test_vault_provider_no_longer_accepts_promotions(fake_vault):
    """Promotions go through memory. A second placement path nothing calls is
    how the two writers came to disagree in #13."""
    with pytest.raises(ValueError, match="Unknown kind"):
        VaultWriteProvider(vault_path=fake_vault).write(
            "cont.promotion", "x", {"scope": "10-projects/LOGOS"}, "b")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_synthesis_pass.py tests/test_vault_write_provider.py -q`
Expected: FAIL — `run_synthesis` still takes `store`, and the vault writer still accepts the kind

- [ ] **Step 3: Write minimal implementation**

Add to `synthesis_pass.py`, after `MIN_SCOPES`:

```python
_MEMORY_TYPES = {"user", "feedback", "project", "reference"}
_DEFAULT_TYPE = "project"


def promotion_type(cluster: Cluster) -> str:
    """The type a merged claim inherits from the memories it combines.

    Unanimous sources hand their type down; anything else falls back to
    `project`. Deterministic, no LLM call.
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
    `user`; `10-projects` is itself an addressable entity.
    """
    return scope.rsplit("/", 1)[-1] if scope else "user"
```

Change the signature to drop `store`, derive `existing` from the reader, and replace the write:

```python
def run_synthesis(reader, writer, clusterer: Clusterer, drafter: Drafter,
                  vault_path: Path, today: Optional[date] = None) -> SynthesisResult:
```

```python
            writer.write(
                "cont.promotion",
                pid,
                {
                    "type": promotion_type(cluster),
                    "subject": scope_to_subject(scope),
                    "description": draft.statement,
                },
                draft.statement,
            )
```

Update `default_synthesis_deps` to wire `MemoryWriteProvider()` and drop `store`. Delete `promotion_to_frontmatter` and `PromotionStore` from `promotion.py`, the promotion branches and `_resolve_promotion` from `vault_write_provider.py`, every `cont.promotion` test in `test_vault_write_provider.py`, and `tests/test_promotion_store.py` entirely.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lib/ tests/
git rm tests/test_promotion_store.py
git commit -m "refactor(synthesis): merge results are memories, written through memory"
```

---

# Part C — continuity: the promotion sweep

## Task 6: The scope judgement

**Files:**
- Create: `continuity/lib/scope_judgement.py`
- Test: `continuity/tests/test_scope_judgement.py`

**Interfaces:**
- Produces:
  - `class ScopeJudge(ABC)` with `judge(entry: MemoryObservation) -> Optional[str]` returning the tightest subject the claim applies to, or None when it cannot tell
  - `needs_promotion(current_subject: str, judged_subject: str, vault_path: Path) -> bool`

The judgement is about one memory's content, not a group. `resolve_scope`'s longest-common-prefix answers a different question — where several observed instances sit — and there are no instances here, only a claim.

- [ ] **Step 1: Write the failing tests**

`tests/test_scope_judgement.py` is a new file, so it defines its own fixture —
nothing is inherited from `test_synthesis_pass.py`:

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from scope_judgement import needs_promotion


@pytest.fixture
def vault(tmp_path):
    """Nested and sibling projects, so subsumption has something to test."""
    projects = tmp_path / "10-projects"
    for name in ("LOGOS", "agent-swarm"):
        (projects / name).mkdir(parents=True)
        (projects / name / "narrative.md").write_text(f"# {name}\n")
    sophia = projects / "LOGOS" / "sophia"
    sophia.mkdir()
    (sophia / "narrative.md").write_text("# sophia\n")
    return tmp_path


def test_needs_promotion_for_a_nested_project(vault):
    """LOGOS subsumes LOGOS/sophia, so a sophia-scoped claim that really
    applies across LOGOS is filed too narrowly."""
    assert needs_promotion("sophia", "LOGOS", vault) is True


def test_needs_promotion_when_the_judged_scope_is_broader(vault):
    """tabs-are-four-spaces filed under LOGOS is a general coding preference:
    user scope subsumes LOGOS, so it is filed too narrowly."""
    assert needs_promotion("LOGOS", "user", vault) is True


def test_no_promotion_when_the_scopes_match(vault):
    assert needs_promotion("LOGOS", "LOGOS", vault) is False


def test_no_promotion_when_the_judged_scope_is_narrower(vault):
    """That is a demotion candidate, which this sweep does not act on:
    over-broad costs noise, under-scoped loses knowledge."""
    assert needs_promotion("user", "LOGOS", vault) is False


def test_no_promotion_for_unrelated_scopes(vault):
    """Neither subsumes the other, so 'too narrow' is not the diagnosis."""
    assert needs_promotion("LOGOS", "agent-swarm", vault) is False


def test_no_promotion_when_the_judge_cannot_place_the_claim(vault):
    assert needs_promotion("LOGOS", None, vault) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_scope_judgement.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'scope_judgement'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Is this memory filed more narrowly than it applies?

Promotion asks one question about one memory. The answer is a scope, judged
from the claim's content — not derived from where instances were observed,
because a single memory has no instances to compare.
"""
from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from project_registry import resolve as _resolve_project  # noqa: E402


class ScopeJudge(ABC):
    @abstractmethod
    def judge(self, entry) -> Optional[str]:
        """The tightest subject this claim applies to, or None if unclear."""


def _dir_for(subject: str, vault_path: Path) -> Optional[str]:
    if subject == "user":
        return ""
    return _resolve_project(subject, vault_path)


def needs_promotion(current_subject: str, judged_subject: Optional[str],
                    vault_path: Path) -> bool:
    """True when the judged scope strictly subsumes where the memory sits.

    Subsumption is directory containment: "" (vault root, `user`) contains
    everything; `10-projects/LOGOS` contains `10-projects/LOGOS/sophia`. Only
    the too-narrow direction promotes — the reverse is a demotion candidate,
    and unrelated scopes mean "too narrow" is the wrong diagnosis entirely.
    """
    if not judged_subject or judged_subject == current_subject:
        return False
    current = _dir_for(current_subject, vault_path)
    judged = _dir_for(judged_subject, vault_path)
    if current is None or judged is None:
        return False
    if judged == current:
        return False
    return judged == "" or current.startswith(judged + "/")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_scope_judgement.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lib/scope_judgement.py tests/test_scope_judgement.py
git commit -m "feat(promotion): decide whether a memory is filed too narrowly"
```

---

## Task 7: The sweep

**Files:**
- Create: `continuity/lib/promotion_sweep.py`
- Test: `continuity/tests/test_promotion_sweep.py`

**Interfaces:**
- Consumes: `ScopeJudge` / `needs_promotion` (Task 6), `MemoryWriteProvider` promotion write (Task 4)
- Produces: `run_promotion_sweep(reader, writer, judge, vault_path, today=None) -> SweepResult` with `.promoted: list[str]` and `.skipped: list[str]`

- [ ] **Step 1: Write the failing tests**

`tests/test_promotion_sweep.py` is a new file and defines its own doubles:

```python
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from memory_read_provider import MemoryObservation
from promotion_sweep import run_promotion_sweep


class FakeReader:
    def __init__(self, obs): self._obs = obs
    def list(self, type_=None, subject=None): return list(self._obs)


class FakeWriter:
    def __init__(self): self.calls = []
    def write(self, kind, id, frontmatter, body):
        self.calls.append((kind, id, frontmatter, body))


class FixedJudge:
    """Maps entry name -> the subject the claim really applies to."""
    def __init__(self, verdicts): self._v = verdicts
    def judge(self, entry): return self._v.get(entry.name)


def _obs(subject, name, type="feedback"):
    return MemoryObservation(type=type, subject=subject, name=name,
                             description="d")


def _vault(tmp_path):
    projects = tmp_path / "10-projects"
    for name in ("LOGOS", "agent-swarm"):
        (projects / name).mkdir(parents=True)
        (projects / name / "narrative.md").write_text(f"# {name}\n")
    return tmp_path


def test_promotes_a_memory_filed_too_narrowly(tmp_path):
    """The whole operation, on one memory: same claim, right level, tagged."""
    entry = _obs("LOGOS", "logos-tabs", "feedback")
    writer = FakeWriter()

    result = run_promotion_sweep(FakeReader([entry]), writer,
                                 FixedJudge({"logos-tabs": "user"}),
                                 vault_path=_vault(tmp_path),
                                 today=date(2026, 9, 3))

    kind, name, fm, body = writer.calls[0]
    assert kind == "cont.promotion"
    assert fm["subject"] == "user"
    assert fm["type"] == "feedback"        # the source's own type
    assert fm["promotes"] == "logos-tabs"  # the tag points at the original
    assert result.promoted == [name]


def test_leaves_a_correctly_filed_memory_alone(tmp_path):
    writer = FakeWriter()

    run_promotion_sweep(FakeReader([_obs("LOGOS", "logos-only", "project")]),
                        writer, FixedJudge({"logos-only": "LOGOS"}),
                        vault_path=_vault(tmp_path), today=date(2026, 9, 3))

    assert writer.calls == []


def test_does_not_promote_what_it_already_promoted(tmp_path):
    """The sweep is idempotent: a promotion is a memory, so it comes back on
    the next run, and re-promoting it to the same scope must be a no-op."""
    promoted = _obs("user", "tabs-are-four-spaces", "feedback")
    writer = FakeWriter()

    run_promotion_sweep(FakeReader([promoted]), writer,
                        FixedJudge({"tabs-are-four-spaces": "user"}),
                        vault_path=_vault(tmp_path), today=date(2026, 9, 3))

    assert writer.calls == []


def test_a_rejected_write_skips_that_memory_and_the_sweep_continues(tmp_path):
    class RejectingWriter:
        def __init__(self): self.calls = []
        def write(self, kind, id, fm, body):
            self.calls.append(id)
            if len(self.calls) == 1:
                raise RuntimeError("memory write failed: already exists")

    entries = [_obs("LOGOS", "first", "feedback"), _obs("LOGOS", "second", "feedback")]
    writer = RejectingWriter()

    result = run_promotion_sweep(FakeReader(entries), writer,
                                 FixedJudge({"first": "user", "second": "user"}),
                                 vault_path=_vault(tmp_path), today=date(2026, 9, 3))

    assert result.skipped == ["first"]
    assert len(result.promoted) == 1


def test_one_failing_judgement_never_aborts_the_sweep(tmp_path):
    class ExplodingJudge:
        def judge(self, entry):
            if entry.name == "boom":
                raise RuntimeError("model unavailable")
            return "user"

    entries = [_obs("LOGOS", "boom", "feedback"), _obs("LOGOS", "fine", "feedback")]
    writer = FakeWriter()

    result = run_promotion_sweep(FakeReader(entries), writer, ExplodingJudge(),
                                 vault_path=_vault(tmp_path), today=date(2026, 9, 3))

    assert result.skipped == ["boom"]
    assert len(writer.calls) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_promotion_sweep.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'promotion_sweep'`

- [ ] **Step 3: Write minimal implementation**

```python
"""The promotion sweep: re-scope memories that were filed too narrowly.

One memory at a time. No clustering, no minimum instance count — if it is at
the wrong level, it is at the wrong level. The promoted memory carries a
`promotes` tag pointing at the original, which is what keeps the original out
of query results while leaving it reachable and unedited.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from scope_judgement import needs_promotion  # noqa: E402

_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class SweepResult:
    promoted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _promoted_name(entry, subject: str) -> str:
    base = _SLUG_RE.sub("-", entry.name.lower()).strip("-")
    return f"{base}-at-{_SLUG_RE.sub('-', subject.lower()).strip('-')}"[:60]


def run_promotion_sweep(reader, writer, judge, vault_path: Path,
                        today: Optional[date] = None) -> SweepResult:
    """Walk the corpus asking whether each memory is filed too narrowly.

    Best-effort per memory: a failed judgement or a refused write skips that
    one and the sweep continues. A refused write is the expected outcome when
    the promotion already exists, which is what makes re-running idempotent.
    """
    result = SweepResult()
    for entry in reader.list():
        try:
            judged = judge.judge(entry)
            if not needs_promotion(entry.subject, judged, vault_path):
                continue
            name = _promoted_name(entry, judged)
            writer.write(
                "cont.promotion",
                name,
                {
                    "type": entry.type,
                    "subject": judged,
                    "description": entry.description,
                    "promotes": entry.name,
                },
                entry.description,
            )
            result.promoted.append(name)
        except Exception:
            result.skipped.append(entry.name)
            continue
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_promotion_sweep.py -q`
Expected: PASS

- [ ] **Step 5: Full suite and commit**

```bash
python3 -m pytest -q
git add lib/promotion_sweep.py tests/test_promotion_sweep.py
git commit -m "feat(promotion): sweep the corpus for memories filed too narrowly"
```

---

## Task 8: End to end across both plugins

**Files:**
- Create: `continuity/tests/test_promotion_end_to_end.py`
- Modify: `continuity/README.md`

**Interfaces:**
- Consumes: every task above

Everything before this uses fakes. The point of the change is that a promoted memory replaces the original *in queries* while staying reachable — which only a run against the real `bin/memory` can show.

- [ ] **Step 1: Write the test**

```python
"""Promotion end to end, against a real memory CLI.

The properties that matter are all cross-plugin: continuity writes the tag,
memory honours it. Fakes cannot show either.
"""
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from memory_read_provider import MemoryObservation
from memory_write_provider import MemoryWriteProvider
from promotion_sweep import run_promotion_sweep

MEMORY_BIN = Path(os.environ.get(
    "MEMORY_BIN", Path.home() / ".claude" / "plugins" / "memory" / "bin" / "memory"))

pytestmark = pytest.mark.skipif(
    not MEMORY_BIN.exists(), reason="memory plugin CLI not installed")


def _run(*args, vault):
    return subprocess.run([str(MEMORY_BIN), *args], capture_output=True, text=True,
                          env={**os.environ, "MEMORY_VAULT_DIR": str(vault)})


def test_a_promoted_memory_replaces_the_original_in_queries(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "10-projects" / "LOGOS").mkdir(parents=True)
    (vault / "10-projects" / "LOGOS" / "narrative.md").write_text("# LOGOS\n")
    monkeypatch.setenv("MEMORY_VAULT_DIR", str(vault))
    monkeypatch.setenv("CONTINUITY_VAULT_DIR", str(vault))

    # A general coding preference, mistakenly filed under one project.
    _run("write", "--type", "feedback", "--name", "logos-tabs",
         "--subject", "LOGOS", "--description", "Tabs are four spaces.",
         vault=vault)
    assert "logos-tabs" in _run("list", vault=vault).stdout

    class FixedJudge:
        def judge(self, entry): return "user"

    class Reader:
        def list(self, type_=None, subject=None):
            return [MemoryObservation(type="feedback", subject="LOGOS",
                                      name="logos-tabs",
                                      description="Tabs are four spaces.")]

    result = run_promotion_sweep(Reader(), MemoryWriteProvider(memory_bin=MEMORY_BIN),
                                 FixedJudge(), vault_path=vault,
                                 today=date(2026, 9, 3))
    assert len(result.promoted) == 1
    promoted = result.promoted[0]

    # 1. the promotion is filed at the level it applies to
    assert list((vault / ".memory").glob(f"*{promoted}.md"))

    # 2. queries return it and no longer return the original
    listed = _run("list", vault=vault).stdout
    assert promoted in listed
    assert "logos-tabs" not in listed

    # 3. the original is untouched on disk and still retrievable by name
    original = list((vault / "10-projects" / "LOGOS" / ".memory").glob("*logos-tabs.md"))
    assert len(original) == 1
    assert "Tabs are four spaces." in original[0].read_text()
    assert "logos-tabs" in _run("get", "--name", "logos-tabs",
                                "--type", "feedback", vault=vault).stdout
```

- [ ] **Step 2: Run it**

Run: `python3 -m pytest tests/test_promotion_end_to_end.py -q`
Expected: FAIL, or SKIP if the CLI is missing — a skip proves nothing here, so point `MEMORY_BIN` at a real install before continuing.

- [ ] **Step 3: Fix what it surfaces**

No new implementation is planned. A failure means a defect in Tasks 1-7; fix it there.

- [ ] **Step 4: Update the README**

Under `## Write providers`:

```markdown
Promotions and merged claims always go through the memory plugin, whatever
`write_provider` is set to — they are memories, and `bin/memory write` is what
indexes them so they are recallable. The `write_provider` setting governs
`cont.insight`, which keeps the vault default.

A promotion carries a `promotes:` tag naming the entry it relocates. Memory
leaves that entry out of query results while `memory get` still returns it, so
the original is superseded without being edited — append-only holds.
```

- [ ] **Step 5: Full suite, lint, commit**

```bash
python3 -m pytest -q
python3 -m ruff check lib/ tests/
git add tests/test_promotion_end_to_end.py README.md
git commit -m "test(promotion): prove the tag replaces the original in queries"
```

---

## Mutation checks before opening either PR

Each mutation must fail at least one test. Edit, run, confirm the failure, restore.

| Mutation | Must fail |
|---|---|
| `index.rebuild_from_scan` stops filtering `promoted_away` | Task 2 omission, Task 8 property 2 |
| `index.append` ignores `promotes` | Task 2 append test |
| `memory_reader.get` filters promoted-away entries too | Task 3 `get_still_returns` |
| `needs_promotion` returns True for a narrower judged scope | Task 6 demotion-direction test |
| `needs_promotion` returns True for unrelated scopes | Task 6 unrelated-scopes test |
| The sweep drops the `promotes` key from the frontmatter it writes | Task 7 tag test, Task 8 property 2 |
| The sweep lets a write rejection propagate | Task 7 rejection test |

## Self-review notes

- **Spec coverage:** D1 → Tasks 4, 5, 7 (ordinary memory, four fields, existing type); D2 → Task 7 idempotence test (a promotion re-read and left alone); D3 → Tasks 5, 7 (type inherited, subject is the scope leaf); D4 → Task 6 (`ScopeJudge`, content-judged); D5 → Tasks 1, 2 (tag on the created entry, memory applies it); D6 → Tasks 4, 5 wiring, Task 8 README; D7 → Tasks 5, 7 rejection tests; D8 → Task 5 deletes the `cont.promotion` vault path.
- **No open questions.** If a step looks like it needs a judgement call, that is a defect in this plan — fix the plan, do not decide at the keyboard.
- **Not in scope:** demotion (same mechanism reversed, low value — over-broad costs noise, under-scoped loses knowledge); the LLM `ScopeJudge` implementation, which needs its own prompt design and slots behind the ABC from Task 6; moving `~/.claude/hooks/surface-memory.py` into continuity, which is tracked separately and is not required for correctness here since it reads `MEMORY.md` and inherits the filter for free.
