from vault_zeta import (
    RetrievalEvalCase,
    VaultZetaStore,
    evaluate_retrieval,
)


def test_retrieval_benchmark_precision_recall_mrr(tmp_path):
    with VaultZetaStore(tmp_path / "bench.db") as store:
        # 1. Corpus of distinct technical memories
        m_docker = store.add_memory(
            kind="procedural",
            content="Docker containers are built using multi-stage Dockerfile with alpine base.",
            scope="devops",
        )
        m_k8s = store.add_memory(
            kind="procedural",
            content="Kubernetes pods run with read-only root filesystems and non-root UID 10001.",
            scope="devops",
        )
        m_auth = store.add_memory(
            kind="semantic",
            content="OAuth2 tokens expire after 3600 seconds and must be refreshed using refresh_token.",
            scope="security",
        )

        # 2. Add an obsolete memory and supersede it
        m_old_db = store.add_memory(
            kind="semantic",
            content="Database host is postgresql-primary.internal port 5432.",
            scope="database",
        )
        m_new_db = store.supersede_memory(
            old_memory_id=m_old_db.id,
            new_content="Database host is aurora-cluster.internal port 5432.",
            reason="Migrated to Aurora PostgreSQL cluster",
        )

        # 3. Define benchmark cases
        cases = [
            RetrievalEvalCase(
                query="Docker multi-stage alpine",
                expected_ids=[m_docker.id],
                scope="devops",
            ),
            RetrievalEvalCase(
                query="Kubernetes read-only root",
                expected_ids=[m_k8s.id],
                scope="devops",
            ),
            RetrievalEvalCase(
                query="OAuth2 tokens expire refresh",
                expected_ids=[m_auth.id],
                scope="security",
            ),
            # Conflicting claim test: querying for database host MUST return m_new_db
            # and MUST NEVER leak m_old_db into top hits
            RetrievalEvalCase(
                query="database host aurora cluster",
                expected_ids=[m_new_db.id],
                forbidden_ids=[m_old_db.id],
                scope="database",
            ),
        ]

        summary = evaluate_retrieval(store, cases, k=3)

        assert summary.total_cases == 4
        assert summary.mean_reciprocal_rank == 1.0  # All top-1 matches
        assert summary.mean_recall_at_k == 1.0
        assert summary.total_forbidden_leakages == 0  # Zero stale/superseded leakages
        assert summary.success is True
