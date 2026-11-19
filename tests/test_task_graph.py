import pytest

from vault_zeta import VaultZetaStore


def test_task_graph_creation_and_dependencies(tmp_path):
    with VaultZetaStore(tmp_path / "tasks.db") as store:
        # Create Task 1 (no dependencies) -> starts pending
        t1 = store.create_task(
            mission_id="m100",
            task_id="setup_env",
            title="Setup Python Environment",
            payload={"python": "3.12"},
        )
        assert t1.status == "pending"
        assert t1.dependencies == []

        # Create Task 2 depending on Task 1 -> starts blocked
        t2 = store.create_task(
            mission_id="m100",
            task_id="run_migrations",
            title="Run Database Migrations",
            dependencies=["setup_env"],
        )
        assert t2.status == "blocked"
        assert t2.dependencies == ["setup_env"]

        # Ready tasks should only be t1
        ready = store.get_ready_tasks("m100")
        assert len(ready) == 1
        assert ready[0].task_id == "setup_env"


def test_task_graph_cycle_detection(tmp_path):
    with VaultZetaStore(tmp_path / "cycle.db") as store:
        store.create_task(mission_id="m1", task_id="A", title="Task A")
        store.create_task(mission_id="m1", task_id="B", title="Task B", dependencies=["A"])
        store.create_task(mission_id="m1", task_id="C", title="Task C", dependencies=["B"])

        # Self-dependency must fail
        with pytest.raises(ValueError, match="Self-dependency"):
            store.create_task(mission_id="m1", task_id="D", title="Task D", dependencies=["D"])

        # Adding A depending on C (forming A -> B -> C -> A cycle) must fail
        with pytest.raises(ValueError, match="Cycle detected"):
            store.create_task(mission_id="m1", task_id="CycleCloser", title="Task", dependencies=["C"])
            # Or creating a new node that causes a loop
            store._check_task_cycle("m1", "A", ["C"])


def test_cascade_unblocking_on_task_completion(tmp_path):
    with VaultZetaStore(tmp_path / "unblock.db") as store:
        # Pipeline: Step 1 -> Step 2 -> Step 3
        store.create_task(mission_id="pipe", task_id="step1", title="Step 1")
        store.create_task(mission_id="pipe", task_id="step2", title="Step 2", dependencies=["step1"])
        store.create_task(mission_id="pipe", task_id="step3", title="Step 3", dependencies=["step2"])

        assert store.get_task("pipe", "step1").status == "pending"
        assert store.get_task("pipe", "step2").status == "blocked"
        assert store.get_task("pipe", "step3").status == "blocked"

        # Complete Step 1
        store.update_task(mission_id="pipe", task_id="step1", status="completed", result={"output": "ok"})

        # Step 2 must be automatically unblocked to pending, Step 3 still blocked
        assert store.get_task("pipe", "step1").status == "completed"
        assert store.get_task("pipe", "step2").status == "pending"
        assert store.get_task("pipe", "step3").status == "blocked"

        # Complete Step 2
        store.update_task(mission_id="pipe", task_id="step2", status="completed")

        # Step 3 must now be unblocked to pending
        assert store.get_task("pipe", "step3").status == "pending"
