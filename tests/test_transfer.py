import json

import pytest

from vault_zeta import VaultZetaStore


@pytest.fixture
def pair(tmp_path):
    with VaultZetaStore(tmp_path / "source.db") as source, VaultZetaStore(tmp_path / "target.db") as target:
        source.add_memory(memory_id="b", kind="semantic", content="Irrigation threshold is 30 percent",
                          source="policy", source_fingerprint="sha256:old", metadata={"z": [1, "ç"], "a": True})
        source.mark_source_stale("policy", current_fingerprint="sha256:new")
        source.add_memory(memory_id="a", kind="preference", content="Prefer morning irrigation", confidence=0.8)
        source.append_event(mission_id="m1", event_type="started", payload={"step": 1})
        source.append_event(mission_id="m1", event_type="paused", payload={"step": 2})
        source.save_mission("m1", status="running", snapshot={"step": 1})
        source.save_mission("m1", status="paused", snapshot={"step": 2}, expected_revision=1)
        yield source, target


def test_round_trip_preserves_all_records_and_search(pair):
    source, target = pair
    document = source.export_json()
    assert document == source.export_json()
    assert str(source.path) not in document
    assert [row["id"] for row in json.loads(document)["memories"]] == ["a", "b"]
    target.import_json(document)
    assert target.export_json() == document
    assert target.get_memory("b") == source.get_memory("b")
    assert target.events("m1") == source.events("m1")
    assert target.load_mission("m1") == source.load_mission("m1")
    assert [row.id for row in target.search("irrigation")] == ["a"]
    assert {row.id for row in target.search("irrigation", include_stale=True)} == {"a", "b"}
    assert target.append_event(mission_id="m1", event_type="resumed") > 2
    assert target.save_mission("m1", status="running", snapshot={}, expected_revision=2) == 3


def test_empty_store_round_trip(pair):
    _, target = pair
    empty = target.export_json()
    target.import_json(empty)
    assert target.export_json() == empty


@pytest.mark.parametrize("collection", ["memories", "events", "snapshots"])
def test_duplicate_ids_in_document_are_rejected_without_changes(pair, collection):
    source, target = pair
    data = json.loads(source.export_json())
    data[collection].append(data[collection][0])
    before = target.export_json()
    with pytest.raises(ValueError, match="Duplicate identifier"):
        target.import_json(json.dumps(data))
    assert target.export_json() == before
    assert target.search("irrigation", include_stale=True) == []


@pytest.mark.parametrize("collision", ["memory", "event", "snapshot"])
def test_target_collision_rolls_back_every_table_and_fts(pair, collision):
    source, target = pair
    if collision == "memory":
        target.add_memory(memory_id="b", kind="semantic", content="Keep existing memory")
    elif collision == "event":
        target.append_event(mission_id="other", event_type="existing")
    else:
        target.save_mission("m1", status="existing", snapshot={})
    before = target.export_json()
    with pytest.raises(ValueError, match="existing identifier"):
        target.import_json(source.export_json())
    assert target.export_json() == before
    assert target.search("irrigation", include_stale=True) == []


@pytest.mark.parametrize("version", [2, True, "1", None])
def test_unsupported_schema_is_rejected(pair, version):
    source, target = pair
    data = json.loads(source.export_json())
    data["schema_version"] = version
    with pytest.raises(ValueError, match="schema version"):
        target.import_json(json.dumps(data))
    assert target.search("") == []


@pytest.mark.parametrize("change", [
    lambda data: data["memories"][0].update(confidence=2),
    lambda data: data["memories"][0].update(stale="false"),
    lambda data: data["memories"][0].update(metadata=[]),
    lambda data: data["memories"][0].update(kind="unknown"),
    lambda data: data["events"][0].update(seq=0),
    lambda data: data["snapshots"][0].update(revision=True),
    lambda data: data["snapshots"][0].update(extra="unexpected"),
])
def test_malformed_record_does_not_import_partial_data(pair, change):
    source, target = pair
    data = json.loads(source.export_json())
    change(data)
    before = target.export_json()
    with pytest.raises(ValueError):
        target.import_json(json.dumps(data))
    assert target.export_json() == before


def test_rejects_duplicate_json_keys_and_nonfinite_metadata(pair):
    source, target = pair
    document = source.export_json()
    with pytest.raises(ValueError, match="Duplicate JSON"):
        target.import_json(document.replace('"schema_version":1', '"schema_version":1,"schema_version":1'))
    data = json.loads(document)
    data["memories"][0]["metadata"] = {"value": float("nan")}
    with pytest.raises(ValueError, match="Non-finite"):
        target.import_json(json.dumps(data))


def test_import_and_export_do_not_commit_callers_transaction(pair):
    source, target = pair
    target.db.execute("BEGIN")
    target.import_json(source.export_json())
    assert target.export_json() == source.export_json()
    assert target.db.in_transaction
    target.db.rollback()
    assert target.search("irrigation", include_stale=True) == []
    assert target.events("m1") == []
    assert target.load_mission("m1") is None
