import json
from pathlib import Path
import subprocess
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.distributed_gateway import DistributedGatewayServer, DistributedGatewayService
from agentos_client import AgentOSClient
from agentos_node.remote_worker import build_default_worker
from runtime_core.canonical_ir import CanonicalIR


def test_attach_submit_execute_receipt(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "core.sqlite3")
    service = DistributedGatewayService(store)

    attached = service.attach({"project_id": "leopardcat-tarot", "agent": {"type": "test"}})
    assert attached["protocol"] == "agentos.core/v0.1"
    assert attached["session_id"].startswith("aos_")
    assert attached["state"]["projectId"] == "leopardcat-tarot"

    submitted = service.submit_task({
        "project_id": "leopardcat-tarot",
        "goal": "validate native AgentOS path",
        "capability": "agentos.ir.validate",
        "payload": {"probe": True},
        "session_id": attached["session_id"],
    })
    task_id = submitted["task"]["taskId"]

    lease = store.lease_next_ir("oracle-core-node", ["agentos.ir.validate"], lease_seconds=60)
    assert lease is not None and lease.task_id == task_id
    worker = build_default_worker("oracle-core-node")
    result = worker.execute(CanonicalIR.from_dict(lease.ir.to_dict()))
    store.complete_ir(task_id, result)

    receipt = service.get_receipt(task_id)
    assert receipt["protocol"] == "agentos.receipt/v0.1"
    assert receipt["terminal"] is True
    assert receipt["status"] == "succeeded"
    assert receipt["executor"] == "oracle-core-node"
    assert receipt["evidence"]["validated"] is True

    resumed = service.attach({"project_id": "leopardcat-tarot", "agent": {"type": "new-session"}})
    assert resumed["state"]["latestTask"]["taskId"] == task_id
    assert resumed["state"]["recommendedAction"] == "continue"


def test_native_project_inspect_is_registry_gated(tmp_path: Path, monkeypatch):
    repo = tmp_path / "demo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "agentos@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "AgentOS Test"], check=True)
    (repo / "README.md").write_text("native inspect\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, stdout=subprocess.DEVNULL)

    registry = tmp_path / "projects.json"
    registry.write_text(json.dumps({"demo": str(repo)}), encoding="utf-8")
    monkeypatch.setenv("AGENTOS_PROJECT_PATHS_FILE", str(registry))

    worker = build_default_worker("oracle-core-node")
    good = worker.execute(CanonicalIR(goal="inspect", project_id="demo", capability="agentos.project.inspect"))
    assert good.status == "succeeded"
    assert good.result["project_id"] == "demo"
    assert good.result["head"]
    assert good.result["dirty"] is False

    denied = worker.execute(CanonicalIR(goal="inspect", project_id="not-registered", capability="agentos.project.inspect"))
    assert denied.status == "failed"
    assert "not registered" in denied.result["message"]


def test_scoped_client_can_use_human_api_but_not_runtime_api(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "edge.sqlite3")
    server = DistributedGatewayServer(("127.0.0.1", 0), DistributedGatewayService(store), token="root-secret")
    issued = server.client_tokens.issue(
        "test:chat-client",
        label="test client",
        permissions=("project.read", "task.read", "task.submit"),
        ttl_days=1,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        client = AgentOSClient(base, token=issued["token"])
        attached = client.attach("demo", agent={"type": "external-test"})
        assert attached["project_id"] == "demo"
        submitted = client.submit_task(goal="validate edge", capability="agentos.ir.validate", payload={})
        assert submitted["task"]["status"] == "submitted"
        assert client.get_state()["projectId"] == "demo"

        request = Request(
            base + "/v1/lease",
            data=b'{"node_id":"intruder","capabilities":["agentos.ir.validate"]}',
            headers={
                "Authorization": f"Bearer {issued['token']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            urlopen(request, timeout=2)
            assert False, "scoped client must not lease runtime work"
        except HTTPError as exc:
            assert exc.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
