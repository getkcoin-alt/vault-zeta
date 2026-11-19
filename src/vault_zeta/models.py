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
    supersedes_id: str | None = None
    superseded_by: str | None = None


@dataclass(frozen=True, slots=True)
class EntityRecord:
    id: str
    name: str
    type: str
    metadata: dict[str, Any]
    created_at: str


@dataclass(frozen=True, slots=True)
class MemoryEntityLink:
    memory_id: str
    entity_id: str
    entity_name: str
    entity_type: str
    relationship: str


@dataclass(frozen=True, slots=True)
class SearchScoreBreakdown:
    memory: MemoryRecord
    bm25_raw: float
    bm25_normalized: float
    confidence_weight: float
    recency_weight: float
    final_score: float
    explanation: str


@dataclass(frozen=True, slots=True)
class EventRecord:
    seq: int
    mission_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: str
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class MissionSnapshot:
    mission_id: str
    status: str
    snapshot: dict[str, Any]
    revision: int
    updated_at: str


@dataclass(frozen=True, slots=True)
class TaskRecord:
    mission_id: str
    task_id: str
    title: str
    description: str
    status: str  # pending, running, completed, failed, skipped, blocked
    dependencies: list[str]
    payload: dict[str, Any]
    result: dict[str, Any]
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ResumptionPlan:
    mission_id: str
    status: str
    revision: int
    last_event_seq: int
    completed_task_ids: list[str]
    ready_task_ids: list[str]
    blocked_task_ids: list[str]
    failed_task_ids: list[str]
    in_progress_recovered_task_ids: list[str]
    snapshot: dict[str, Any] | None
