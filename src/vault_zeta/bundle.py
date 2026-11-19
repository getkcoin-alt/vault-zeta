"""Vault Zeta Bundle — portable export/import for long-term memory.

A bundle is a self-contained directory with:
- manifest.json: protocol version, vault_id, export timestamp, record counts
- memories.jsonl: durable memory records (content, kind, scope, source, confidence)
- events.jsonl: append-only mission events
- snapshots.jsonl: mission state snapshots
- state.json: counters and provenance metadata

Embeddings are intentionally never transported.
Secrets across all fields (content, source, metadata, payloads, snapshots)
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

PROTOCOL_VERSION = "1.0.0"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def content_hash(text: str) -> str:
    """Legacy text-only hash for backwards compatibility."""
    norm = " ".join((text or "").split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def record_hash(content: str, scope: str = "global", kind: str = "semantic") -> str:
    """Composite deduplication hash preventing collisions across scopes and kinds."""
    norm = " ".join((content or "").split())
    key = f"{scope.strip()}::{kind.strip()}::{norm}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


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
            }
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    # 2. Events (Scan payloads)
    event_rows = store.db.execute("SELECT * FROM mission_events ORDER BY seq ASC").fetchall()
    events = [
        EventRecord(
            seq=int(r["seq"]),
            mission_id=r["mission_id"],
            event_type=r["event_type"],
            payload=json.loads(r["payload_json"]),
            created_at=r["created_at"],
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
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    # 3. Snapshots (Scan snapshots)
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

    # 4. Manifest
    manifest = BundleManifest(
        protocol_version=PROTOCOL_VERSION,
        vault_id=vault_id,
        counts={
            "memories": len(memories),
            "events": len(events),
            "snapshots": len(snapshots),
        },
    )
    (out / "manifest.json").write_text(
        json.dumps(asdict(manifest), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # 5. State
    state = {
        "memory_count": len(memories),
        "event_count": len(events),
        "snapshot_count": len(snapshots),
        "exported_at": manifest.exported_at,
    }
    (out / "state.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return out


def import_bundle(store, input_dir: str | Path) -> dict[str, int]:
    """Import a bundle directory into store with composite deduplication and provenance preservation."""
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

    # 1. Existing memory composite hashes
    existing_rows = store.db.execute("SELECT content, scope, kind FROM memories").fetchall()
    known_record_hashes = {record_hash(r[0], r[1], r[2]) for r in existing_rows}

    memories_added = 0
    memories_skipped = 0

    memories_file = src / "memories.jsonl"
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

                store.add_memory(
                    kind=k,
                    content=c,
                    scope=s,
                    source=d.get("source"),
                    source_fingerprint=d.get("source_fingerprint"),
                    confidence=float(d.get("confidence", 1.0)),
                    metadata=d.get("metadata"),
                    memory_id=d.get("id"),
                    stale=bool(d.get("stale", False)),
                    created_at=d.get("created_at"),
                    updated_at=d.get("updated_at"),
                    reject_secrets=True,
                )
                known_record_hashes.add(rh)
                memories_added += 1

    # 2. Existing event signatures to prevent event duplication
    existing_events = store.db.execute(
        "SELECT mission_id, event_type, payload_json, created_at FROM mission_events"
    ).fetchall()
    known_event_hashes = {
        hashlib.sha256(f"{r[0]}::{r[1]}::{r[2]}::{r[3]}".encode("utf-8")).hexdigest()
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
                    f"{d['mission_id']}::{d['event_type']}::{payload_json}::{d.get('created_at', '')}".encode("utf-8")
                ).hexdigest()

                if eh in known_event_hashes:
                    events_skipped += 1
                    continue

                store.append_event(
                    mission_id=d["mission_id"],
                    event_type=d["event_type"],
                    payload=d.get("payload"),
                    created_at=d.get("created_at"),
                    reject_secrets=True,
                )
                known_event_hashes.add(eh)
                events_added += 1

    # 3. Snapshots (preserves higher revision or creates new)
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
                mid = d["mission_id"]
                current = store.load_mission(mid)
                imported_rev = int(d.get("revision", 1))

                if current is not None and current.revision >= imported_rev:
                    snapshots_skipped += 1
                    continue

                store.save_mission(
                    mission_id=mid,
                    status=d["status"],
                    snapshot=d["snapshot"],
                    forced_revision=imported_rev,
                    updated_at=d.get("updated_at"),
                    reject_secrets=True,
                )
                snapshots_added += 1

    return {
        "memories_added": memories_added,
        "memories_skipped": memories_skipped,
        "events_added": events_added,
        "events_skipped": events_skipped,
        "snapshots_added": snapshots_added,
        "snapshots_skipped": snapshots_skipped,
    }
