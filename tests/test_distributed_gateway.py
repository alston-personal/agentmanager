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


def test_non_loopback_gateway_requires_token():
    with pytest.raises(ValueError, match="TOKEN"):
        validate_bind_security("0.0.0.0", None)
    validate_bind_security("0.0.0.0", "secret")
    validate_bind_security("127.0.0.1", None)
