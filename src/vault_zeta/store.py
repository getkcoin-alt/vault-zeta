from __future__ import annotations

import json
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterable

from .models import EventRecord, MemoryRecord, MissionSnapshot


class RevisionConflict(RuntimeError):
    """Raised when a caller tries to overwrite a newer mission snapshot."""


class VaultZetaStore:
    MEMORY_KINDS = {
        "episodic",
        "semantic",
        "procedural",
        "failure",
        "entity",
        "preference",
    }

    def __init__(self, path: str | Path = "vault_zeta.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA journal_mode = WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                scope TEXT NOT NULL,
                source TEXT,
                source_fingerprint TEXT,
                confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
                metadata_json TEXT NOT NULL,
                stale INTEGER NOT NULL DEFAULT 0 CHECK(stale IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                memory_id UNINDEXED,
                content,
                scope
            );

            CREATE TABLE IF NOT EXISTS mission_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_mission_events_mission_seq
            ON mission_events(mission_id, seq);

            CREATE TABLE IF NOT EXISTS mission_snapshots (
                mission_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                revision INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self.db.commit()

    def add_memory(
        self,
        *,
        kind: str,
        content: str,
        scope: str = "global",
        source: str | None = None,
        source_fingerprint: str | None = None,
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
        memory_id: str | None = None,
    ) -> MemoryRecord:
        if kind not in self.MEMORY_KINDS:
            raise ValueError(f"Unsupported memory kind: {kind}")
        content = content.strip()
        scope = scope.strip()
        if not content:
            raise ValueError("content must not be empty")
        if not scope:
            raise ValueError("scope must not be empty")
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")

        memory_id = memory_id or str(uuid.uuid4())
        metadata_json = json.dumps(metadata or {}, sort_keys=True, separators=(",", ":"))

        with self.db:
            self.db.execute(
                """
                INSERT INTO memories (
                    id, kind, content, scope, source, source_fingerprint,
                    confidence, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    kind,
                    content,
                    scope,
                    source,
                    source_fingerprint,
                    confidence,
                    metadata_json,
                ),
            )
            self.db.execute(
                "INSERT INTO memories_fts(memory_id, content, scope) VALUES (?, ?, ?)",
                (memory_id, content, scope),
            )

        return self.get_memory(memory_id)

    def get_memory(self, memory_id: str) -> MemoryRecord:
        row = self.db.execute(
            "SELECT * FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()
        if row is None:
            raise KeyError(memory_id)
        return self._memory(row)

    def search(
        self,
        query: str,
        *,
        scope: str | None = None,
        kinds: Iterable[str] | None = None,
        include_stale: bool = False,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")

        kind_list = tuple(kinds or ())
        unknown = set(kind_list) - self.MEMORY_KINDS
        if unknown:
            raise ValueError(f"Unsupported memory kinds: {sorted(unknown)}")

        tokens = re.findall(r"[A-Za-z0-9_]+", query)
        clauses: list[str] = []
        params: list[Any] = []

        if not include_stale:
            clauses.append("m.stale = 0")
        if scope is not None:
            clauses.append("m.scope = ?")
            params.append(scope)
        if kind_list:
            clauses.append("m.kind IN (" + ",".join("?" for _ in kind_list) + ")")
            params.extend(kind_list)

        where = (" AND " + " AND ".join(clauses)) if clauses else ""

        if tokens:
            fts_query = " ".join(f'"{token}"' for token in tokens)
            rows = self.db.execute(
                f"""
                SELECT m.*
                FROM memories_fts f
                JOIN memories m ON m.id = f.memory_id
                WHERE memories_fts MATCH ? {where}
                ORDER BY bm25(memories_fts), m.confidence DESC, m.updated_at DESC
                LIMIT ?
                """,
                [fts_query, *params, limit],
            ).fetchall()
        else:
            rows = self.db.execute(
                f"""
                SELECT m.*
                FROM memories m
                WHERE 1 = 1 {where}
                ORDER BY m.confidence DESC, m.updated_at DESC
                LIMIT ?
                """,
                [*params, limit],
            ).fetchall()

        return [self._memory(row) for row in rows]

    def mark_source_stale(self, source: str, *, current_fingerprint: str) -> int:
        """Mark memories stale when their source no longer matches the supplied fingerprint."""
        with self.db:
            cursor = self.db.execute(
                """
                UPDATE memories
                SET stale = 1, updated_at = CURRENT_TIMESTAMP
                WHERE source = ?
                  AND source_fingerprint IS NOT NULL
                  AND source_fingerprint != ?
                  AND stale = 0
                """,
                (source, current_fingerprint),
            )
        return cursor.rowcount

    def append_event(
        self,
        *,
        mission_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> int:
        mission_id = mission_id.strip()
        event_type = event_type.strip()
        if not mission_id or not event_type:
            raise ValueError("mission_id and event_type must not be empty")

        payload_json = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))
        with self.db:
            cursor = self.db.execute(
                """
                INSERT INTO mission_events(mission_id, event_type, payload_json)
                VALUES (?, ?, ?)
                """,
                (mission_id, event_type, payload_json),
            )
        return int(cursor.lastrowid)

    def events(self, mission_id: str, *, after_seq: int = 0) -> list[EventRecord]:
        rows = self.db.execute(
            """
            SELECT * FROM mission_events
            WHERE mission_id = ? AND seq > ?
            ORDER BY seq ASC
            """,
            (mission_id, after_seq),
        ).fetchall()
        return [
            EventRecord(
                seq=int(row["seq"]),
                mission_id=row["mission_id"],
                event_type=row["event_type"],
                payload=json.loads(row["payload_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def save_mission(
        self,
        mission_id: str,
        *,
        status: str,
        snapshot: dict[str, Any],
        expected_revision: int | None = None,
    ) -> int:
        mission_id = mission_id.strip()
        status = status.strip()
        if not mission_id or not status:
            raise ValueError("mission_id and status must not be empty")

        snapshot_json = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))

        with self.db:
            existing = self.db.execute(
                "SELECT revision FROM mission_snapshots WHERE mission_id = ?",
                (mission_id,),
            ).fetchone()

            if existing is None:
                if expected_revision not in (None, 0):
                    raise RevisionConflict(
                        f"mission {mission_id!r} does not exist; expected revision {expected_revision}"
                    )
                revision = 1
                self.db.execute(
                    """
                    INSERT INTO mission_snapshots(
                        mission_id, status, snapshot_json, revision
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (mission_id, status, snapshot_json, revision),
                )
                return revision

            current = int(existing["revision"])
            if expected_revision is not None and expected_revision != current:
                raise RevisionConflict(
                    f"mission {mission_id!r} is revision {current}, not {expected_revision}"
                )

            revision = current + 1
            self.db.execute(
                """
                UPDATE mission_snapshots
                SET status = ?, snapshot_json = ?, revision = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE mission_id = ?
                """,
                (status, snapshot_json, revision, mission_id),
            )
            return revision

    def load_mission(self, mission_id: str) -> MissionSnapshot | None:
        row = self.db.execute(
            "SELECT * FROM mission_snapshots WHERE mission_id = ?",
            (mission_id,),
        ).fetchone()
        if row is None:
            return None
        return MissionSnapshot(
            mission_id=row["mission_id"],
            status=row["status"],
            snapshot=json.loads(row["snapshot_json"]),
            revision=int(row["revision"]),
            updated_at=row["updated_at"],
        )

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "VaultZetaStore":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    @staticmethod
    def _memory(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            kind=row["kind"],
            content=row["content"],
            scope=row["scope"],
            source=row["source"],
            source_fingerprint=row["source_fingerprint"],
            confidence=float(row["confidence"]),
            metadata=json.loads(row["metadata_json"]),
            stale=bool(row["stale"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
