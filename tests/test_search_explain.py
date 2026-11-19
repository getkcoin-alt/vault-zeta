from vault_zeta import VaultZetaStore


def test_search_explain_breakdown(tmp_path):
    with VaultZetaStore(tmp_path / "explain.db") as store:
        store.add_memory(
            kind="semantic",
            content="PostgreSQL connection pooling is managed by PgBouncer with transaction mode.",
            scope="database",
            confidence=0.9,
        )
        store.add_memory(
            kind="semantic",
            content="Redis caching layer stores user sessions with 24 hour TTL.",
            scope="database",
            confidence=0.7,
        )

        results = store.search_explain("PgBouncer connection", scope="database")
        assert len(results) >= 1
        top = results[0]

        assert "PostgreSQL" in top.memory.content
        assert top.bm25_raw != 0.0
        assert 0.0 <= top.bm25_normalized <= 1.0
        assert top.confidence_weight == 0.9
        assert 0.0 <= top.recency_weight <= 1.0
        assert 0.0 <= top.final_score <= 1.0
        assert "BM25 match quality" in top.explanation
        assert "confidence" in top.explanation


def test_search_explain_no_tokens_fallback(tmp_path):
    with VaultZetaStore(tmp_path / "fallback.db") as store:
        store.add_memory(
            kind="semantic",
            content="System heartbeat check",
            confidence=0.95,
        )

        # Empty search query -> ranking defaults to confidence + recency
        results = store.search_explain("")
        assert len(results) == 1
        assert "No lexical tokens" in results[0].explanation
        assert results[0].confidence_weight == 0.95
