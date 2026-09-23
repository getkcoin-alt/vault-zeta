# Vault Zeta architecture

Vault Zeta starts with a deliberately small boundary:

```text
agent / application
       |
       v
+-------------------+
| Vault Zeta API    |
+-------------------+
   |        |       |
   v        v       v
memory   events   mission snapshot
   |        |       |
   +--------+-------+
            |
          SQLite
```

## Memory

Memory is durable context with provenance.

A record has a type, scope, source, source fingerprint, confidence, metadata and stale state. The first alpha uses FTS5 lexical retrieval because it is inspectable and has no external model dependency.

Embeddings can be added later as another retrieval signal. They should not become the only way to explain why a memory was returned.

## Events

Mission events are append-only.

Examples:

- observation
- tool_result
- correction
- pause
- resume
- priority_change
- verification
- failure

The library does not decide which event types an application is allowed to emit. That contract belongs to the caller.

## Mission snapshots

A snapshot is the compact state needed to resume a mission.

Snapshots use monotonically increasing revisions. A caller can provide `expected_revision` when saving so two workers do not silently overwrite one another.

The event log and snapshot serve different purposes:

- event log = what happened
- snapshot = where to resume

## Trust boundary

Vault Zeta **does not grant permission**.

It should be safe for an authorization layer to read Vault Zeta, but authorization must be decided elsewhere. A stored preference, past approval or remembered credential-related fact must never silently become a new permission grant.

## Current storage choice

SQLite is intentional for the first public alpha:

- local
- transactional
- inspectable
- easy to test
- no service required

If the design later moves to PostgreSQL or a distributed log, the data contracts should survive the migration.

## What needs evidence before scaling

Before calling the system production-ready, I want evidence around:

- concurrent writers
- corruption/recovery behavior
- larger stores and retrieval latency
- retrieval quality
- stale/conflicting memory
- privacy and encryption
- import/export stability
- long-running task resumption
- schema migrations
