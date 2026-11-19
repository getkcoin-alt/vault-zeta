from vault_zeta import VaultZetaStore


def test_crash_recovery_resets_interrupted_tasks(tmp_path):
    db_file = tmp_path / "recovery.db"

    # Session 1: Start tasks, but crash while task2 is running
    with VaultZetaStore(db_file) as store:
        store.save_mission("mission_reboot", status="running", snapshot={"phase": "execution"})
        store.create_task(mission_id="mission_reboot", task_id="t1", title="Task 1")
        store.create_task(mission_id="mission_reboot", task_id="t2", title="Task 2", dependencies=["t1"])

        store.update_task(mission_id="mission_reboot", task_id="t1", status="completed")
        # t2 is unblocked to pending, then starts running
        store.update_task(mission_id="mission_reboot", task_id="t2", status="running")
        # Simulation of process crash: connection closes with t2 in 'running' state

    # Session 2: Fresh process start and recovery
    with VaultZetaStore(db_file) as store2:
        plan = store2.recover_mission("mission_reboot", reset_running=True)

        assert plan.mission_id == "mission_reboot"
        assert plan.status == "running"
        assert plan.completed_task_ids == ["t1"]
        # t2 was interrupted and recovered back to ready/pending
        assert "t2" in plan.in_progress_recovered_task_ids
        assert "t2" in plan.ready_task_ids
        assert store2.get_task("mission_reboot", "t2").status == "pending"


def test_event_idempotency_key_deduplication(tmp_path):
    with VaultZetaStore(tmp_path / "idempotent.db") as store:
        seq1 = store.append_event(
            mission_id="m99",
            event_type="deploy_step",
            payload={"step": "provision"},
            idempotency_key="tx-step-1-uuid",
        )

        # Append identical event with same idempotency key
        seq2 = store.append_event(
            mission_id="m99",
            event_type="deploy_step",
            payload={"step": "provision"},
            idempotency_key="tx-step-1-uuid",
        )

        # Must return same sequence number and not duplicate
        assert seq1 == seq2
        assert len(store.events("m99")) == 1


def test_event_replay_verifies_deterministic_consistency(tmp_path):
    with VaultZetaStore(tmp_path / "replay.db") as store:
        store.create_task(mission_id="rep", task_id="build", title="Build binary")
        store.create_task(mission_id="rep", task_id="test", title="Run tests", dependencies=["build"])

        store.update_task(mission_id="rep", task_id="build", status="running")
        store.update_task(mission_id="rep", task_id="build", status="completed")
        store.update_task(mission_id="rep", task_id="test", status="running")
        store.update_task(mission_id="rep", task_id="test", status="completed")

        report = store.replay_events("rep")
        assert report["events_replayed"] >= 4
        assert report["is_consistent"] is True
        assert report["reconstructed_task_statuses"] == {"build": "completed", "test": "completed"}


def test_mission_compaction(tmp_path):
    with VaultZetaStore(tmp_path / "compact.db") as store:
        store.save_mission("m_comp", status="running", snapshot={"ver": 1})
        store.append_event(mission_id="m_comp", event_type="heartbeat", payload={"beat": 1})

        res = store.compact_mission("m_comp")
        assert res["events_preserved"] >= 1
        assert res["snapshots_active"] == 1
