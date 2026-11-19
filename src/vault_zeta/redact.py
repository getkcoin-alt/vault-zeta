"""Secret detection for Vault Zeta.

A memory record or bundle is designed to be persistent and potentially shared
across agents and machines. A credential inside one is a credential published.
So this runs at the sink — every record on its way into memory — rather than
trusting each caller or agent to have been careful.

Detection is by value shape, not by key name. If an agent tries to save
"deploy it with sk-live-abc123", that sentence is refused so credentials
never contaminate long-term memory.
"""

from __future__ import annotations

import re
from typing import Final

SECRET_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("openai-style key", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b")),
    ("aws access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
    ),
    (
        "private key block",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ),
    ("bearer/basic header", re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._\-+/=]{20,}")),
    (
        "connection string with password",
        re.compile(r"(?i)\b[a-z][a-z0-9+.\-]*://[^\s:/@]+:[^\s/@]{6,}@"),
    ),
)


class SecretInVault(ValueError):
    """A credential was found in content bound for Vault Zeta memory."""

    def __init__(self, kind: str, where: str = "memory") -> None:
        super().__init__(
            f"Refusing to save: detected what looks like a {kind} in {where}. "
            "Vault Zeta memory is persistent and portable — secrets must stay in the host's "
            "own secret store or environment variables, never written to memory. "
            "Redact or remove the credential and try again."
        )
        self.kind = kind
        self.where = where


def find_secret(text: str) -> str | None:
    """Return the kind of credential found in text, or None if it looks clean."""
    if not text:
        return None
    for kind, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            return kind
    return None


def assert_clean(text: str, where: str = "memory") -> None:
    """Raise SecretInVault if text carries something credential-shaped."""
    kind = find_secret(text)
    if kind is not None:
        raise SecretInVault(kind, where)


def mask(text: str) -> str:
    """Replace credential-shaped runs with [REDACTED] for safe logging."""
    out = text or ""
    for _kind, pattern in SECRET_PATTERNS:
        out = pattern.sub("[REDACTED]", out)
    return out
