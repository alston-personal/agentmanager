from pathlib import Path

import pytest

from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.distributed_gateway import DistributedGatewayService, validate_bind_security
from runtime_core.canonical_ir import CanonicalIR
from runtime_core.remote_runtime import RemoteRuntimeWorker


def test_gateway_service_submit_lease_complete(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "gateway.sqlite3")
    service = DistributedGatewayService(store)
    ir = CanonicalIR(
        goal="remote continuation",
        project_id="agentmanager",
        capability="agentos.ir.validate",
        payload={"value": 1},
    )

    submitted = service.submit({"canonical_ir": ir.to_dict()})
    task_id = submitted["task"]["taskId"]
    assert submitted["inputDigest"] == ir.digest()

    leased = service.lease({
        "node_id": "remote-worker-1",
        "capabilities": ["agentos.ir.validate"],
    })["lease"]
    assert leased is not None
    assert leased["taskId"] == task_id

    worker = RemoteRuntimeWorker("remote-worker-1")
    worker.register("agentos.ir.validate", lambda current: {"ok": True})
    result = worker.execute(CanonicalIR.from_dict(leased["canonicalIR"]))

    completed = service.complete(task_id, {"runtime_result": result.to_dict()})
    assert completed["task"]["status"] == "succeeded"
    assert completed["continuationIR"]["parent_ir_id"] == ir.ir_id


def test_active_project_resolver_uses_latest_and_hint(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "active.sqlite3")
    service = DistributedGatewayService(store)
    service.submit({
        "canonical_ir": CanonicalIR(
            goal="continue 3D layoutlib demo implementation",
            project_id="layoutlib-3d",
            capability="web.reason",
        ).to_dict()
    })
    service.submit({
        "canonical_ir": CanonicalIR(
            goal="continue AgentOS runtime work",
            project_id="agentmanager",
            capability="web.reason",
        ).to_dict()
    })

    latest = service.resolve_active_project({})
    assert latest["resolution"] == "resolved"
    assert latest["project_id"] == "agentmanager"

    hinted = service.resolve_active_project({"hint": "3D layoutlib"})
    assert hinted["resolution"] == "resolved"
    assert hinted["project_id"] == "layoutlib-3d"


def test_active_project_resolver_filters_principal_scope(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "scoped.sqlite3")
    service = DistributedGatewayService(store)
    for project_id in ("private-a", "allowed-b"):
        service.submit({
            "canonical_ir": CanonicalIR(
                goal=f"continue {project_id}",
                project_id=project_id,
                capability="web.reason",
            ).to_dict()
        })

    class ScopedPrincipal:
        def allows_project(self, project_id: str) -> bool:
            return project_id == "allowed-b"

    resolved = service.resolve_active_project({}, principal=ScopedPrincipal())
    assert resolved["project_id"] == "allowed-b"
    assert {item["project_id"] for item in resolved["candidates"]} == {"allowed-b"}


def test_non_loopback_gateway_requires_token():
    with pytest.raises(ValueError, match="TOKEN"):
        validate_bind_security("0.0.0.0", None)
    validate_bind_security("0.0.0.0", "secret")
    validate_bind_security("127.0.0.1", None)
