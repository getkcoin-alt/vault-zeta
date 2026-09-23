from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    id: str
    kind: str
    content: str
    scope: str
    source: str | None
    source_fingerprint: str | None
    confidence: float
    metadata: dict[str, Any]
    stale: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class EventRecord:
    seq: int
    mission_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: str


@dataclass(frozen=True, slots=True)
class MissionSnapshot:
    mission_id: str
    status: str
    snapshot: dict[str, Any]
    revision: int
    updated_at: str
