import threading
from pathlib import Path

from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.distributed_gateway import DistributedGatewayServer, DistributedGatewayService
from agent_core.runtime_dispatcher import RuntimeDispatcher, RuntimeTarget
from agentos_node.control_plane_client import ControlPlaneClient
from runtime_core.canonical_ir import CanonicalIR


def _ir(step: int) -> CanonicalIR:
    return CanonicalIR(
        goal="exact push lease",
        project_id="agentmanager",
        capability="agentos.ir.validate",
        payload={"step": step},
    )


def test_exact_lease_does_not_steal_another_targeted_task(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "exact.sqlite3")
    first = store.submit_ir(_ir(1), target_node_id="push-runtime")
    second = store.submit_ir(_ir(2), target_node_id="push-runtime")

    lease = store.lease_ir_task(second["taskId"], "push-runtime", lease_seconds=60)
    assert lease is not None
    assert lease.task_id == second["taskId"]
    assert lease.ir.payload["step"] == 2
    assert store.get_task(first["taskId"])["status"] == "submitted"
    assert store.lease_ir_task(second["taskId"], "push-runtime") is None


def test_expired_exact_lease_preserves_registered_push_target(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "expiry.sqlite3")
    dispatcher = RuntimeDispatcher(store)
    dispatcher.register_target(
        RuntimeTarget(
            target_id="provider-bridge",
            kind="webhook",
            capabilities=("agentos.ir.validate",),
            config={"endpoint": "https://bridge.example.test/v1/runtime-dispatch"},
        )
    )
    task = store.submit_ir(_ir(1), target_node_id="provider-bridge")
    lease = store.lease_ir_task(task["taskId"], "provider-bridge", lease_seconds=60)
    assert lease is not None

    with store._connect() as connection:
        connection.execute(
            "UPDATE tasks SET lease_until='2000-01-01T00:00:00Z' WHERE task_id=?",
            (task["taskId"],),
        )
    assert store.requeue_expired_ir_leases() == 1
    requeued = store.get_task(task["taskId"])
    assert requeued["status"] == "submitted"
    assert requeued["targetNodeId"] == "provider-bridge"


def test_exact_lease_over_http(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "http-exact.sqlite3")
    server = DistributedGatewayServer(
        ("127.0.0.1", 0),
        DistributedGatewayService(store),
        token="test-token",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        client = ControlPlaneClient(f"http://{host}:{port}", token="test-token")
        first = client.submit_ir(_ir(1), target_node_id="github-actions-worker")["task"]
        second = client.submit_ir(_ir(2), target_node_id="github-actions-worker")["task"]

        lease = client.lease_task(second["taskId"], "github-actions-worker")
        assert lease is not None
        assert lease["taskId"] == second["taskId"]
        assert lease["canonicalIR"]["payload"]["step"] == 2
        assert client.get_task(first["taskId"])["task"]["status"] == "submitted"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
