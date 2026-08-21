import threading
from pathlib import Path

from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.distributed_gateway import DistributedGatewayServer, DistributedGatewayService
from agentos_node.control_plane_client import ControlPlaneClient
from runtime_core.canonical_ir import CanonicalIR


def test_project_state_over_http_handles_encoded_project_id(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "project-http.sqlite3")
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
        project_id = "team/demo project"
        empty = client.get_project_state(project_id)
        assert empty["recommendedAction"] == "start"

        ir = CanonicalIR(goal="resume everywhere", project_id=project_id, capability="reason")
        task = client.submit_ir(ir)["task"]
        state = client.get_project_state(project_id)
        assert state["latestTask"]["taskId"] == task["taskId"]
        assert state["currentIR"]["ir_id"] == ir.ir_id
        assert state["recommendedAction"] == "wait"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
