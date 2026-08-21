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
        {"runtime_result": runtime_result.to_dict()},
    )

    assert completed["enqueuedTask"] is not None
    second_task_id = completed["enqueuedTask"]["taskId"]
    assert second_task_id != first_task_id
    assert completed["dispatch"]["taskId"] == second_task_id
    assert dispatcher.task_ids == [first_task_id, second_task_id]
