from pathlib import Path

import pytest

from agent_core.state_kernel import StateKernelConflict, StateKernelStore
from runtime_core.state_v2 import ProjectState, StateDelta, StateOperation


def delta(state: ProjectState, *operations: StateOperation, work_id: str | None = None) -> StateDelta:
    return StateDelta(
        project_id=state.project_id,
        base_state_id=state.state_id,
        operations=tuple(operations),
        work_id=work_id,
    )


def test_project_state_content_hash_detects_tampering():
    state = ProjectState(project_id="agentmanager", goal="Build shared state")
    payload = state.to_dict()
    assert payload["state_id"].startswith("state_")

    payload["goal"] = "Tampered"
    with pytest.raises(ValueError, match="content hash mismatch"):
        ProjectState.from_dict(payload)


def test_initialize_and_fast_forward_commit(tmp_path: Path):
    store = StateKernelStore(tmp_path / "kernel.sqlite3")
    initial = ProjectState(project_id="agentmanager", goal="Build shared state")
    head = store.initialize_project(initial, author_principal="github:alstonhuang")

    assert head["revision"] == 1
    assert head["headStateId"] == initial.state_id

    update = delta(initial, StateOperation("set", ("metadata", "phase"), "kernel-v2"), work_id="work_a")
    committed = store.commit_delta(
        update,
        author_principal="runtime:test",
        source_work_ids=["work_a"],
    )

    assert committed["revision"] == 2
    assert committed["state"]["metadata"]["phase"] == "kernel-v2"
    assert committed["commit"]["baseStateId"] == initial.state_id
    assert committed["commit"]["sourceWorkIds"] == ["work_a"]
    assert committed["commit"]["validationReceipt"]["mergedFromStaleBase"] is False


def test_stale_disjoint_delta_auto_merges_onto_current_head(tmp_path: Path):
    store = StateKernelStore(tmp_path / "kernel.sqlite3")
    initial = ProjectState(project_id="agentmanager", goal="Build shared state")
    store.initialize_project(initial, author_principal="system")

    agent_a = delta(initial, StateOperation("set", ("metadata", "agent_a"), "done"), work_id="work_a")
    agent_b = delta(initial, StateOperation("set", ("metadata", "agent_b"), "done"), work_id="work_b")

    store.commit_delta(agent_a, author_principal="runtime:a", source_work_ids=["work_a"])
    merged = store.commit_delta(agent_b, author_principal="runtime:b", source_work_ids=["work_b"])

    assert merged["revision"] == 3
    assert merged["state"]["metadata"] == {"agent_a": "done", "agent_b": "done"}
    assert merged["commit"]["validationReceipt"]["mergedFromStaleBase"] is True
    assert merged["commit"]["validationReceipt"]["baseStateId"] == initial.state_id


def test_stale_conflicting_delta_is_rejected_without_moving_head(tmp_path: Path):
    store = StateKernelStore(tmp_path / "kernel.sqlite3")
    initial = ProjectState(project_id="agentmanager", goal="Original goal")
    store.initialize_project(initial, author_principal="system")

    first = delta(initial, StateOperation("set", ("goal",), "Goal from A"))
    second = delta(initial, StateOperation("set", ("goal",), "Goal from B"))

    committed = store.commit_delta(first, author_principal="runtime:a")
    head_before = committed["headStateId"]

    with pytest.raises(StateKernelConflict) as exc:
        store.commit_delta(second, author_principal="runtime:b")

    assert exc.value.paths == (("goal",),)
    assert store.head("agentmanager")["headStateId"] == head_before
    assert store.head("agentmanager")["state"]["goal"] == "Goal from A"


def test_concurrent_add_unique_to_reference_list_is_commutative(tmp_path: Path):
    store = StateKernelStore(tmp_path / "kernel.sqlite3")
    initial = ProjectState(project_id="agentmanager", goal="Track decisions")
    store.initialize_project(initial, author_principal="system")

    first = delta(initial, StateOperation("add_unique", ("decision_refs",), "decision:a"))
    second = delta(initial, StateOperation("add_unique", ("decision_refs",), "decision:b"))

    store.commit_delta(first, author_principal="runtime:a")
    merged = store.commit_delta(second, author_principal="runtime:b")

    assert merged["state"]["decision_refs"] == ["decision:a", "decision:b"]
    assert merged["commit"]["validationReceipt"]["mergedFromStaleBase"] is True


def test_work_items_can_merge_by_work_id(tmp_path: Path):
    store = StateKernelStore(tmp_path / "kernel.sqlite3")
    initial = ProjectState(project_id="agentmanager", goal="Parallel work")
    store.initialize_project(initial, author_principal="system")

    first = delta(
        initial,
        StateOperation(
            "set",
            ("work_items", "work_a"),
            {"status": "succeeded", "capability": "code.implement"},
        ),
    )
    second = delta(
        initial,
        StateOperation(
            "set",
            ("work_items", "work_b"),
            {"status": "ready", "capability": "code.review"},
        ),
    )

    store.commit_delta(first, author_principal="runtime:a")
    merged = store.commit_delta(second, author_principal="runtime:b")

    assert set(merged["state"]["work_items"]) == {"work_a", "work_b"}
