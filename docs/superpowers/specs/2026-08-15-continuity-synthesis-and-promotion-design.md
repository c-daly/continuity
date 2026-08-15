# Continuity Synthesis & Promotion — v1 Design

**Date:** 2026-08-15
**Status:** Draft for review
**Owner:** continuity
**Scope of this spec:** v1 = the synthesis + promotion *settling pass*, including the vault-write-provider generalization it needs. Deferred to slice 2: the on-the-fly flagger and the embedding index.

## Problem

Continuity is the constellation's L2 layer — it exists to "trawl L1 memory for meaning." Today its `_synthesize()` is a stub: it counts a project's memory observations by type and disclaims that "richer synthesis will arrive in later phases." No meaning-making happens.

The meaning continuity owes is **cross-boundary promotion**: recognizing that the same concept has recurred across multiple projects/contexts, and consolidating those scattered first-order memories into a single cohesive higher-scope entity — so the idea is *seen* instead of fading inside one project's ~14-day-half-life memory.

## Definition

**Synthesis (v1) = detect cross-boundary recurrence → promote → refine.**

- **Detect** — find groups of similar / same-concept memories spanning >=2 distinct scopes (projects/entities).
- **Promote** — write a new, continuity-owned cohesive entity at the *appropriate subsuming scope* that consolidates the group.
- **Refine** — as new instances accrue, append a *superseding* promotion.

## Invariants (firm)

1. **Continuity never edits memory.** Promotion is purely additive. Sources are referenced, never moved, rewritten, or deleted.
2. **Promotions are continuity-owned artifacts**, not memory reproductions — written via the continuity write provider as a continuity-namespaced kind, co-located in the shared store alongside memory entries.
3. **Least-general subsuming scope; never a lazy root-dump.** A promotion lands at the *tightest* scope that genuinely subsumes all its instances (walk-up common ancestor). The user/root scope is a valid target only for genuinely universal concepts — it is never a default dumping ground for clusters whose real home is narrower. If the gate cannot establish a coherent shared concept, the cluster is rejected (no promotion), not dumped.
4. **Converge, not proliferate.** Re-running the pass over unchanged data is a near no-op. Promotion is gated and idempotent; existing promotions are recognized, not re-minted. (Ref: sophia's measured 21->51 type proliferation from unconditional minting.)
5. **Refinement is append-only.** A changed picture yields a *new superseding* promotion; the prior one is never edited. The chain of promotions is the revision history.

## Architecture (v1)

**Cadence:** a deferred **settling pass**, run on demand or scheduled — off any hot path. (The on-the-fly flagger is slice 2.)

**Pipeline:**

1. **Read corpus** — all memory observations across all scopes, via `memory_read_provider`. Scope-blind: this is the only cross-boundary view in the stack.
2. **Detect candidate clusters** — an LLM proposes clusters of same-concept entries spanning >=2 scopes. Existing structural links (shared entities, `[[refs]]`) seed/bias the batching; the LLM does the conceptual grouping (this is what catches recurrences the human never hand-linked). Existing promotions are supplied as context so their members are not re-clustered from scratch.
3. **Convergence gate** — a cluster proceeds only if it: spans >=2 distinct scopes; has >= MIN_INSTANCES members; is not already covered by a live promotion; and the LLM affirms it genuinely *consolidates* (adds cohesion / compresses), not merely restates.
4. **Resolve scope** — the least-general entity that subsumes the instances, by walking up the vault hierarchy (and laterally to related entities). The target may live anywhere in the vault, up to the user/root scope for universal concepts. Resolve to the *tightest* subsuming scope; never a lazy root-dump.
5. **Draft** — the LLM writes the cohesive entity: a refined statement of the recurring concept + explicit references to every source memory.
6. **Write** — persist as a continuity-owned promotion artifact at the resolved scope, marked as a promotion.
7. **Refine** — if the cluster already has a live promotion but membership/content changed materially, write a *new superseding* promotion (link supersedes -> prior).

## The write path (grounded in existing code)

`vault_write_provider.VaultWriteProvider` already maps continuity-namespaced kinds to vault paths, requires `project` in frontmatter, validates basenames against traversal, and writes atomically (temp file + `os.replace`). Today it only addresses `10-projects/<project>/<subdir>/`.

**v1 generalizes the provider to write *throughout the vault*** (decision, 2026-08-15): the resolved scope is a vault locator — user/root level, any PARA area, a project, or a sub-entity — not just a project name. A promotion is written at `<resolved-scope-path>/promotions/<id>.md`, creating the scope path as needed, with the resolved scope carried in frontmatter. Traversal validation and atomic write are preserved. The new kind is `cont.promotion`.

Examples: a concept recurring across sophia + hermes promotes to `10-projects/LOGOS/promotions/`; a concept recurring across LOGOS + agent-swarm — whose common ancestor is the user/cross-cutting level — promotes at a vault-root `promotions/` home, mirroring where user-level memory lives.

Generalizing the path resolution (from a fixed `10-projects/<project>/<subdir>/` mapping to a scope-driven locator across the whole vault) is the one non-trivial provider change v1 carries; it stays traversal-safe and atomic.

## The promotion artifact (proposed — for review)

Kind `cont.promotion`, one markdown file per promotion at the resolved scope. Proposed frontmatter fields:

- `kind: promotion`
- `scope` — the resolved subsuming scope (also drives the write path)
- `title` — short name of the recurring concept
- `sources` — list of source memory references (name + their scope) — links, never copies
- `instances` — count, and the distinct scopes spanned
- `created_at`
- `supersedes` / `superseded_by` — the refinement chain (nullable)
- `confidence` — optional; derived from instance count / scope spread

Body: the LLM-drafted cohesive statement of the concept.

The `promotion` marker is load-bearing: the detector excludes promotions from being re-promoted, and consumers use it to distinguish first-order memory from synthesized second-order artifacts.

## Convergence gate thresholds (proposed — for review)

- `MIN_INSTANCES = 2` — at least two source memories.
- `MIN_SCOPES = 2` — spanning at least two distinct entities/projects (the cross-boundary requirement).
- **Idempotence:** a cluster is "already covered" if its member set is a subset of an existing live promotion's `sources`. Members beyond that subset trigger *refinement* (a superseding promotion), not a duplicate.
- **Consolidation affirmation:** the LLM must return a boolean + one-line justification that the promotion consolidates rather than restates. This is the guard against restatement-only promotions.

Conservative on purpose; all tunable.

## Error handling

- The pass is best-effort and additive. A failure on one cluster (LLM error, write error, scope-resolution failure) aborts *that cluster only*; other clusters proceed. Writes are atomic (nothing partial persists).
- LLM nondeterminism is bounded by the gate: a spurious cluster must still clear >=2 scopes, MIN_INSTANCES, and the consolidation affirmation; idempotence prevents duplicate promotions across runs.
- Corpus-read failure or an empty corpus degrades to a no-op (presence-gated: no memory -> nothing to synthesize).

## Testing

- **Convergence (load-bearing):** run the pass twice over a fixed fixture corpus; the second run writes zero new promotions. This is the sophia-proliferation guard.
- **Cross-boundary gate:** a concept present in only one scope is NOT promoted; the same concept across >=2 scopes IS.
- **Additivity:** after a pass, every source memory file is byte-identical (continuity never edits memory).
- **Scope resolution:** instances under a common project-ancestor promote there; instances spanning sibling projects promote at the user/root scope; a narrow cluster never dumps at root.
- **Provider reach:** the generalized write provider writes (and creates paths) at project, sub-entity, and user/root scopes, and still rejects traversal in scope/id.
- **Refinement:** adding a new instance to a promoted cluster yields a superseding promotion linking to the prior; the prior is untouched.
- **Artifact shape:** promotions carry references (not copies) and the `promotion` marker; a promotion is never re-promoted.
- **LLM isolation:** the clusterer and drafter sit behind an injectable interface; tests drive the pipeline/gate/write logic with fixture returns (deterministic). A thin live smoke test exercises the real LLM path.

## Out of scope (slice 2+)

- On-the-fly flagger (hot-path recognition writing candidate flags for the later pass).
- Embedding index + semantic clustering (a *scale* optimization so the pass need not LLM-scan the whole corpus each run; at ~700-1k entries the LLM pass is feasible without it).
- Surfacing polish (promotions land where the brief already reads; deeper brief integration later).
- **Refinement** — writing a *superseding* promotion when a promoted cluster gains new instances. The `supersedes`/`superseded_by` fields exist but v1 never writes a supersession; the gate treats a grown (nested) cluster as already-covered and no-ops. *(Definition/Pipeline above list "Refine" under v1; moved to slice 2 during implementation to keep v1 provably convergent — convergence is the load-bearing invariant and is honored.)*

## Resolved decisions

- **Scope reach (2026-08-15):** the vault write provider is generalized to write *throughout the vault* — promotions land at the resolved scope wherever it lives, up to user/root level. The provider extension is part of v1 (not deferred).

## Open questions for review

1. **Artifact fields + the `cont.promotion` kind name** and the `promotions/` subdir name.
2. **Gate thresholds** (`MIN_INSTANCES`, `MIN_SCOPES`).
3. **LLM invocation** — which runner (the same `claude -p` bridge memory's recorder uses, or a direct API path), and batching/parallelism for the corpus pass.
