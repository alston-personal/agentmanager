from agent_core.cognitive_observatory import CognitiveObservatory
from agent_core.cognitive_observatory_store import CognitiveObservatoryStore
from runtime_core.cognitive_ir import KnowledgeCandidate


def snapshot(statement: str, at: str, trigger: str):
    item = KnowledgeCandidate(
        project_id="agentmanager",
        kind="observation",
        statement=statement,
        abstraction_level="working",
    )
    return CognitiveObservatory.snapshot(
        project_id="agentmanager",
        captured_at=at,
        trigger_ref=trigger,
        knowledge=(item,),
    )


def test_store_persists_snapshot_timeline_and_delta(tmp_path):
    store = CognitiveObservatoryStore(tmp_path / "cognition.sqlite3")
    first = snapshot("first", "2026-08-22T00:00:00Z", "review:0")
    second = snapshot("second", "2026-08-22T01:00:00Z", "review:1")
    store.persist_snapshot(first)
    store.persist_snapshot(second)
    delta = CognitiveObservatory.diff(first, second, annotations=("rereview",))
    store.persist_delta(delta)

    timeline = store.timeline("agentmanager")
    assert [item["snapshot_id"] for item in timeline] == [first.snapshot_id, second.snapshot_id]
    assert store.snapshot_payload(first.snapshot_id)["trigger_ref"] == "review:0"
    deltas = store.deltas("agentmanager")
    assert len(deltas) == 1
    assert deltas[0]["delta_id"] == delta.delta_id
    assert deltas[0]["payload"]["annotations"] == ["rereview"]


def test_snapshot_persistence_is_idempotent(tmp_path):
    store = CognitiveObservatoryStore(tmp_path / "cognition.sqlite3")
    item = snapshot("same", "2026-08-22T00:00:00Z", "review:0")
    assert store.persist_snapshot(item) == item.snapshot_id
    assert store.persist_snapshot(item) == item.snapshot_id
    assert len(store.timeline("agentmanager")) == 1


def test_delta_requires_persisted_lineage(tmp_path):
    store = CognitiveObservatoryStore(tmp_path / "cognition.sqlite3")
    first = snapshot("first", "2026-08-22T00:00:00Z", "review:0")
    second = snapshot("second", "2026-08-22T01:00:00Z", "review:1")
    delta = CognitiveObservatory.diff(first, second)
    try:
        store.persist_delta(delta)
    except ValueError as exc:
        assert "persisted first" in str(exc)
    else:
        raise AssertionError("delta without snapshot lineage must fail closed")
