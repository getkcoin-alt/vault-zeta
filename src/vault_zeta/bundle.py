"""Vault Zeta Bundle — portable export/import for long-term memory and mission continuity.

A bundle is a self-contained directory with:
- manifest.json: protocol version, vault_id, export timestamp, record counts
- memories.jsonl: durable memory records (content, kind, scope, source, confidence, lineage)
- entities.jsonl: named entities (optional)
- memory_entities.jsonl: memory-entity relationships (optional)
- tasks.jsonl: mission task graph nodes (optional)
- task_deps.jsonl: task graph dependencies (optional)
- events.jsonl: append-only mission events
- snapshots.jsonl: mission state snapshots
- state.json: counters and provenance metadata

Embeddings are intentionally never transported.
Secrets across all fields (content, source, metadata, payloads, snapshots, tasks)
are strictly verified before exporting.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .models import EventRecord, MissionSnapshot
from .redact import assert_clean, assert_clean_structure
from .store import RevisionConflict

PROTOCOL_VERSION = "1.2.0"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def content_hash(text: str) -> str:
    """Legacy text-only hash for backwards compatibility."""
    norm = " ".join((text or "").split())
    return hashlib.sha256(norm.encode()).hexdigest()


def record_hash(content: str, scope: str = "global", kind: str = "semantic") -> str:
    """Composite deduplication hash preventing collisions across scopes and kinds."""
    norm = " ".join((content or "").split())
    key = f"{scope.strip()}::{kind.strip()}::{norm}"
    return hashlib.sha256(key.encode()).hexdigest()


class MalformedBundle(ValueError):
    """The directory is not a valid Vault Zeta bundle."""


@dataclass(slots=True)
class BundleManifest:
    protocol_version: str = PROTOCOL_VERSION
    vault_id: str = "vault-zeta-default"
    exported_at: str = ""
    counts: dict[str, int] = None

    def __post_init__(self):
        if not self.exported_at:
            self.exported_at = utc_now_iso()
        if self.counts is None:
            self.counts = {}


def export_bundle(
    store,
    output_dir: str | Path,
    *,
    vault_id: str = "vault-zeta",
) -> Path:
    """Export the contents of a VaultZetaStore into a portable directory bundle."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # 1. Memories (Scan content, source, and metadata)
    mem_rows = store.db.execute("SELECT * FROM memories ORDER BY created_at ASC").fetchall()
    memories = [store._memory(r) for r in mem_rows]
    for m in memories:
        assert_clean(m.content, f"memory {m.id} content")
        assert_clean(m.source or "", f"memory {m.id} source")
        if m.metadata:
            assert_clean_structure(m.metadata, f"memory {m.id} metadata")

    with (out / "memories.jsonl").open("w", encoding="utf-8") as f:
        for m in memories:
            d = {
                "id": m.id,
                "kind": m.kind,
                "content": m.content,
                "content_sha256": content_hash(m.content),
                "record_sha256": record_hash(m.content, m.scope, m.kind),
                "scope": m.scope,
                "source": m.source,
                "source_fingerprint": m.source_fingerprint,
                "confidence": m.confidence,
                "metadata": m.metadata,
                "stale": m.stale,
                "created_at": m.created_at,
                "updated_at": m.updated_at,
                "supersedes_id": m.supersedes_id,
                "superseded_by": m.superseded_by,
            }
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    # 2. Entities & Relationships (if any)
    entity_rows = store.db.execute("SELECT * FROM entities ORDER BY name ASC").fetchall()
    entities = [
        {
            "id": r["id"],
            "name": r["name"],
            "type": r["type"],
            "metadata": json.loads(r["metadata_json"]),
            "created_at": r["created_at"],
        }
        for r in entity_rows
    ]
    for e in entities:
        assert_clean(e["name"], f"entity {e['id']} name")
        if e["metadata"]:
            assert_clean_structure(e["metadata"], f"entity {e['id']} metadata")

    if entities:
        with (out / "entities.jsonl").open("w", encoding="utf-8") as f:
            for e in entities:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

    link_rows = store.db.execute("SELECT * FROM memory_entities").fetchall()
    links = [
        {
            "memory_id": r["memory_id"],
            "entity_id": r["entity_id"],
            "relationship": r["relationship"],
        }
        for r in link_rows
    ]
    if links:
        with (out / "memory_entities.jsonl").open("w", encoding="utf-8") as f:
            for link in links:
                f.write(json.dumps(link, ensure_ascii=False) + "\n")

    # 3. Tasks & Dependencies (Phase 2)
    task_rows = store.db.execute("SELECT * FROM mission_tasks ORDER BY created_at ASC").fetchall()
    tasks = []
    for tr in task_rows:
        t = store._task(tr)
        assert_clean(t.title, f"task {t.task_id} title")
        if t.description:
            assert_clean(t.description, f"task {t.task_id} description")
        if t.payload:
            assert_clean_structure(t.payload, f"task {t.task_id} payload")
        if t.result:
            assert_clean_structure(t.result, f"task {t.task_id} result")
        tasks.append({
            "mission_id": t.mission_id,
            "task_id": t.task_id,
            "title": t.title,
            "description": t.description,
            "status": t.status,
            "dependencies": t.dependencies,
            "payload": t.payload,
            "result": t.result,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        })
    if tasks:
        with (out / "tasks.jsonl").open("w", encoding="utf-8") as f:
            for t in tasks:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")

    dep_rows = store.db.execute("SELECT * FROM mission_task_deps").fetchall()
    task_deps = [
        {"mission_id": r["mission_id"], "task_id": r["task_id"], "depends_on_task_id": r["depends_on_task_id"]}
        for r in dep_rows
    ]
    if task_deps:
        with (out / "task_deps.jsonl").open("w", encoding="utf-8") as f:
            for dep in task_deps:
                f.write(json.dumps(dep, ensure_ascii=False) + "\n")

    # 4. Events (Scan payloads)
    event_rows = store.db.execute("SELECT * FROM mission_events ORDER BY seq ASC").fetchall()
    events = [
        EventRecord(
            seq=int(r["seq"]),
            mission_id=r["mission_id"],
            event_type=r["event_type"],
            payload=json.loads(r["payload_json"]),
            created_at=r["created_at"],
            idempotency_key=r["idempotency_key"] if "idempotency_key" in r.keys() else None,
        )
        for r in event_rows
    ]
    for e in events:
        if e.payload:
            assert_clean_structure(e.payload, f"event {e.seq} payload ({e.mission_id})")

    with (out / "events.jsonl").open("w", encoding="utf-8") as f:
        for e in events:
            f.write(
                json.dumps(
                    {
                        "seq": e.seq,
                        "mission_id": e.mission_id,
                        "event_type": e.event_type,
                        "payload": e.payload,
                        "created_at": e.created_at,
                        "idempotency_key": e.idempotency_key,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    # 5. Snapshots (Scan snapshots)
    snap_rows = store.db.execute("SELECT * FROM mission_snapshots").fetchall()
    snapshots = [
        MissionSnapshot(
            mission_id=r["mission_id"],
            status=r["status"],
            snapshot=json.loads(r["snapshot_json"]),
            revision=int(r["revision"]),
            updated_at=r["updated_at"],
        )
        for r in snap_rows
    ]
    for s in snapshots:
        if s.snapshot:
            assert_clean_structure(s.snapshot, f"mission snapshot ({s.mission_id})")

    with (out / "snapshots.jsonl").open("w", encoding="utf-8") as f:
        for s in snapshots:
            f.write(
                json.dumps(
                    {
                        "mission_id": s.mission_id,
                        "status": s.status,
                        "snapshot": s.snapshot,
                        "revision": s.revision,
                        "updated_at": s.updated_at,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    # 6. Manifest
    manifest = BundleManifest(
        protocol_version=PROTOCOL_VERSION,
        vault_id=vault_id,
        counts={
            "memories": len(memories),
            "entities": len(entities),
            "memory_entities": len(links),
            "tasks": len(tasks),
            "task_deps": len(task_deps),
            "events": len(events),
            "snapshots": len(snapshots),
        },
    )
    (out / "manifest.json").write_text(
        json.dumps(asdict(manifest), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # 7. State
    state = {
        "memory_count": len(memories),
        "entity_count": len(entities),
        "task_count": len(tasks),
        "event_count": len(events),
        "snapshot_count": len(snapshots),
        "exported_at": manifest.exported_at,
    }
    (out / "state.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return out


def import_bundle(store, input_dir: str | Path) -> dict[str, int]:
    """Import a bundle directory into store with composite deduplication, entities, tasks, and provenance preservation."""
    src = Path(input_dir)
    manifest_file = src / "manifest.json"
    if not manifest_file.is_file():
        raise MalformedBundle(f"Missing manifest.json in {src}")

    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    proto = manifest_data.get("protocol_version", "1.0.0")
    if int(proto.split(".")[0]) != int(PROTOCOL_VERSION.split(".")[0]):
        raise MalformedBundle(
            f"Incompatible bundle protocol {proto}, this engine speaks {PROTOCOL_VERSION}"
        )

    # 1. Memories
    existing_rows = store.db.execute("SELECT content, scope, kind FROM memories").fetchall()
    known_record_hashes = {record_hash(r[0], r[1], r[2]) for r in existing_rows}

    memories_added = 0
    memories_skipped = 0

    memories_file = src / "memories.jsonl"
    deferred_lineage: list[tuple[str, str | None, str | None]] = []

    if memories_file.is_file():
        with memories_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                c = d["content"]
                s = d.get("scope", "global")
                k = d.get("kind", "semantic")
                rh = d.get("record_sha256") or record_hash(c, s, k)

                if rh in known_record_hashes:
                    memories_skipped += 1
                    continue

                mem_id = d.get("id")
                s_id = d.get("supersedes_id")
                s_by = d.get("superseded_by")
                if s_id or s_by:
                    deferred_lineage.append((mem_id, s_id, s_by))

                store.add_memory(
                    kind=k,
                    content=c,
                    scope=s,
                    source=d.get("source"),
                    source_fingerprint=d.get("source_fingerprint"),
                    confidence=float(d.get("confidence", 1.0)),
                    metadata=d.get("metadata"),
                    memory_id=mem_id,
                    stale=bool(d.get("stale", False)),
                    created_at=d.get("created_at"),
                    updated_at=d.get("updated_at"),
                    supersedes_id=None,
                    superseded_by=None,
                    reject_secrets=True,
                )
                known_record_hashes.add(rh)
                memories_added += 1

        if deferred_lineage:
            with store._lock, store.db:
                for mem_id, s_id, s_by in deferred_lineage:
                    store.db.execute(
                        "UPDATE memories SET supersedes_id = ?, superseded_by = ? WHERE id = ?",
                        (s_id, s_by, mem_id),
                    )

    # 2. Entities
    entities_added = 0
    entities_file = src / "entities.jsonl"
    if entities_file.is_file():
        with entities_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                meta_json = json.dumps(d.get("metadata") or {}, sort_keys=True, separators=(",", ":"))
                with store._lock, store.db:
                    cursor = store.db.execute(
                        """
                        INSERT INTO entities (id, name, type, metadata_json, created_at)
                        VALUES (?, ?, ?, ?, coalesce(?, CURRENT_TIMESTAMP))
                        ON CONFLICT(name, type) DO NOTHING
                        """,
                        (d["id"], d["name"], d["type"], meta_json, d.get("created_at")),
                    )
                    if cursor.rowcount > 0:
                        entities_added += 1

    # 3. Memory-Entity Links
    links_added = 0
    links_file = src / "memory_entities.jsonl"
    if links_file.is_file():
        with links_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                with store._lock, store.db:
                    cursor = store.db.execute(
                        """
                        INSERT INTO memory_entities (memory_id, entity_id, relationship)
                        VALUES (?, ?, ?)
                        ON CONFLICT DO NOTHING
                        """,
                        (d["memory_id"], d["entity_id"], d.get("relationship", "mentions")),
                    )
                    if cursor.rowcount > 0:
                        links_added += 1

    # 4. Tasks & Task Dependencies (Phase 2)
    tasks_added = 0
    tasks_file = src / "tasks.jsonl"
    if tasks_file.is_file():
        with tasks_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                with store._lock, store.db:
                    cursor = store.db.execute(
                        """
                        INSERT INTO mission_tasks (
                            mission_id, task_id, title, description, status, payload_json, result_json, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, coalesce(?, CURRENT_TIMESTAMP), coalesce(?, CURRENT_TIMESTAMP))
                        ON CONFLICT(mission_id, task_id) DO NOTHING
                        """,
                        (
                            d["mission_id"],
                            d["task_id"],
                            d["title"],
                            d.get("description", ""),
                            d.get("status", "pending"),
                            json.dumps(d.get("payload") or {}, sort_keys=True, separators=(",", ":")),
                            json.dumps(d.get("result") or {}, sort_keys=True, separators=(",", ":")),
                            d.get("created_at"),
                            d.get("updated_at"),
                        ),
                    )
                    if cursor.rowcount > 0:
                        tasks_added += 1

    task_deps_added = 0
    deps_file = src / "task_deps.jsonl"
    if deps_file.is_file():
        with deps_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                with store._lock, store.db:
                    cursor = store.db.execute(
                        """
                        INSERT INTO mission_task_deps (mission_id, task_id, depends_on_task_id)
                        VALUES (?, ?, ?)
                        ON CONFLICT DO NOTHING
                        """,
                        (d["mission_id"], d["task_id"], d["depends_on_task_id"]),
                    )
                    if cursor.rowcount > 0:
                        task_deps_added += 1

    # 5. Events (deduplicated by idempotency key or content hash)
    existing_events = store.db.execute(
        "SELECT mission_id, event_type, payload_json, created_at FROM mission_events"
    ).fetchall()
    known_event_hashes = {
        hashlib.sha256(f"{r[0]}::{r[1]}::{r[2]}::{r[3]}".encode()).hexdigest()
        for r in existing_events
    }

    events_added = 0
    events_skipped = 0
    events_file = src / "events.jsonl"
    if events_file.is_file():
        with events_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                payload_json = json.dumps(d.get("payload") or {}, sort_keys=True, separators=(",", ":"))
                eh = hashlib.sha256(
                    f"{d['mission_id']}::{d['event_type']}::{payload_json}::{d.get('created_at', '')}".encode()
                ).hexdigest()

                if eh in known_event_hashes:
                    events_skipped += 1
                    continue

                store.append_event(
                    mission_id=d["mission_id"],
                    event_type=d["event_type"],
                    payload=d.get("payload"),
                    created_at=d.get("created_at"),
                    idempotency_key=d.get("idempotency_key"),
                    reject_secrets=True,
                )
                known_event_hashes.add(eh)
                events_added += 1

    # 6. Snapshots
    snapshots_added = 0
    snapshots_skipped = 0
    snaps_file = src / "snapshots.jsonl"
    if snaps_file.is_file():
        with snaps_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                try:
                    store.save_mission(
                        mission_id=d["mission_id"],
                        status=d["status"],
                        snapshot=d["snapshot"],
                        forced_revision=int(d.get("revision", 1)),
                        updated_at=d.get("updated_at"),
                        reject_secrets=True,
                        only_if_newer=True,
                    )
                except RevisionConflict:
                    snapshots_skipped += 1
                else:
                    snapshots_added += 1

    return {
        "memories_added": memories_added,
        "memories_skipped": memories_skipped,
        "entities_added": entities_added,
        "entity_links_added": links_added,
        "tasks_added": tasks_added,
        "task_deps_added": task_deps_added,
        "events_added": events_added,
        "events_skipped": events_skipped,
        "snapshots_added": snapshots_added,
        "snapshots_skipped": snapshots_skipped,
    }
