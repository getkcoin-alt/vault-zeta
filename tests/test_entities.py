from vault_zeta import VaultZetaStore


def test_entity_indexing_and_linking(tmp_path):
    with VaultZetaStore(tmp_path / "entities.db") as store:
        m1 = store.add_memory(
            kind="semantic",
            content="Vault Zeta uses SQLite FTS5 for local deterministic search.",
            scope="architecture",
        )
        m2 = store.add_memory(
            kind="semantic",
            content="OpenCode connects to Vault Zeta via MCP stdio protocol.",
            scope="integration",
        )

        link1 = store.link_memory_entity(
            memory_id=m1.id,
            entity_name="SQLite FTS5",
            entity_type="technology",
            relationship="uses",
        )
        assert link1.entity_name == "SQLite FTS5"
        assert link1.relationship == "uses"

        store.link_memory_entity(
            memory_id=m1.id,
            entity_name="Vault Zeta",
            entity_type="project",
            relationship="defines",
        )

        store.link_memory_entity(
            memory_id=m2.id,
            entity_name="Vault Zeta",
            entity_type="project",
            relationship="mentions",
        )

        # Query entities for m1
        entities_m1 = store.get_entities_for_memory(m1.id)
        assert len(entities_m1) == 2
        names = {e.entity_name for e in entities_m1}
        assert names == {"SQLite FTS5", "Vault Zeta"}

        # Query memories for entity 'Vault Zeta'
        vz_mems = store.get_entity_memories("Vault Zeta")
        assert len(vz_mems) == 2

        # Query memories for entity 'Vault Zeta' with relationship 'defines'
        vz_defines = store.get_entity_memories("Vault Zeta", relationship="defines")
        assert len(vz_defines) == 1
        assert vz_defines[0].id == m1.id


def test_supersession_preserves_entity_links(tmp_path):
    with VaultZetaStore(tmp_path / "ent_super.db") as store:
        m1 = store.add_memory(
            kind="semantic",
            content="Kubernetes cluster hosted on AWS EKS",
            scope="cloud",
        )
        store.link_memory_entity(m1.id, "AWS", "cloud_provider", "runs_on")

        # Supersede m1
        m2 = store.supersede_memory(
            old_memory_id=m1.id,
            new_content="Kubernetes cluster migrated to Bare Metal Talos Linux",
            reason="Cloud egress cost reduction",
        )

        # Entity links should automatically copy over to new memory
        entities_m2 = store.get_entities_for_memory(m2.id)
        assert len(entities_m2) == 1
        assert entities_m2[0].entity_name == "AWS"
