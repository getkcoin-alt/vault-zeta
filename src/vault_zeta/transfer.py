"""Versioned, deterministic JSON transfer without filesystem side effects."""

from __future__ import annotations

import json
import math
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import fields

from .models import EventRecord, MemoryRecord, MissionSnapshot


@contextmanager
def _transaction(db):
    name = "transfer_" + uuid.uuid4().hex
    db.execute(f"SAVEPOINT {name}")
    try:
        yield
    except BaseException:
        db.execute(f"ROLLBACK TO {name}")
        raise
    finally:
        db.execute(f"RELEASE {name}")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def export_json(store) -> str:
    envelope = {"schema_version": 1}
    with _transaction(store.db):
        for collection, table, order, json_field in (
            ("memories", "memories", "id", "metadata"),
            ("events", "mission_events", "seq", "payload"),
            ("snapshots", "mission_snapshots", "mission_id", "snapshot"),
        ):
            records = []
            for row in store.db.execute(f"SELECT * FROM {table} ORDER BY {order}"):
                record = dict(row)
                record[json_field] = json.loads(record.pop(json_field + "_json"))
                if collection == "memories":
                    record["stale"] = bool(record["stale"])
                records.append(record)
            envelope[collection] = records
    return _json(envelope) + "\n"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def _validate(envelope, kinds):
    if not isinstance(envelope, dict) or set(envelope) != {"schema_version", "memories", "events", "snapshots"}:
        raise ValueError("Invalid transfer envelope")
    if type(envelope["schema_version"]) is not int or envelope["schema_version"] != 1:
        raise ValueError("Unsupported transfer schema version")
    for collection, model, identity, nested in (
        ("memories", MemoryRecord, "id", "metadata"),
        ("events", EventRecord, "seq", "payload"),
        ("snapshots", MissionSnapshot, "mission_id", "snapshot"),
    ):
        rows = envelope[collection]
        if not isinstance(rows, list):
            raise ValueError(f"{collection} must be an array")
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {field.name for field in fields(model)}:
                raise ValueError(f"Invalid {collection} record fields")
            for key, value in row.items():
                if key == nested:
                    if not isinstance(value, dict):
                        raise ValueError(f"{key} must be an object")
                    _json(value)
                elif key in ("seq", "revision"):
                    if type(value) is not int or not 1 <= value <= 2**63 - 1:
                        raise ValueError(f"{key} must be a positive SQLite integer")
                elif key == "stale":
                    if type(value) is not bool:
                        raise ValueError("stale must be a boolean")
                elif key == "confidence":
                    if type(value) not in (int, float) or not 0 <= value <= 1 or not math.isfinite(value):
                        raise ValueError("confidence must be between 0 and 1")
                elif key in ("source", "source_fingerprint"):
                    if value is not None and not isinstance(value, str):
                        raise ValueError(f"{key} must be a string or null")
                elif not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{key} must be a nonempty string")
            if collection == "memories" and row["kind"] not in kinds:
                raise ValueError("Unsupported memory kind")
            if row[identity] in seen:
                raise ValueError(f"Duplicate identifier in {collection}")
            seen.add(row[identity])


def import_json(store, document: str) -> None:
    envelope = json.loads(document, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    _validate(envelope, store.MEMORY_KINDS)
    try:
        with _transaction(store.db):
            for collection, table, nested in (
                ("memories", "memories", "metadata"),
                ("events", "mission_events", "payload"),
                ("snapshots", "mission_snapshots", "snapshot"),
            ):
                for row in envelope[collection]:
                    columns = dict(row)
                    columns[nested + "_json"] = _json(columns.pop(nested))
                    names = ",".join(columns)  # Keys have been checked against the fixed dataclasses.
                    placeholders = ",".join("?" for _ in columns)
                    store.db.execute(f"INSERT INTO {table} ({names}) VALUES ({placeholders})", tuple(columns.values()))
                    if collection == "memories":
                        store.db.execute(
                            "INSERT INTO memories_fts(memory_id,content,scope) VALUES (?,?,?)",
                            (row["id"], row["content"], row["scope"]),
                        )
    except sqlite3.IntegrityError as exc:
        raise ValueError("Import conflicts with an existing identifier; no records were imported") from exc
