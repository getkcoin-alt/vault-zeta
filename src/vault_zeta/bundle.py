"""Vault Zeta Bundle — portable export/import for long-term memory.

A bundle is a self-contained directory with:
- manifest.json: protocol version, vault_id, export timestamp, record counts
- memories.jsonl: durable memory records (content, kind, scope, source, confidence)
- events.jsonl: append-only mission events
- snapshots.jsonl: mission state snapshots
- state.json: counters and provenance metadata

Embeddings are intentionally never transported.
Secrets are strictly checked with redact.assert_clean before exporting.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .models import EventRecord, MissionSnapshot
from .redact import assert_clean

PROTOCOL_VERSION = "1.0.0"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def content_hash(text: str) -> str:
    norm = " ".join((text or "").split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


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

    # 1. Memories
    mem_rows = store.db.execute("SELECT * FROM memories ORDER BY created_at ASC").fetchall()
    memories = [store._memory(r) for r in mem_rows]
    for m in memories:
        assert_clean(m.content, f"memory {m.id}")
        assert_clean(m.source or "", f"memory source {m.id}")

    with (out / "memories.jsonl").open("w", encoding="utf-8") as f:
        for m in memories:
            d = {
                "id": m.id,
                "kind": m.kind,
                "content": m.content,
                "content_sha256": content_hash(m.content),
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

    # 2. Events
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

    # 3. Snapshots
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
    """Import a bundle directory into store, deduplicating memories by content_sha256."""
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

    # Dedupe set from store
    existing_rows = store.db.execute("SELECT content FROM memories").fetchall()
    known_hashes = {content_hash(r[0]) for r in existing_rows}

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
                ch = d.get("content_sha256") or content_hash(d["content"])
                if ch in known_hashes:
                    memories_skipped += 1
                    continue

                store.add_memory(
                    kind=d.get("kind", "semantic"),
                    content=d["content"],
                    scope=d.get("scope", "global"),
                    source=d.get("source"),
                    source_fingerprint=d.get("source_fingerprint"),
                    confidence=float(d.get("confidence", 1.0)),
                    metadata=d.get("metadata"),
                    memory_id=d.get("id"),
                )
                known_hashes.add(ch)
                memories_added += 1

    events_added = 0
    events_file = src / "events.jsonl"
    if events_file.is_file():
        with events_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                store.append_event(
                    mission_id=d["mission_id"],
                    event_type=d["event_type"],
                    payload=d.get("payload"),
                )
                events_added += 1

    snapshots_added = 0
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
                    )
                    snapshots_added += 1
                except Exception:
                    pass

    return {
        "memories_added": memories_added,
        "memories_skipped": memories_skipped,
        "events_added": events_added,
        "snapshots_added": snapshots_added,
    }
