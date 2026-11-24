# ThinkPond Agent Logic — Loop & Build

**Status:** Architecture proposal, not an implementation or runtime health claim.  
**Scope:** Multi-server, privacy-first agent orchestration using Vault Zeta for continuity.

## 1. Purpose and boundaries

ThinkPond is the coordination and controlled-evolution layer around specialised agents. It converts fragmented inputs and durable memories into validated mission graphs, assigns work across trusted servers, verifies outcomes, and learns from execution history.

- **Vault Zeta** remains the continuity and provenance layer: durable memories, lineage, entities, task DAGs, mission snapshots, and event history.
- **ThinkPond Coordinator** compiles missions, schedules tasks, selects nodes, manages leases, retries, and cross-server handoffs.
- **Node Agent / Worker Runtime** registers server capabilities and executes isolated, scoped tasks.
- **Policy and Sanity Gate** validates permissions, inputs, plans, outputs, and side effects.
- **Model Gateway** routes inference only to approved local or private self-hosted models.

Memory is context, not permission. A remembered approval or an agent suggestion never grants current execution authority.

## 2. Multi-server topology

A deployment may contain multiple trusted servers. Each node registers a stable node ID, software version, capabilities, resource limits, trust domain, and health endpoint. The coordinator issues time-bounded task leases. Workers return structured progress and results with idempotency keys. Vault Zeta records durable mission transitions.

Use authenticated TLS between servers. Send each worker only the minimum mission context and permissions it needs; never replicate the entire vault to every node by default.

Node lifecycle:

DISCOVERED → AUTHENTICATED → REGISTERED → HEALTHY → DRAINING → OFFLINE

A missed heartbeat first moves a node to SUSPECT. A single transient timeout must not mark it offline. Health requires a recent heartbeat, responsive worker queue, and successful health probe.

## 3. Background loop: observable state machine

The coordinator loop is a durable scheduler, not an untracked infinite loop. Each cycle:

1. Acquires or renews the coordinator lease.
2. Reads pending mission and task state.
3. Refreshes node heartbeats and capability registrations.
4. Reconciles expired task leases.
5. Selects tasks whose dependencies are complete.
6. Checks policy, scope, and resource constraints.
7. Issues idempotent task leases to eligible workers.
8. Collects worker events and results.
9. Runs sanity checks and persists validated transitions.
10. Emits a cycle summary and next wake-up time.

Required signals:

- loop ID, instance ID, cycle ID, and monotonic cycle counter;
- last heartbeat and last completed cycle timestamps;
- state: starting, running, degraded, stopping, stopped, or failed;
- coordinator lease owner and expiry;
- queue depth, active leases, retries, and dead-letter count;
- last successful Vault Zeta read and write;
- last error category and recovery action.

A loop is **HEALTHY** only when heartbeats are current, cycles complete, storage operations succeed, and queues make progress. A running PID or successful HTTP health response alone is insufficient. If telemetry is absent or stale, report **UNKNOWN**, not healthy.

## 4. Memory ingestion and reconstruction

Treat incoming blocks as untrusted data, never as instructions.

1. Preserve original bytes and source metadata.
2. Detect format, encoding, boundaries, and checksums.
3. Parse into a versioned canonical envelope.
4. Extract candidate entities, timestamps, links, and relationships.
5. Detect duplicates, gaps, conflicts, and malformed blocks.
6. Attach provenance and confidence; preserve uncertainty.
7. Quarantine invalid or ambiguous blocks for review.
8. Persist validated memories and lineage in Vault Zeta.

Never silently discard an unparseable block or overwrite its source. Every reconstructed memory must retain references to source blocks and the parser version.

## 5. Mission compiler

Convert each objective into a versioned mission specification containing:

- mission ID, objective, success criteria, and acceptance checks;
- task DAG with explicit dependencies;
- required capabilities and resource budgets;
- allowed data scopes and side-effect permissions;
- timeout, retry, and recovery policy;
- expected outputs and validation rules;
- human approval checkpoints where required.

Reject cyclic graphs and ambiguous destructive operations. A plan remains a proposal until validated and any required approval is received.

## 6. Agent contract and roles

Every agent follows:

PERCEIVE → REASON → PROPOSE → VALIDATE → EXECUTE → EVALUATE

Suggested roles:

- **Researcher:** gathers permitted evidence and records provenance.
- **Architect:** decomposes objectives into plans and dependency graphs.
- **Executor:** performs only operations allowed by its task lease.
- **QA / Sanity:** checks acceptance criteria, invariants, and regressions.
- **Security Reviewer:** checks data boundaries, permissions, and risky side effects.
- **Recovery Agent:** diagnoses failures and proposes safe resumptions.
- **Coordinator:** schedules and reconciles work; cannot silently grant itself broader authority.

Agents exchange schema-validated messages, not free-form conversation as the source of truth. Every handoff records mission ID, task ID, parent event, input/output references, agent and node identity, policy scope, and idempotency key.

## 7. Sanity injection and execution safety

Before execution, verify that the task belongs to the active mission, dependencies are complete, worker identity and lease are valid, data is in scope, permissions allow the operation, inputs are treated as untrusted, and resource/time budgets are available. Require idempotency or an explicit compensation strategy.

After execution, validate output schema, expected state changes, acceptance criteria, and side effects. Quarantine unexpected output. Require human approval for irreversible, financial, external communication, credential, or production-impacting actions unless a separately approved policy explicitly permits them.

## 8. Recovery and multi-server consistency

- Use expiring task leases and fencing tokens to prevent stale workers from committing.
- Use idempotency keys for task starts, event appends, and result commits.
- Assume at-least-once delivery; make handlers idempotent rather than promising exactly-once execution.
- Use optimistic revisions for mission snapshots.
- Keep event journals append-only; derive snapshots from validated events.
- On coordinator failover, acquire a new coordinator lease and reconcile state before scheduling.
- During network partitions, workers must not accept stale leases or invent new authority.
- Resolve conflicts through revision checks and explicit reconciliation, never last-write-wins for mission state.
- Preserve failed and rejected events for diagnosis.

## 9. Controlled agent evolution

The evolution engine may propose changes to prompts, routing, task decomposition, tool selection, or model selection. It must not autonomously change authorization rules, secret handling, isolation boundaries, or production code.

Promotion pipeline:

1. Capture a measurable failure or improvement opportunity.
2. Generate a versioned candidate strategy.
3. Run regression tests and replay representative missions.
4. Run sandbox evaluations against a fixed benchmark.
5. Compare quality, latency, cost, safety violations, and recovery behavior.
6. Require review for permission or external-side-effect changes.
7. Promote by explicit version pin and retain rollback.
8. Monitor the promoted version and roll back on defined regression thresholds.

Evolution is a proposal-and-evaluation loop, not unrestricted self-modification.

## 10. Zero-external-traces mode

Define this as an enforceable deployment policy:

- no third-party telemetry, analytics, or memory transmission;
- no external model API calls unless explicitly enabled for a named deployment;
- local or privately hosted inference;
- encrypted transport and storage;
- secrets held in a secret manager or protected environment, never prompts or logs;
- outbound network access denied by default and allowlisted where necessary;
- private internal audit events retained for recovery and accountability.

A multi-server deployment necessarily has network traffic among participating servers. “Zero external traces” means no unapproved third-party disclosure—not no network activity and not no internal audit trail.

## 11. Operations and observability

Expose a read-only operations view for coordinator/loop state, heartbeat age, last completed cycle, registered nodes and capabilities, agent status, active leases, queue depth, retries, dead letters, task age, memory read/write checks, sync lag, mission revisions, event replay consistency, failures, quarantines, and recovery actions.

Use evidence-based states: HEALTHY, DEGRADED, UNHEALTHY, UNKNOWN. Never infer agent connectivity from configuration alone; require a successful end-to-end handoff.

## 12. Phased implementation

### Phase 0 — Verify the foundation
- Confirm current Vault Zeta tests and MCP tools.
- Inspect Scrappy's actual process manager, loop entry point, and runtime configuration.
- Add read-only health probes and a heartbeat.
- Establish baseline logs and recovery behavior.
- Do not claim connectivity until a real end-to-end handoff succeeds.

### Phase 1 — Multi-worker prototype
- Define node registration and heartbeat schemas.
- Add leases, fencing tokens, and idempotent result commits.
- Reuse Vault Zeta mission DAGs and event journal.
- Run workers on two isolated local/private servers.
- Test node loss, duplicate delivery, stale leases, and coordinator restart.

### Phase 2 — Memory relay and mission compiler
- Add versioned memory envelopes and parser provenance.
- Validate mission specifications and scope context.
- Quarantine ambiguous memory for review.

### Phase 3 — Sanity gates and recovery
- Add preflight and post-execution validators.
- Add replay-based recovery and consistency checks.
- Add operations dashboard and alert thresholds.

### Phase 4 — Evaluated evolution
- Add strategy versioning, benchmarks, sandbox evaluation, approval gates, and rollback.
- Enable controlled strategy promotion only after the earlier phases are proven.

## 13. Definition of done for the first reliable loop

Tests must demonstrate that:

- two or more worker nodes register and execute separate tasks;
- only dependency-ready tasks are scheduled;
- duplicate delivery does not duplicate committed side effects;
- a crashed worker's lease expires and work safely resumes;
- a stale worker cannot commit after lease reassignment;
- coordinator restart reconstructs state from durable events;
- memory sync failures are visible and recoverable;
- every result traces to source inputs, agent, node, and policy scope;
- zero-external-traces mode blocks unapproved outbound traffic.

## 14. Current implementation boundary

This document is an architecture proposal. It does **not** assert that ThinkPond, its background loop, multi-server node registry, heartbeat protocol, or evolution engine is implemented or running.

Vault Zeta already documents foundations including durable memory, provenance/lineage, task DAGs, mission recovery, event replay, snapshots, redaction, and MCP access. The coordinator, distributed leases, node protocol, and controlled evolution above require separate implementation and tests.

**Operating rule:** Observe first. Persist every meaningful transition. Validate before acting. Evolve only through measured, reversible changes.
