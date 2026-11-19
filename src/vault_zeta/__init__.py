"""Vault Zeta — experimental continuity and memory layer for long-running AI systems."""

from .bundle import export_bundle, import_bundle, record_hash
from .models import EventRecord, MemoryRecord, MissionSnapshot
from .redact import SecretInVault, assert_clean, assert_clean_structure
from .store import RevisionConflict, VaultZetaStore

__all__ = [
    "EventRecord",
    "MemoryRecord",
    "MissionSnapshot",
    "RevisionConflict",
    "SecretInVault",
    "VaultZetaStore",
    "assert_clean",
    "assert_clean_structure",
    "export_bundle",
    "import_bundle",
    "record_hash",
]

__version__ = "0.2.1"
