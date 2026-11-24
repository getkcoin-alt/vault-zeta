import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from vault_zeta import RevisionConflict, VaultZetaStore
from vault_zeta.mcp_server import create_server


def overlap_snapshot_writes(first_store, first_write, second_store, second_write):
    """Start the second write while the first holds an uncommitted SQLite write."""
    first_at_commit = Event()
    second_at_begin = Event()

    def pause_commit(sql):
        if sql == "COMMIT":
            first_at_commit.set()
            second_at_begin.wait(timeout=5)

    def mark_begin(sql):
        if sql.startswith("BEGIN"):
            second_at_begin.set()

    first_store.db.set_trace_callback(pause_commit)
    second_store.db.set_trace_callback(mark_begin)
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(first_write)
            assert first_at_commit.wait(timeout=5), "First writer did not reach commit"
            second = workers.submit(second_write)
            assert second_at_begin.wait(timeout=5), "Second writer did not reach its transaction"
            return first.result(timeout=5), second
    finally:
        first_store.db.set_trace_callback(None)
        second_store.db.set_trace_callback(None)


@pytest.mark.parametrize("expected_revision", [0, 1])
def test_only_one_connection_can_save_the_same_revision(tmp_path, expected_revision):
    db_path = tmp_path / "vault.db"
    with VaultZetaStore(db_path) as first, VaultZetaStore(db_path) as second:
        if expected_revision == 1:
            first.save_mission("mission", status="running", snapshot={"step": "start"})

        def save(store, step):
            return store.save_mission(
                "mission", status="running", snapshot={"step": step}, expected_revision=expected_revision
            )

        winner_revision, loser = overlap_snapshot_writes(
            first, lambda: save(first, "first"), second, lambda: save(second, "second")
        )

        assert winner_revision == expected_revision + 1
        with pytest.raises(RevisionConflict):
            loser.result()
        saved = second.load_mission("mission")
        assert saved.revision == winner_revision
        assert saved.snapshot == {"step": "first"}


def test_bundle_restore_keeps_concurrent_live_snapshot(tmp_path):
    bundle_path = tmp_path / "bundle"
    with VaultZetaStore(tmp_path / "source.db") as source:
        source.save_mission("mission", status="paused", snapshot={"source": "bundle"}, forced_revision=2)
        source.export_bundle(bundle_path)

    db_path = tmp_path / "target.db"
    with VaultZetaStore(db_path) as live, VaultZetaStore(db_path) as restore:
        live.save_mission("mission", status="running", snapshot={"step": "start"})
        revision, imported = overlap_snapshot_writes(
            live,
            lambda: live.save_mission(
                "mission", status="running", snapshot={"step": "live"}, expected_revision=1
            ),
            restore,
            lambda: restore.import_bundle(bundle_path),
        )

        assert imported.result()["snapshots_skipped"] == 1
        assert revision == 2
        saved = restore.load_mission("mission")
        assert saved.revision == revision
        assert saved.snapshot == {"step": "live"}


@pytest.mark.asyncio
async def test_mcp_snapshot_updates_require_the_loaded_revision(tmp_path):
    server = create_server(str(tmp_path / "vault.db"))

    async def call(name, arguments):
        result = await server.call_tool(name, arguments)
        return json.loads(result.content[0].text)

    create = {"mission_id": "mission", "status": "running", "snapshot": {"step": 1}}
    update = {**create, "snapshot": {"step": 2}}
    assert (await call("mission_save", create))["revision"] == 1

    rejected = await call("mission_save", update)
    assert rejected["saved"] is False
    assert rejected["error"] == "revision_conflict"
    current = await call("mission_load", {"mission_id": "mission"})
    assert current["snapshot"] == create["snapshot"]

    assert (await call("mission_save", {**update, "expected_revision": current["revision"]}))["revision"] == 2
    stale = await call("mission_save", {**create, "expected_revision": 1})
    assert stale["saved"] is False
    assert stale["error"] == "revision_conflict"
    latest = await call("mission_load", {"mission_id": "mission"})
    assert latest["snapshot"] == update["snapshot"]
