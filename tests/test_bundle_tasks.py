from vault_zeta import VaultZetaStore


def test_bundle_exports_and_imports_task_graphs(tmp_path):
    db1 = tmp_path / "src_tasks.db"
    bundle_dir = tmp_path / "bundle_tasks_out"
    db2 = tmp_path / "dst_tasks.db"

    with VaultZetaStore(db1) as s1:
        s1.create_task(
            mission_id="m_pipeline",
            task_id="extract",
            title="Extract Raw Data",
            payload={"source": "s3"},
        )
        s1.create_task(
            mission_id="m_pipeline",
            task_id="transform",
            title="Transform Clean Features",
            dependencies=["extract"],
        )
        s1.update_task(mission_id="m_pipeline", task_id="extract", status="completed")

        s1.export_bundle(bundle_dir)

    with VaultZetaStore(db2) as s2:
        report = s2.import_bundle(bundle_dir)
        assert report["tasks_added"] == 2
        assert report["task_deps_added"] == 1

        t_ext = s2.get_task("m_pipeline", "extract")
        t_trans = s2.get_task("m_pipeline", "transform")

        assert t_ext.status == "completed"
        assert t_trans.dependencies == ["extract"]
