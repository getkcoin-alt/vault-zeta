from vault_zeta import VaultZetaStore


def test_bundle_exports_and_imports_entities_and_lineage(tmp_path):
    db1 = tmp_path / "bundle_src.db"
    bundle_dir = tmp_path / "bundle_out"
    db2 = tmp_path / "bundle_dst.db"

    with VaultZetaStore(db1) as s1:
        m1 = s1.add_memory(
            kind="semantic",
            content="Old primary DNS server 1.1.1.1",
            scope="net",
        )
        s1.link_memory_entity(m1.id, "Cloudflare DNS", "infra", "uses")

        m2 = s1.supersede_memory(
            old_memory_id=m1.id,
            new_content="New primary DNS server 8.8.8.8",
            reason="Switched to Google Public DNS",
        )
        s1.link_memory_entity(m2.id, "Google DNS", "infra", "uses")

        s1.export_bundle(bundle_dir)

    with VaultZetaStore(db2) as s2:
        report = s2.import_bundle(bundle_dir)
        assert report["memories_added"] == 2
        assert report["entities_added"] >= 2
        assert report["entity_links_added"] >= 2

        # Check lineage in imported store
        lineage = s2.get_lineage(m1.id)
        assert len(lineage) == 2
        assert lineage[0].id == m1.id
        assert lineage[1].id == m2.id
        assert lineage[0].superseded_by == m2.id
        assert lineage[1].supersedes_id == m1.id

        # Verify entity links
        ent_m2 = s2.get_entities_for_memory(m2.id)
        assert any(e.entity_name == "Google DNS" for e in ent_m2)
