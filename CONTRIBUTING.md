# Contributing to Vault Zeta

Thanks for being curious about the project.

The easiest way to help is to make one piece of continuity more measurable, more reliable or easier to understand.

Good contribution areas:

- retrieval evaluation
- SQLite behavior and migrations
- memory correction/supersession
- provenance
- entity linking
- import/export
- concurrency
- documentation
- adapters for agent frameworks
- privacy and encryption design
- tests for weird failure cases

## Setup

```bash
git clone https://github.com/getkcoin-alt/vault-zeta.git
cd vault-zeta
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
ruff check .
```

## Before a PR

Please keep the change focused and include tests when behavior changes.

A useful PR explains:

- the problem
- the smallest change that solves it
- how you verified it
- what remains uncertain

Please do not put real private memories, credentials, customer data or personal datasets into issues or test fixtures.

## One design rule

**Memory is not authority.**

If a change makes stored history automatically grant permission to execute something, send something, spend something or expose something, it needs a different design.

## Licensing

Vault Zeta is licensed under the [Apache License 2.0](LICENSE). By submitting a contribution for inclusion in the project, you agree that it can be distributed under that license.
