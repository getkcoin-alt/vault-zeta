import pytest

from vault_zeta import VaultZetaStore


def test_supersede_memory_creates_lineage(tmp_path):
    with VaultZetaStore(tmp_path / "super.db") as store:
        m1 = store.add_memory(
            kind="semantic",
            content="API endpoint is https://api.v1.example.com",
            scope="infra",
            confidence=0.8,
        )

        m2 = store.supersede_memory(
            old_memory_id=m1.id,
            new_content="API endpoint is https://api.v2.example.com",
            reason="Upgraded to v2 REST API",
            confidence=0.95,
        )

        assert m2.supersedes_id == m1.id
        assert m2.content == "API endpoint is https://api.v2.example.com"
        assert m2.metadata.get("superseded_reason") == "Upgraded to v2 REST API"

        # Check old memory state
        old_m1 = store.get_memory(m1.id)
        assert old_m1.stale is True
        assert old_m1.superseded_by == m2.id

        # Check lineage
        lineage = store.get_lineage(m1.id)
        assert len(lineage) == 2
        assert lineage[0].id == m1.id
        assert lineage[1].id == m2.id

        # Querying lineage from the newest node yields identical sequence
        lineage2 = store.get_lineage(m2.id)
        assert [m.id for m in lineage2] == [m1.id, m2.id]


def test_three_generation_supersession(tmp_path):
    with VaultZetaStore(tmp_path / "gen3.db") as store:
        g1 = store.add_memory(kind="semantic", content="Version 1.0 released")
        g2 = store.supersede_memory(g1.id, "Version 2.0 released", reason="v2 update")
        g3 = store.supersede_memory(g2.id, "Version 3.0 released", reason="v3 update")

        lineage = store.get_lineage(g2.id)
        assert [m.id for m in lineage] == [g1.id, g2.id, g3.id]


def test_superseded_memory_excluded_from_search_and_context(tmp_path):
    with VaultZetaStore(tmp_path / "search_super.db") as store:
        m1 = store.add_memory(
            kind="semantic",
            content="Default database timeout is 30 seconds",
            scope="database",
        )
        m2 = store.supersede_memory(
            old_memory_id=m1.id,
            new_content="Default database timeout is 60 seconds",
            reason="Increased under high load",
        )

        # Standard search returns ONLY m2
        hits = store.search("timeout", scope="database")
        assert len(hits) == 1
        assert hits[0].id == m2.id
        assert hits[0].content == "Default database timeout is 60 seconds"

        # Search with include_superseded=True and include_stale=True returns both
        all_hits = store.search("timeout", scope="database", include_stale=True, include_superseded=True)
        assert len(all_hits) == 2

        # Context pack contains only active memory
        pack = store.context_pack("timeout", scope="database")
        assert "60 seconds" in pack["context"]
        assert "30 seconds" not in pack["context"]


def test_cannot_supersede_already_superseded_memory(tmp_path):
    with VaultZetaStore(tmp_path / "err.db") as store:
        m1 = store.add_memory(kind="semantic", content="Original fact")
        _ = store.supersede_memory(m1.id, "Second fact")

        with pytest.raises(ValueError, match="already been superseded"):
            store.supersede_memory(m1.id, "Third fact branching off old node")
