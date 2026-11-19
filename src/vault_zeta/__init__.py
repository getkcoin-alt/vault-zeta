"""Vault Zeta — experimental continuity and memory layer for long-running AI systems."""

from .bundle import export_bundle, import_bundle
from .models import EventRecord, MemoryRecord, MissionSnapshot
from .redact import SecretInVault
from .store import RevisionConflict, VaultZetaStore

__all__ = [
    "EventRecord",
    "MemoryRecord",
    "MissionSnapshot",
    "RevisionConflict",
    "SecretInVault",
    "VaultZetaStore",
    "export_bundle",
    "import_bundle",
]

__version__ = "0.2.0"
