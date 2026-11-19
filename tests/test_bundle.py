from vault_zeta import VaultZetaStore


def test_bundle_export_and_import(tmp_path):
    db1 = tmp_path / "zeta1.db"
    bundle_dir = tmp_path / "bundle"
    db2 = tmp_path / "zeta2.db"

    with VaultZetaStore(db1) as z1:
        z1.add_memory(
            kind="semantic",
            content="Zone 1 requires 25% moisture target.",
            scope="farm/alpha",
            confidence=0.92,
        )
        z1.append_event(
            mission_id="mission-101",
            event_type="observation",
            payload={"reading": 22},
        )
        z1.save_mission(
            "mission-101",
            status="running",
            snapshot={"step": "water"},
        )
        z1.export_bundle(bundle_dir, vault_id="test-vault")

    assert (bundle_dir / "manifest.json").exists()
    assert (bundle_dir / "memories.jsonl").exists()
    assert (bundle_dir / "events.jsonl").exists()
    assert (bundle_dir / "snapshots.jsonl").exists()

    with VaultZetaStore(db2) as z2:
        report = z2.import_bundle(bundle_dir)
        assert report["memories_added"] == 1
        assert report["events_added"] == 1
        assert report["snapshots_added"] == 1

        hits = z2.search("moisture", scope="farm/alpha")
        assert len(hits) == 1
        assert hits[0].content == "Zone 1 requires 25% moisture target."

        snap = z2.load_mission("mission-101")
        assert snap is not None
        assert snap.snapshot == {"step": "water"}

        # Importing again dedupes memories
        report2 = z2.import_bundle(bundle_dir)
        assert report2["memories_added"] == 0
        assert report2["memories_skipped"] == 1
