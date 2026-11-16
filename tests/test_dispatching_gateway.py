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


def test_gateway_entrypoint_starts_existing_sweep_for_enabled_push_target(
    tmp_path: Path, monkeypatch,
):
    """Exercise the real gateway entrypoint, not just dispatcher methods."""
    import sys
    import threading
    from scripts import distributed_gateway as entrypoint
    from agent_core.push_dispatch import ResilientRuntimeDispatcher

    started = threading.Event()

    def observed_sweep(self, stop_event, *, interval_seconds, limit):
        assert interval_seconds == 0.01
        assert limit == 7
        assert "bridge-a" in self.targets
        assert "webhook" in self.transports
        started.set()

    class LocalOnlyServer:
        def __init__(self, address, service, token=None):
            assert isinstance(service, DispatchingGatewayService)
            assert address == ("127.0.0.1", 8765)

        def serve_forever(self):
            assert started.wait(3), "the configured gateway never started its sweep"

        def server_close(self):
            pass

    monkeypatch.setattr(ResilientRuntimeDispatcher, "run_sweep_loop", observed_sweep)
    monkeypatch.setattr(entrypoint, "DistributedGatewayServer", LocalOnlyServer)
    monkeypatch.setenv("AGENTOS_CONTROL_PLANE_DB", str(tmp_path / "gateway.sqlite3"))
    monkeypatch.setenv("AGENTOS_PROVIDER_DISPATCH_ENABLED", "true")
    monkeypatch.setenv("AGENTOS_PROVIDER_BRIDGE_ENDPOINT", "https://bridge.example.test/wake")
    monkeypatch.setenv("AGENTOS_PROVIDER_CAPABILITIES", "agent.step")
    monkeypatch.setenv("AGENTOS_CONTROL_PLANE_PUBLIC_URL", "https://one.example.test")
    monkeypatch.setenv("AGENTOS_PROVIDER_RUNTIME_ID", "bridge-a")
    monkeypatch.setenv("AGENTOS_DISPATCH_INTERVAL_SECONDS", "0.01")
    monkeypatch.setenv("AGENTOS_DISPATCH_LIMIT", "7")
    monkeypatch.delenv("AGENTOS_CONTINUITY_MIRROR_ENABLED", raising=False)
    monkeypatch.setattr(sys, "argv", ["distributed_gateway"])
    assert entrypoint.main() == 0
    assert started.is_set()
