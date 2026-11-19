# Changelog

## 0.3.0 — durable mission execution and task graphs

- added directed acyclic task graphs (`mission_tasks`, `mission_task_deps`, `create_task`, `update_task`)
- added cycle detection preventing recursive dependency loops in task graphs
- added cascade unblocking: completing a prerequisite task automatically unblocks downstream dependent tasks
- added crash recovery and resumption plan builder (`recover_mission`, `mission_resumption_plan`) identifying interrupted running tasks and resetting them safely
- added deterministic event replay harness (`replay_events`, `mission_replay_events`) reconstructing task states from immutable event journals
- added event deduplication with `idempotency_key` ensuring safe retries across network or process boundaries
- added mission state compaction (`compact_mission`, `mission_compact`) preserving append-only audit journals
- upgraded bundle export/import protocol to v1.2.0 supporting portable task graphs and dependencies
- added MCP tools: `task_create`, `task_update`, `task_list`, `mission_resumption_plan`, `mission_replay_events`, `mission_compact`

## 0.2.2 — retrieval intelligence and lineage

- added memory supersession (`supersedes_id`, `superseded_by`, `supersede_memory`) for explicit factual evolution
- added lineage traversal (`get_lineage`, `memory_lineage`) tracing ancestor and descendant memory chains
- added explainable retrieval breakdown (`search_explain`, `memory_search_explain`) returning BM25 score, confidence weight, recency decay, and readable reasoning
- added entity indexing and semantic relationship mapping (`entities`, `memory_entities`, `index_entity`, `link_memory_entity`, `get_entity_memories`)
- added retrieval evaluation and benchmarking harness (`eval.py`, `evaluate_retrieval`) measuring MRR, Precision@K, Recall@K, and stale/conflicting memory rejection
- upgraded bundle export/import protocol to v1.1.0 preserving entity graphs and supersession lineages with zero foreign key hazard

## 0.2.1 — security hardening and concurrency

- resolved V01: recursive secret scanning across metadata, event payloads, and snapshot JSON
- resolved V02: XML escaping in context pack to prevent prompt injection delimiter escapes
- resolved V03: preserved stale flags, timestamps, and revision history during bundle import/export
- resolved V04: idempotent event deduplication on repeated bundle imports
- resolved V05: composite deduplication hash preventing cross-scope collisions
- resolved V06: added `memory_mark_stale` tool to MCP interface
- resolved V07: thread-safe SQLite concurrency using `threading.RLock()` across all store methods

## 0.1.0 — public alpha

- added SQLite-backed typed memory
- added provenance, confidence and source fingerprints
- added stale-memory marking when a source fingerprint changes
- added FTS5 lexical retrieval
- added append-only mission event journal
- added durable mission snapshots with optimistic revision checks
- added tests, CI, contribution docs and public roadmap

This release is an experimental foundation, not a production-readiness claim.
