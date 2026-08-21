from pathlib import Path

from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.project_state import read_project_state
from runtime_core.canonical_ir import CanonicalIR
from runtime_core.remote_runtime import RemoteRuntimeWorker


def test_project_state_starts_empty_then_tracks_active_ir(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "state.sqlite3")
    empty = read_project_state(store, "demo")
    assert empty["recommendedAction"] == "start"
    assert empty["currentIR"] is None

    ir = CanonicalIR(goal="shared IDE state", project_id="demo", capability="reason")
    task = store.submit_ir(ir)
    state = read_project_state(store, "demo")
    assert state["latestTask"]["taskId"] == task["taskId"]
    assert state["recommendedAction"] == "wait"
    assert state["currentSource"] == "task_input"
    assert state["currentIR"]["ir_id"] == ir.ir_id


def test_project_state_exposes_trusted_continuation(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "continuation.sqlite3")
    ir = CanonicalIR(goal="continue elsewhere", project_id="demo", capability="reason")
    task = store.submit_ir(ir)
    lease = store.lease_next_ir("worker", ["reason"])
    assert lease is not None

    worker = RemoteRuntimeWorker("worker")
    worker.register("reason", lambda _: {"answer": 42})
    result = worker.execute(lease.ir)
    store.complete_ir(task["taskId"], result, enqueue_continuation=False)

    state = read_project_state(store, "demo")
    assert state["latestTask"]["status"] == "succeeded"
    assert state["recommendedAction"] == "continue"
    assert state["currentSource"] == "task_continuation"
    assert state["currentIR"]["parent_ir_id"] == ir.ir_id


def test_project_state_skips_newer_generic_tasks(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "mixed.sqlite3")
    ir = CanonicalIR(goal="distributed state", project_id="demo", capability="reason")
    distributed = store.submit_ir(ir)
    store.submit_task(
        capability="legacy.task",
        payload={"legacy": True},
        idempotency_key="legacy-demo-task",
        project_id="demo",
    )

    state = read_project_state(store, "demo")
    assert state["latestTask"]["taskId"] == distributed["taskId"]
    assert state["currentIR"]["ir_id"] == ir.ir_id
    assert state["ignoredNonDistributedTasks"] == 1
