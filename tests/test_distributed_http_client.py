import threading
from pathlib import Path

import pytest

from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.distributed_gateway import DistributedGatewayServer, DistributedGatewayService
from agentos_node.control_plane_client import ControlPlaneClient, ControlPlaneHTTPError
from agentos_node.remote_worker import run_once
from runtime_core.canonical_ir import CanonicalIR


def test_lightweight_remote_worker_over_real_http(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "http.sqlite3")
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
        assert client.health()["status"] == "ok"

        ir = CanonicalIR(
            goal="execute without full host runtime",
            project_id="agentmanager",
            capability="agentos.ir.validate",
            payload={"source": "test"},
        )
        task_id = client.submit_ir(ir)["task"]["taskId"]

        outcome = run_once(client, "remote-http-worker")
        assert outcome["status"] == "succeeded"
        assert outcome["task_id"] == task_id
        assert client.get_task(task_id)["task"]["status"] == "succeeded"

        wrong_client = ControlPlaneClient(f"http://{host}:{port}", token="wrong-token")
        with pytest.raises(ControlPlaneHTTPError) as exc_info:
            wrong_client.get_task(task_id)
        # A supplied but invalid bearer is neither the root credential nor a
        # scoped client principal, so permission enforcement rejects it.
        assert exc_info.value.status == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_remote_http_requires_explicit_insecure_override():
    with pytest.raises(ValueError, match="HTTPS"):
        ControlPlaneClient("http://control-plane.example.test:8765")
    ControlPlaneClient("http://control-plane.example.test:8765", allow_insecure_http=True)
