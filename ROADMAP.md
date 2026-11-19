# Vault Zeta roadmap

This is a direction, not a release promise.

## 0.1 — public alpha (completed)

- durable typed memory
- provenance and source fingerprints
- stale-memory marking
- FTS5 retrieval
- append-only mission events
- resumable mission snapshot primitive
- optimistic revision checks
- tests and contributor setup

## 0.2 — retrieval that can be measured (completed)

- retrieval evaluation and benchmarking harness (`eval.py`, MRR, Precision@K, Recall@K)
- correction and supersession links (`supersedes_id`, `superseded_by`)
- entity indexing and semantic relationship history (`entities`, `memory_entities`)
- explainable score breakdown with BM25, confidence, and recency (`search_explain`)
- import/export bundle format v1.1.0 with provenance, entities, and lineages preserved
- MCP tools for supersession, lineage, explainable search, and entity navigation

## 0.3 — long-running work & mission continuity (next)

- task graph primitives and dependency tracking
- pause/resume/correction event helpers
- recovery tests across process restarts
- deterministic event replay harnesses
- retention and compaction policies
- Scrappy Forge and CANOPY adapters

## Later

- optional embedding adapter and hybrid lexical/vector ranking
- encryption at rest options
- PostgreSQL backend
- multi-device sync experiments
- conflict resolution between stores
- signed continuity bundles
- long-duration multi-agent simulations

## Things I do not want to fake

Vault Zeta should not become a place where vague AI language hides missing mechanisms.

No “infinite memory”, “consciousness”, “digital soul”, “AGI memory” or “production ready” label until the code and evidence justify the words.
