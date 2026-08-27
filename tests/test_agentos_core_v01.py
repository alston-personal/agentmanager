from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from agent_core.context_compiler import compile_execution_context
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
    assert attached["execution_context"]["schema"] == "agentos.execution-context/v0.1"
    assert attached["execution_context"]["context_freshness"]["status"] == "unknown"
    submitted = service.submit_task({"project_id": "leopardcat-tarot", "goal": "validate native AgentOS path", "capability": "agentos.ir.validate", "payload": {"probe": True}, "session_id": attached["session_id"]})
    task_id = submitted["task"]["taskId"]
    lease = store.lease_next_ir("oracle-core-node", ["agentos.ir.validate"], lease_seconds=60)
    assert lease is not None and lease.task_id == task_id
    worker = build_default_worker("oracle-core-node")
    result = worker.execute(CanonicalIR.from_dict(lease.ir.to_dict()))
    store.complete_ir(task_id, result)
    receipt = service.get_receipt(task_id)
    assert receipt["protocol"] == "agentos.receipt/v0.1"
    assert receipt["terminal"] is True and receipt["status"] == "succeeded"
    assert receipt["executor"] == "oracle-core-node"
    assert receipt["evidence"]["validated"] is True
    resumed = service.attach({"project_id": "leopardcat-tarot", "agent": {"type": "new-session"}})
    assert resumed["state"]["latestTask"]["taskId"] == task_id
    assert resumed["state"]["recommendedAction"] == "continue"
    assert resumed["execution_context"]["latest_task"]["taskId"] == task_id
    assert resumed["execution_context"]["recommended_action"] == "continue"


def test_attach_compiles_goal_findings_actions_and_write_policy(tmp_path: Path, monkeypatch):
    context_doc = tmp_path / "development-context.json"
    context_doc.write_text(json.dumps({"updated_at": "2026-08-27T10:00:00+08:00", "integration_branch": "feature/context-proof", "write_policy": {"branch_required_for_writes": True}, "active_work": {"goal": "Prove a fresh agent can resume without conversation history.", "integration_branch": "feature/context-proof", "current_findings": ["Native Oracle execution is proven.", "Scoped external edge is proven."], "next_actions": ["Run the blind fresh-session attach proof.", "Then add native project test capability."]}}), encoding="utf-8")
    registry = tmp_path / "contexts.json"
    registry.write_text(json.dumps({"demo": str(context_doc)}), encoding="utf-8")
    monkeypatch.setenv("AGENTOS_PROJECT_CONTEXTS_FILE", str(registry))
    context = compile_execution_context(
        "demo",
        {"recommendedAction": "start"},
        agent={"type": "blind-fresh-session", "model": "weak-executor"},
        now=datetime(2026, 8, 27, 2, 30, tzinfo=timezone.utc),
    )
    assert context["schema"] == "agentos.execution-context/v0.1"
    assert context["active_goal"] == "Prove a fresh agent can resume without conversation history."
    assert context["next_action"] == "Run the blind fresh-session attach proof."
    assert context["current_findings"] == ["Native Oracle execution is proven.", "Scoped external edge is proven."]
    assert context["integration_branch"] == "feature/context-proof"
    assert context["write_policy"]["branch_required_for_writes"] is True
    assert context["agent"]["type"] == "blind-fresh-session"
    assert context["context_freshness"]["status"] == "fresh"
    assert context["context_freshness"]["age_seconds"] == 1800


def test_execution_context_marks_stale_source_without_blocking_it(tmp_path: Path, monkeypatch):
    context_doc = tmp_path / "stale-context.json"
    context_doc.write_text(json.dumps({
        "updated_at": "2026-08-20T00:00:00Z",
        "active_work": {"goal": "Old but still visible goal", "next_actions": ["Reconcile before acting"]},
    }), encoding="utf-8")
    registry = tmp_path / "contexts.json"
    registry.write_text(json.dumps({"stale-demo": str(context_doc)}), encoding="utf-8")
    monkeypatch.setenv("AGENTOS_PROJECT_CONTEXTS_FILE", str(registry))
    monkeypatch.setenv("AGENTOS_CONTEXT_MAX_AGE_SECONDS", "86400")
    context = compile_execution_context(
        "stale-demo",
        {"recommendedAction": "start"},
        now=datetime(2026, 8, 27, 0, 0, tzinfo=timezone.utc),
    )
    freshness = context["context_freshness"]
    assert context["active_goal"] == "Old but still visible goal"
    assert freshness["status"] == "stale"
    assert freshness["age_seconds"] == 7 * 24 * 60 * 60
    assert freshness["max_age_seconds"] == 86400


def _make_git_repo(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init", str(path)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "agentos@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "AgentOS Test"], check=True)
    (path / "README.md").write_text("native inspect\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "init"], check=True, stdout=subprocess.DEVNULL)


def test_native_project_inspect_is_registry_gated(tmp_path: Path, monkeypatch):
    repo = tmp_path / "demo"
    _make_git_repo(repo)
    registry = tmp_path / "projects.json"
    registry.write_text(json.dumps({"demo": str(repo)}), encoding="utf-8")
    monkeypatch.setenv("AGENTOS_PROJECT_PATHS_FILE", str(registry))
    worker = build_default_worker("oracle-core-node")
    good = worker.execute(CanonicalIR(goal="inspect", project_id="demo", capability="agentos.project.inspect"))
    assert good.status == "succeeded" and good.result["project_id"] == "demo"
    assert good.result["head"] and good.result["dirty"] is False
    denied = worker.execute(CanonicalIR(goal="inspect", project_id="not-registered", capability="agentos.project.inspect"))
    assert denied.status == "failed" and "not registered" in denied.result["message"]


def test_native_project_test_uses_only_registered_profile(tmp_path: Path, monkeypatch):
    repo = tmp_path / "demo"
    _make_git_repo(repo)
    projects = tmp_path / "projects.json"
    projects.write_text(json.dumps({"demo": str(repo)}), encoding="utf-8")
    profiles = tmp_path / "tests.json"
    profiles.write_text(json.dumps({"demo": {"smoke": {"argv": ["python3", "-c", "print('native-profile-ok')"], "timeout_seconds": 10}}}), encoding="utf-8")
    monkeypatch.setenv("AGENTOS_PROJECT_PATHS_FILE", str(projects))
    monkeypatch.setenv("AGENTOS_PROJECT_TESTS_FILE", str(profiles))
    worker = build_default_worker("oracle-core-node")
    good = worker.execute(CanonicalIR(goal="test", project_id="demo", capability="agentos.project.test", payload={"profile": "smoke", "argv": ["false"], "command": "false"}))
    assert good.status == "succeeded"
    assert good.result["profile"] == "smoke" and good.result["passed"] is True
    assert "native-profile-ok" in good.result["stdout"]
    denied = worker.execute(CanonicalIR(goal="test", project_id="demo", capability="agentos.project.test", payload={"profile": "not-registered"}))
    assert denied.status == "failed" and "not registered" in denied.result["message"]


def test_scoped_client_enforces_permission_project_capability_and_task_isolation(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "edge.sqlite3")
    service = DistributedGatewayService(store)
    foreign = service.submit_task({"project_id": "other-project", "goal": "foreign task", "capability": "agentos.ir.validate", "payload": {}})["task"]
    server = DistributedGatewayServer(("127.0.0.1", 0), service, token="root-secret")
    issued = server.client_tokens.issue("test:chat-client", label="test client", permissions=("project.read", "task.read", "task.submit"), projects=("demo",), capabilities=("agentos.ir.validate",), ttl_days=1)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        client = AgentOSClient(base, token=issued["token"])
        attached = client.attach("demo", agent={"type": "external-test"})
        assert attached["project_id"] == "demo" and attached["execution_context"]["project_id"] == "demo"
        submitted = client.submit_task(goal="validate edge", capability="agentos.ir.validate", payload={})
        assert submitted["task"]["status"] == "submitted" and client.get_state()["projectId"] == "demo"
        with pytest.raises(RuntimeError, match="HTTP 403"): client.attach("other-project")
        with pytest.raises(RuntimeError, match="HTTP 403"): client.submit_task(project_id="demo", goal="forbidden capability", capability="agentos.project.inspect", payload={})
        with pytest.raises(RuntimeError, match="HTTP 403"): client.get_task(foreign["taskId"])
        request = Request(base + "/v1/lease", data=b'{"node_id":"intruder","capabilities":["agentos.ir.validate"]}', headers={"Authorization": f"Bearer {issued['token']}", "Content-Type": "application/json"}, method="POST")
        try:
            urlopen(request, timeout=2)
            assert False, "scoped client must not lease runtime work"
        except HTTPError as exc:
            assert exc.code == 403
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
