from __future__ import annotations

from pathlib import Path

import pytest

from agent_core.controller_service import ControllerService
from agent_core.executor_job_contract import canonical_experience_regression_request
from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore


class FakeDispatcher:
    def __init__(self):
        self.calls = []

    def submit(self, *, node_id, request):
        self.calls.append((node_id, dict(request)))
        return {
            "schema": "agentos.executor-job-submission/v1",
            "ok": True,
            "state": "queued",
            "job_id": "action-12345678",
            "node_id": node_id,
            "job_type": request["job_type"],
            "project_id": request["project_id"],
            "executor_class": request["executor_class"],
            "capability": "agentos.experience.regression",
            "reused": False,
            "credential_exposed": False,
        }


def _fabric(tmp_path: Path) -> RealmFabricStore:
    registry = NodeRegistry(tmp_path / "nodes.json")
    fabric = RealmFabricStore(tmp_path / "fabric.json", node_registry=registry)
    fabric.initialize_realm("realm-test")
    manifest = {
        "schema": "agentos.node-manifest/v0.1",
        "realm_id": "realm-test",
        "node_id": "oracle-core-node",
        "role": "core",
        "hostname": "oracle",
        "platform": "Linux",
        "platform_release": "test",
        "capabilities": ["agentos.experience.regression"],
        "tool_presence": {},
        "surface_inventory": {"surfaces": []},
    }
    registry.record_heartbeat({
        "schema": "agentos.node-heartbeat/v0.1",
        "realm_id": "realm-test",
        "node_id": "oracle-core-node",
        "role": "core",
        "status": "online",
        "observed_at": "2099-01-01T00:00:00Z",
        "uptime_seconds": 1,
        "surface_count": 0,
        "manifest": manifest,
    })
    return fabric


def test_executor_job_routes_to_local_dispatcher_not_thin_client_queue(tmp_path: Path) -> None:
    fabric = _fabric(tmp_path)
    dispatcher = FakeDispatcher()
    controller = ControllerService(fabric, executor_job_dispatcher=dispatcher)
    job = canonical_experience_regression_request()

    result = controller.dispatch({
        "schema": "agentos.controller-dispatch/v0.1",
        "node_id": "oracle-core-node",
        "action": "agentos.executor.job",
        "payload": job,
    })

    assert result["schema"] == "agentos.executor-job-submission/v1"
    assert result["job_id"] == "action-12345678"
    assert dispatcher.calls == [("oracle-core-node", job)]
    assert fabric.load()["tasks"].get("oracle-core-node", []) == []


def test_executor_job_requires_registered_semantic_capability(tmp_path: Path) -> None:
    fabric = _fabric(tmp_path)
    state = registry_state = fabric.node_registry.load()
    # Replace the advertised heartbeat with no executor-job capability.
    node = registry_state["nodes"]["oracle-core-node"]
    node["manifest"]["capabilities"] = []
    node["capabilities"] = []
    fabric.node_registry.path.write_text(__import__("json").dumps(state), encoding="utf-8")

    controller = ControllerService(fabric, executor_job_dispatcher=FakeDispatcher())
    with pytest.raises(ValueError, match="does not advertise capability"):
        controller.dispatch({
            "node_id": "oracle-core-node",
            "action": "agentos.executor.job",
            "payload": canonical_experience_regression_request(),
        })


def test_executor_job_rejects_legacy_passthrough_and_caller_task_id(tmp_path: Path) -> None:
    fabric = _fabric(tmp_path)
    controller = ControllerService(fabric, executor_job_dispatcher=FakeDispatcher())
    base = {
        "node_id": "oracle-core-node",
        "action": "agentos.executor.job",
        "payload": canonical_experience_regression_request(),
    }
    with pytest.raises(ValueError, match="unexpected executor-job controller fields"):
        controller.dispatch({**base, "provider": "anything"})
    with pytest.raises(ValueError, match="relay-owned"):
        controller.dispatch({**base, "task_id": "caller-selected"})
    assert fabric.load()["tasks"].get("oracle-core-node", []) == []
