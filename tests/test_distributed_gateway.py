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

    completed = service.complete(task_id, {"runtime_result": result.to_dict(), "lease_epoch": leased["leaseEpoch"]})
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


def test_ir_advance_endpoint_enforces_permission_and_generation_fence(tmp_path: Path, monkeypatch):
    import json
    from threading import Thread
    from agent_core.active_continuation import activate_continuation, resolve_active_continuation
    from agent_core.client_auth import ClientTokenStore
    from agent_core.distributed_gateway import DistributedGatewayServer
    from agentos_node.control_plane_client import ControlPlaneClient, ControlPlaneHTTPError

    data_root = tmp_path / "agent-data"
    proj_dir = data_root / "projects" / "agentos-core"
    (proj_dir / "continuity").mkdir(parents=True)
    gov_dir = data_root / "governance"
    gov_dir.mkdir(parents=True)
    (gov_dir / "directory.json").write_text(json.dumps({
        "entities": {
            "project://agentos-core": {
                "id": "project://agentos-core",
                "kind": "project",
                "state": "verified",
                "canonical_id": "agentos-core",
                "name": "AgentOS Core",
                "aliases": ["AgentOS", "AgentOS Core"],
                "implementation": {
                    "source": {
                        "repo": "alston-personal/agentmanager",
                        "branch": "main",
                        "canonical_path": str(tmp_path / "agentmanager"),
                        "node": "oracle-core-node",
                    }
                },
                "metadata": {
                    "state": {
                        "continuity": str(proj_dir / "continuity" / "latest.json"),
                    }
                },
            }
        }
    }), encoding="utf-8")

    init_index = "idx-core-20261116T000000Z-init"
    init_ir = "ir_20261116T000000Z_init"
    (proj_dir / "execution-head.json").write_text(json.dumps({
        "schema": "agentos.execution-head/v1",
        "index_id": init_index,
        "active_goal": "Test goal",
        "execution_head": {"status": "in_progress"},
        "updated_at": "2026-11-16T00:00:00Z",
    }), encoding="utf-8")
    (proj_dir / "continuity" / "latest.json").write_text(json.dumps({
        "index_id": init_index,
        "protocol": "ANCP/1.0",
        "published_at": "2026-11-16T00:00:00Z",
        "recommended_action": "Initial step",
        "canonical_ir": {
            "schema_version": "agentos.ir/v1",
            "index_id": init_index,
            "ir_id": init_ir,
            "parent_ir_id": None,
            "goal": "Test goal",
            "constraints": [],
            "decisions": [],
            "pending_tasks": ["Initial step"],
            "evidence": [],
            "continuation": {"next_action": "Initial step", "recommended_action": "Initial step"},
            "capability": "agentos.project.test",
        },
    }), encoding="utf-8")
    activate_continuation(
        "agentos-core",
        index_id=init_index,
        ir_id=init_ir,
        reason="test init",
        data_root=data_root,
    )
    monkeypatch.setenv("AGENT_DATA_ROOT", str(data_root))

    store = DistributedControlPlane(tmp_path / "ir_advance.sqlite3")
    service = DistributedGatewayService(store)
    tokens = ClientTokenStore(store)
    ro_tok = tokens.issue(subject="ro", label="ro", permissions=("project.read",), projects=("agentos-core",))["token"]
    rw_tok = tokens.issue(subject="chatgpt-web", label="chatgpt-web", permissions=("project.read", "ir.advance"), projects=("agentos-core",))["token"]

    server = DistributedGatewayServer(
        ("127.0.0.1", 0),
        service,
        token="root-secret",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        ro_client = ControlPlaneClient(base_url, token=ro_tok)
        with pytest.raises(ControlPlaneHTTPError) as exc_ro:
            ro_client.advance_ir(
                "agentos-core",
                observed_index_id=init_index,
                observed_ir_id=init_ir,
                next_action="Should fail",
            )
        assert exc_ro.value.status == 403

        rw_client = ControlPlaneClient(base_url, token=rw_tok)
        with pytest.raises(ControlPlaneHTTPError) as exc_stale:
            rw_client.advance_ir(
                "agentos-core",
                observed_index_id="idx-stale",
                observed_ir_id="ir_stale",
                next_action="Should conflict",
            )
        assert exc_stale.value.status == 409

        receipt = rw_client.advance_ir(
            "agentos-core",
            observed_index_id=init_index,
            observed_ir_id=init_ir,
            next_action="Verified remote handoff",
            decisions_append=["Web GPT advanced ONE IR with receipt"],
            evidence=[{"kind": "remote-handoff", "verdict": "PASS", "summary": "Verified writeback"}],
            actor="chatgpt-web",
        )
        assert receipt["schema"] == "agentos.ir-writeback-receipt/v1"
        assert receipt["ok"] is True
        assert receipt["credential_exposed"] is False
        assert receipt["previous"] == {"index_id": init_index, "ir_id": init_ir}
        assert receipt["publish_receipt"]["guarded_advance"] is True
        assert receipt["activation"]["ok"] is True

        resolved = resolve_active_continuation(data_root=data_root)
        assert resolved["selector"]["ir_id"] == receipt["current"]["ir_id"]
        assert resolved["selector"]["index_id"] == receipt["current"]["index_id"]
    finally:
        server.shutdown()
        server.server_close()
