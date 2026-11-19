"""Vault Zeta — experimental continuity and memory layer for long-running AI systems."""

from .bundle import export_bundle, import_bundle, record_hash
from .eval import RetrievalEvalCase, RetrievalEvalResult, RetrievalEvalSummary, evaluate_retrieval
from .models import (
    EntityRecord,
    EventRecord,
    MemoryEntityLink,
    MemoryRecord,
    MissionSnapshot,
    SearchScoreBreakdown,
)
from .redact import SecretInVault, assert_clean, assert_clean_structure
from .store import RevisionConflict, VaultZetaStore

__all__ = [
    "EntityRecord",
    "EventRecord",
    "MemoryEntityLink",
    "MemoryRecord",
    "MissionSnapshot",
    "RetrievalEvalCase",
    "RetrievalEvalResult",
    "RetrievalEvalSummary",
    "RevisionConflict",
    "SearchScoreBreakdown",
    "SecretInVault",
    "VaultZetaStore",
    "assert_clean",
    "assert_clean_structure",
    "evaluate_retrieval",
    "export_bundle",
    "import_bundle",
    "record_hash",
]

__version__ = "0.2.2"
