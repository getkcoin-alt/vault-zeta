# Security

Vault Zeta stores continuity data. That means even a tiny deployment can contain sensitive context.

## Reporting a vulnerability

Please do not open a public issue for a security vulnerability.

Until GitHub private vulnerability reporting is enabled for this repository, send a minimal report to **karnveer@scriza.in** with the affected version/commit and reproduction steps.

Do not include real API keys, unrelated private data or customer datasets.

## Current alpha boundaries

- the SQLite database is **not encrypted by Vault Zeta**
- callers are responsible for filesystem permissions and disk encryption
- there is no network server in the current package
- no authorization system is included
- metadata can itself be sensitive
- memory retrieval is not a truth guarantee
- source fingerprints help detect staleness but do not prove a source is trustworthy
- the current implementation has not had an independent security audit

Do not use the alpha as the only store for secrets or irreversible decision authority.
