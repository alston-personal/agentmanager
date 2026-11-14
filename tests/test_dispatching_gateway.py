from pathlib import Path

from agent_core.dispatching_gateway import DispatchingGatewayService
from agent_core.distributed_control_plane import DistributedControlPlane
from runtime_core.canonical_ir import CanonicalIR
from runtime_core.remote_runtime import ExecutionOutcome, RemoteRuntimeWorker


class FakeDispatcher:
    def __init__(self) -> None:
        self.task_ids = []

    def dispatch_task(self, task_id: str):
        self.task_ids.append(task_id)
        return {"taskId": task_id, "status": "dispatched", "targetId": "fake-push"}


def test_dispatching_gateway_wakes_initial_and_continuation_tasks(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "control-plane.sqlite3")
    dispatcher = FakeDispatcher()
    service = DispatchingGatewayService(store, dispatcher)

    ir = CanonicalIR(
        goal="automatic cross-agent continuation",
        project_id="agentmanager",
        capability="agent.step",
    )
    submitted = service.submit({"canonical_ir": ir.to_dict()})
    first_task_id = submitted["task"]["taskId"]

    assert submitted["dispatch"]["status"] == "dispatched"
    assert dispatcher.task_ids == [first_task_id]

    lease = store.lease_next_ir("runtime-a", ["agent.step"])
    assert lease is not None

    worker = RemoteRuntimeWorker("runtime-a")
    worker.register(
        "agent.step",
        lambda current: ExecutionOutcome(
            result={"step": "done"},
            next_capability="agent.step",
            auto_continue=True,
        ),
    )
    runtime_result = worker.execute(lease.ir)
    completed = service.complete(
        lease.task_id,
        {"runtime_result": runtime_result.to_dict(), "lease_epoch": lease.lease_epoch},
    )

    assert completed["enqueuedTask"] is not None
    second_task_id = completed["enqueuedTask"]["taskId"]
    assert second_task_id != first_task_id
    assert completed["dispatch"]["taskId"] == second_task_id
    assert dispatcher.task_ids == [first_task_id, second_task_id]


def test_committed_continuation_recovers_after_push_crash(tmp_path: Path):
    """A crash after parent commit must not lose the durable child on restart."""
    from agent_core.runtime_dispatcher import (
        DispatchTransport, RuntimeDispatcher, RuntimeTarget,
    )
    import pytest

    class CrashBeforeWake:
        def dispatch_task(self, task_id: str):
            raise RuntimeError("simulated process crash after sqlite commit")

    class RecordingTransport(DispatchTransport):
        kind = "webhook"

        def __init__(self) -> None:
            self.wakes = []

        def dispatch(self, *, target, task, ir, dispatch_id):
            self.wakes.append((task["taskId"], dispatch_id))
            return {"external_ref": f"test:{dispatch_id}"}

    db_path = tmp_path / "crash-recovery.sqlite3"
    store = DistributedControlPlane(db_path)
    ir = CanonicalIR(
        goal="recover child after committed parent",
        project_id="agentmanager",
        capability="agent.step",
    )
    parent = store.submit_ir(ir)
    lease = store.lease_next_ir("runtime-a", ["agent.step"])
    assert lease is not None

    worker = RemoteRuntimeWorker("runtime-a")
    worker.register(
        "agent.step",
        lambda current: ExecutionOutcome(
            result={"step": "done"},
            next_capability="agent.step",
            auto_continue=True,
        ),
    )
    result = worker.execute(lease.ir)
    gateway = DispatchingGatewayService(store, CrashBeforeWake())
    with pytest.raises(RuntimeError, match="simulated process crash"):
        gateway.complete(
            parent["taskId"],
            {"runtime_result": result.to_dict(), "lease_epoch": lease.lease_epoch},
        )

    # Simulate a fresh process: only durable SQLite state may survive.
    recovered_store = DistributedControlPlane(db_path)
    assert recovered_store.get_task(parent["taskId"])["status"] == "succeeded"
    with recovered_store._connect() as db:
        children = db.execute(
            "SELECT task_id FROM tasks WHERE status='submitted' AND task_id<>?",
            (parent["taskId"],),
        ).fetchall()
    assert len(children) == 1
    child_id = children[0]["task_id"]

    dispatcher = RuntimeDispatcher(recovered_store)
    dispatcher.register_target(RuntimeTarget(
        target_id="bridge-a",
        kind="webhook",
        capabilities=("agent.step",),
        config={"endpoint": "https://bridge.example.test/wake"},
    ))
    transport = RecordingTransport()
    dispatcher.register_transport(transport)

    # This is the existing reconciliation primitive, not a new scheduler.
    first_sweep = dispatcher.dispatch_pending()
    assert any(item["taskId"] == child_id and item["status"] == "dispatched"
               for item in first_sweep)
    assert len(transport.wakes) == 1
    assert transport.wakes[0][0] == child_id

    # Repeated startup/sweep does not duplicate wake before stale timeout.
    again = RuntimeDispatcher(DistributedControlPlane(db_path))
    again.register_transport(transport)
    repeat = again.dispatch_pending()
    assert any(item["taskId"] == child_id and item["status"] == "already_dispatched"
               for item in repeat)
    assert len(transport.wakes) == 1

    claimed = recovered_store.lease_ir_task(child_id, "bridge-a")
    assert claimed is not None
    assert claimed.lease_epoch == 1
    assert again.dispatch_pending() == []

    with recovered_store._connect() as db:
        assert db.execute(
            "SELECT COUNT(*) FROM tasks WHERE task_id<>?", (parent["taskId"],)
        ).fetchone()[0] == 1
