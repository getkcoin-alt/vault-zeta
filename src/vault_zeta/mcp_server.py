"""Vault Zeta MCP Server — persistent long-term memory for any AI agent.

Wraps VaultZetaStore as a Model Context Protocol (MCP) server so that any
MCP-capable agent (OpenCode, Claude Code, Cursor, Antigravity, etc.) can read
and write durable memories from the sovereign local SQLite store.

Agents come and go — memory stays.

Tools:
  memory_save         Persist a durable fact with provenance and confidence.
  memory_search       FTS5 lexical search over stored memories.
  context_pack        Model-ready context formatted safely inside <vault_memories>.
  memory_list         Browse recent memories (newest first).
  memory_delete       Remove a memory by ID.
  vault_status        Health, DB path, and memory counts.
  event_append        Append a mission event to the journal.
  event_list          Read mission events by mission_id.
  mission_save        Save or update a mission snapshot (optimistic locking).
  mission_load        Load a mission snapshot by ID.
  bundle_export       Export vault data into a portable directory bundle.
  bundle_import       Import a portable bundle directory into this vault.

Run:
  uv run --python 3.12 -m vault_zeta.mcp_server
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Ensure vault_zeta is on sys.path
_here = Path(__file__).resolve().parent
_src = _here.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from vault_zeta import SecretInVault, VaultZetaStore  # noqa: E402

# Support both mcp 2.x (MCPServer) and mcp 1.x (FastMCP)
try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print(
            "ERROR: 'mcp' package not installed.\n"
            "Install with:\n"
            "  uv pip install 'mcp>=1.0'",
            file=sys.stderr,
        )
        sys.exit(1)

DB_PATH = os.environ.get("VAULT_ZETA_DB", os.path.expanduser("~/.vault-zeta/memory.db"))


def _fmt(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _memory_dict(m) -> dict:
    return {
        "id": m.id,
        "kind": m.kind,
        "content": m.content,
        "scope": m.scope,
        "source": m.source,
        "source_fingerprint": m.source_fingerprint,
        "confidence": m.confidence,
        "metadata": m.metadata,
        "stale": m.stale,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }


def create_server(db_path: str = DB_PATH) -> FastMCP:
    server = FastMCP(
        "vault-zeta",
        instructions=(
            "Vault Zeta provides sovereign, persistent long-term memory and mission continuity. "
            "Use memory_save to persist durable facts, user preferences, instructions, and insights. "
            "Use memory_search or context_pack to recall past context. "
            "Never store credentials or API keys in memory."
        ),
    )
    store = VaultZetaStore(db_path)

    @server.tool()
    def memory_save(
        content: str,
        kind: str = "semantic",
        scope: str = "global",
        source: str | None = None,
        confidence: float = 0.9,
    ) -> str:
        """Save a durable fact or insight to Vault Zeta's long-term memory.

        The memory persists across all agents, sessions, and restarts.
        Pass a clean, self-contained sentence as content.
        Kinds: semantic, episodic, procedural, failure, entity, preference.
        Credentials and secrets are automatically detected and refused.
        """
        try:
            mem = store.add_memory(
                content=content,
                kind=kind,
                scope=scope,
                source=source,
                confidence=float(confidence),
            )
            return _fmt({"saved": True, **_memory_dict(mem)})
        except SecretInVault as e:
            return _fmt({"saved": False, "error": "secret_rejected", "message": str(e)})
        except Exception as e:
            return _fmt({"saved": False, "error": str(e)})

    @server.tool()
    def memory_search(
        query: str,
        scope: str | None = None,
        include_stale: bool = False,
        limit: int = 10,
    ) -> str:
        """Search Vault Zeta's long-term memory using FTS5 lexical search.

        Returns memories ranked by relevance and confidence.
        This is how agents recall things learned in past sessions.
        """
        try:
            hits = store.search(
                query,
                scope=scope,
                include_stale=include_stale,
                limit=min(max(1, limit), 100),
            )
            return _fmt({
                "query": query,
                "count": len(hits),
                "memories": [_memory_dict(h) for h in hits],
            })
        except Exception as e:
            return _fmt({"error": str(e)})

    @server.tool()
    def context_pack(
        query: str,
        scope: str | None = None,
        limit: int = 8,
        max_chars: int = 4000,
    ) -> str:
        """Return model-ready recalled context safely wrapped in <vault_memories>.

        Treats recalled memory as untrusted context data to prevent prompt injection.
        """
        try:
            packed = store.context_pack(
                query,
                scope=scope,
                limit=min(max(1, limit), 50),
                max_chars=min(max(500, max_chars), 20000),
            )
            return _fmt(packed)
        except Exception as e:
            return _fmt({"error": str(e)})

    @server.tool()
    def memory_list(
        scope: str | None = None,
        limit: int = 20,
    ) -> str:
        """Browse memories from Vault Zeta (newest first).

        Useful for inspecting stored context without a specific search query.
        """
        try:
            hits = store.search(
                "",
                scope=scope,
                limit=min(max(1, limit), 100),
            )
            return _fmt({
                "count": len(hits),
                "memories": [_memory_dict(h) for h in hits],
            })
        except Exception as e:
            return _fmt({"error": str(e)})

    @server.tool()
    def memory_delete(memory_id: str) -> str:
        """Delete a specific memory from Vault Zeta by its ID."""
        try:
            store.get_memory(memory_id)
            store.db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            store.db.execute("DELETE FROM memories_fts WHERE memory_id = ?", (memory_id,))
            store.db.commit()
            return _fmt({"deleted": True, "id": memory_id})
        except KeyError:
            return _fmt({"deleted": False, "id": memory_id, "error": "not found"})
        except Exception as e:
            return _fmt({"deleted": False, "id": memory_id, "error": str(e)})

    @server.tool()
    def vault_status() -> str:
        """Health, DB path, memory count, and configuration of the Vault Zeta store."""
        try:
            total = store.db.execute("SELECT count(*) FROM memories").fetchone()[0]
            by_kind = store.db.execute(
                "SELECT kind, count(*) as cnt FROM memories GROUP BY kind ORDER BY cnt DESC"
            ).fetchall()
            missions = store.db.execute("SELECT count(*) FROM mission_snapshots").fetchone()[0]
            events = store.db.execute("SELECT count(*) FROM mission_events").fetchone()[0]
            return _fmt({
                "vault": "Vault Zeta",
                "version": "0.2.0",
                "db_path": str(store.path),
                "memories": total,
                "by_kind": {r["kind"]: r["cnt"] for r in by_kind},
                "missions": missions,
                "events": events,
            })
        except Exception as e:
            return _fmt({"error": str(e)})

    @server.tool()
    def event_append(
        mission_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> str:
        """Append an event to a mission's append-only journal.

        Events record what happened during long-running work (e.g. observation, correction, step).
        """
        try:
            seq = store.append_event(
                mission_id=mission_id,
                event_type=event_type,
                payload=payload,
            )
            return _fmt({"appended": True, "seq": seq, "mission_id": mission_id})
        except Exception as e:
            return _fmt({"appended": False, "error": str(e)})

    @server.tool()
    def event_list(mission_id: str, after_seq: int = 0) -> str:
        """Read ordered event log for a specific mission."""
        try:
            evs = store.events(mission_id=mission_id, after_seq=after_seq)
            return _fmt({
                "mission_id": mission_id,
                "count": len(evs),
                "events": [
                    {
                        "seq": e.seq,
                        "event_type": e.event_type,
                        "payload": e.payload,
                        "created_at": e.created_at,
                    }
                    for e in evs
                ],
            })
        except Exception as e:
            return _fmt({"error": str(e)})

    @server.tool()
    def mission_save(
        mission_id: str,
        status: str,
        snapshot: dict[str, Any],
        expected_revision: int | None = None,
    ) -> str:
        """Save or update a mission snapshot — the compact state needed to resume.

        Uses optimistic revision checks to prevent silent overwrites.
        """
        try:
            rev = store.save_mission(
                mission_id,
                status=status,
                snapshot=snapshot,
                expected_revision=expected_revision,
            )
            return _fmt({"saved": True, "mission_id": mission_id, "revision": rev})
        except Exception as e:
            return _fmt({"saved": False, "error": str(e)})

    @server.tool()
    def mission_load(mission_id: str) -> str:
        """Load a mission snapshot by ID to see where to resume."""
        try:
            snap = store.load_mission(mission_id)
            if snap is None:
                return _fmt({"found": False, "mission_id": mission_id})
            return _fmt({
                "found": True,
                "mission_id": snap.mission_id,
                "status": snap.status,
                "snapshot": snap.snapshot,
                "revision": snap.revision,
                "updated_at": snap.updated_at,
            })
        except Exception as e:
            return _fmt({"error": str(e)})

    @server.tool()
    def bundle_export(output_dir: str, vault_id: str = "vault-zeta") -> str:
        """Export vault data into a portable directory bundle with manifest and JSONL records."""
        try:
            out_path = store.export_bundle(output_dir, vault_id=vault_id)
            return _fmt({"exported": True, "directory": str(out_path)})
        except Exception as e:
            return _fmt({"exported": False, "error": str(e)})

    @server.tool()
    def bundle_import(input_dir: str) -> str:
        """Import a portable bundle directory into this Vault Zeta store (dedupes automatically)."""
        try:
            stats = store.import_bundle(input_dir)
            return _fmt({"imported": True, **stats})
        except Exception as e:
            return _fmt({"imported": False, "error": str(e)})

    return server


def main():
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
