"""Crash-window regressions for already-durable child continuations.

Only temp SQLite and a recording transport are used. These tests deliberately
do not call the external network or mutate live Oracle tasks.
"""

from pathlib import Path

from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.push_dispatch import ResilientRuntimeDispatcher
from agent_core.runtime_dispatcher import DispatchTransport, RuntimeTarget
from runtime_core.canonical_ir import CanonicalIR
from runtime_core.remote_runtime import ExecutionOutcome, RemoteRuntimeWorker


class RecordingWake(DispatchTransport):
    kind = "recording"

    def __init__(self):
        self.sent = []

    def dispatch(self, *, target, task, ir, dispatch_id):
        self.sent.append((target.target_id, task["taskId"], ir.ir_id, dispatch_id))
        return {"external_ref": f"recording:{dispatch_id}"}


def _make_parent_and_durable_child(db_path: Path):
    store = DistributedControlPlane(db_path)
    ir = CanonicalIR(
        goal="continue after crash",
        project_id="agentmanager",
        capability="parent.step",
    )
    store.submit_ir(ir)
    leased = store.lease_next_ir("parent-worker", ["parent.step"])
    assert leased is not None
    worker = RemoteRuntimeWorker("parent-worker")
    worker.register(
        "parent.step",
        lambda current: ExecutionOutcome(
            result={"ok": True}, next_capability="child.step", auto_continue=True,
        ),
    )
    committed = store.complete_ir(
        leased.task_id, worker.execute(leased.ir), lease_epoch=leased.lease_epoch,
    )
    child = committed["enqueuedTask"]
    assert child is not None and child["status"] == "submitted"
    return leased.task_id, child["taskId"]


def test_committed_child_is_woken_by_sweep_after_process_restart(tmp_path: Path):
    db_path = tmp_path / "crash-before-first-push.sqlite3"
    parent_id, child_id = _make_parent_and_durable_child(db_path)
    # Simulated process loss: the committing store is discarded without a
    # direct dispatch_task(), push notification or Executor lease.
    restarted = DistributedControlPlane(db_path)
    dispatcher = ResilientRuntimeDispatcher(restarted)
    transport = RecordingWake()
    dispatcher.register_transport(transport)
    dispatcher.register_target(RuntimeTarget(
        target_id="child-worker",
        kind="recording",
        capabilities=("child.step",),
    ))

    recovered = dispatcher.dispatch_pending()
    assert any(
        item["taskId"] == child_id and item["status"] == "dispatched"
        for item in recovered
    )
    assert len(transport.sent) == 1
    assert transport.sent[0][1] == child_id
    assert restarted.get_task(parent_id)["status"] == "succeeded"
    assert restarted.get_task(child_id)["status"] == "submitted"

    # Repeated sweeps and another dispatcher restart must not spawn an
    # immediate duplicate wake or duplicate durable continuation.
    dispatcher.dispatch_pending()
    again = ResilientRuntimeDispatcher(DistributedControlPlane(db_path))
    again.register_transport(transport)
    again.dispatch_pending()
    assert len(transport.sent) == 1
    with restarted._connect() as connection:
        child_count = connection.execute(
            "SELECT COUNT(*) FROM tasks WHERE capability='child.step'"
        ).fetchone()[0]
    assert child_count == 1

    child_lease = restarted.lease_ir_task(child_id, "child-worker")
    assert child_lease is not None
    child_worker = RemoteRuntimeWorker("child-worker")
    child_worker.register("child.step", lambda current: {"ok": True})
    completed = restarted.complete_ir(
        child_id, child_worker.execute(child_lease.ir),
        lease_epoch=child_lease.lease_epoch,
    )
    assert completed["task"]["status"] == "succeeded"
    assert again.dispatch_pending() == []
    assert len(transport.sent) == 1


def test_durable_child_with_no_matching_executor_remains_pending(tmp_path: Path):
    db_path = tmp_path / "unmatched-child.sqlite3"
    _, child_id = _make_parent_and_durable_child(db_path)
    dispatcher = ResilientRuntimeDispatcher(DistributedControlPlane(db_path))
    transport = RecordingWake()
    dispatcher.register_transport(transport)
    dispatcher.register_target(RuntimeTarget(
        target_id="unrelated-worker",
        kind="recording",
        capabilities=("other.step",),
    ))
    sweep = dispatcher.dispatch_pending()
    assert any(
        row["taskId"] == child_id and row["status"] == "no_target"
        for row in sweep
    )
    assert transport.sent == []
    assert dispatcher.store.get_task(child_id)["status"] == "submitted"

    # Once a correctly scoped target is *explicitly* registered, the normal
    # sweep recovers the saved child without re-running its parent.
    dispatcher.register_target(RuntimeTarget(
        target_id="child-worker",
        kind="recording",
        capabilities=("child.step",),
    ))
    resumed = dispatcher.dispatch_pending()
    assert any(
        row["taskId"] == child_id and row["status"] == "dispatched"
        for row in resumed
    )
    assert len(transport.sent) == 1
