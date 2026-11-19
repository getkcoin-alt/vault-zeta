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

## 0.3 — long-running work & mission continuity (completed)

- directed acyclic task graph (DAG) primitives with cycle detection (`mission_tasks`, `mission_task_deps`)
- cascade unblocking of downstream dependent tasks
- crash recovery and resumption plan builder (`recover_mission`, `mission_resumption_plan`)
- deterministic event replay verification (`replay_events`, `mission_replay_events`)
- event deduplication via `idempotency_key`
- mission state compaction (`compact_mission`)
- bundle protocol v1.2.0 supporting portable task graphs
- MCP tools for task management, recovery, and replay

## 0.4 — multi-agent continuity & external integrations (next)

- independent agent identities and scoped memory namespaces (`agent_id`, `actor`, `workspace`)
- cross-agent handoffs with explicit provenance tracking
- Scrappy Forge and CANOPY adapters
- shared versus private memory semantics
- retention and compaction lifecycle policies

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
