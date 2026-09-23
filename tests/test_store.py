import pytest

from vault_zeta import RevisionConflict, VaultZetaStore


@pytest.fixture
def store(tmp_path):
    with VaultZetaStore(tmp_path / "zeta.db") as zeta:
        yield zeta


def test_memory_search_respects_scope_and_kind(store):
    store.add_memory(
        kind="semantic",
        content="Greenhouse irrigation uses soil moisture targets",
        scope="canopy",
        confidence=0.9,
    )
    store.add_memory(
        kind="failure",
        content="Irrigation command timed out on zone seven",
        scope="canopy",
        confidence=0.8,
    )
    store.add_memory(
        kind="semantic",
        content="Invoice reconciliation uses bank statement references",
        scope="finance",
    )

    hits = store.search("irrigation", scope="canopy", kinds=["semantic"])

    assert len(hits) == 1
    assert hits[0].scope == "canopy"
    assert hits[0].kind == "semantic"


def test_source_change_marks_old_memory_stale(store):
    memory = store.add_memory(
        kind="semantic",
        content="Threshold is 30 percent",
        source="policy.md",
        source_fingerprint="sha256:old",
    )

    changed = store.mark_source_stale("policy.md", current_fingerprint="sha256:new")

    assert changed == 1
    assert store.get_memory(memory.id).stale is True
    assert store.search("threshold") == []
    assert len(store.search("threshold", include_stale=True)) == 1


def test_event_journal_is_append_only_and_ordered(store):
    first = store.append_event(
        mission_id="m1",
        event_type="observation",
        payload={"value": 1},
    )
    second = store.append_event(
        mission_id="m1",
        event_type="correction",
        payload={"value": 2},
    )

    events = store.events("m1")

    assert second > first
    assert [event.event_type for event in events] == ["observation", "correction"]
    assert store.events("m1", after_seq=first)[0].seq == second


def test_mission_snapshots_use_optimistic_revisions(store):
    revision = store.save_mission(
        "m1",
        status="running",
        snapshot={"step": 1},
    )

    assert revision == 1

    revision = store.save_mission(
        "m1",
        status="paused",
        snapshot={"step": 2},
        expected_revision=1,
    )

    assert revision == 2
    mission = store.load_mission("m1")
    assert mission is not None
    assert mission.status == "paused"
    assert mission.snapshot == {"step": 2}

    with pytest.raises(RevisionConflict):
        store.save_mission(
            "m1",
            status="running",
            snapshot={"step": 3},
            expected_revision=1,
        )


def test_invalid_memory_kind_is_rejected(store):
    with pytest.raises(ValueError):
        store.add_memory(kind="telepathy", content="Nope")
