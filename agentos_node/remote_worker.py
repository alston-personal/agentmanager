"""Single-shot lightweight Distributed AgentOS remote worker."""

from __future__ import annotations

from typing import Any

from runtime_core.canonical_ir import CanonicalIR
from runtime_core.remote_runtime import RemoteRuntimeWorker

from .control_plane_client import ControlPlaneClient


def _validate(ir: CanonicalIR) -> dict[str, Any]:
    return {
        "validated": True,
        "project_id": ir.project_id,
        "goal": ir.goal,
        "payload_keys": sorted(ir.payload),
    }


def build_default_worker(runtime_id: str) -> RemoteRuntimeWorker:
    worker = RemoteRuntimeWorker(runtime_id)
    worker.register("agentos.ir.validate", _validate)
    return worker


def run_once(
    client: ControlPlaneClient,
    runtime_id: str,
    *,
    worker: RemoteRuntimeWorker | None = None,
    lease_seconds: int = 60,
    task_id: str | None = None,
) -> dict[str, Any]:
    active_worker = worker or build_default_worker(runtime_id)
    if active_worker.runtime_id != runtime_id:
        raise ValueError("worker.runtime_id must match the leasing runtime_id")

    lease = (
        client.lease_task(task_id, runtime_id, lease_seconds=lease_seconds)
        if task_id
        else client.lease(runtime_id, active_worker.capabilities, lease_seconds=lease_seconds)
    )
    if lease is None:
        return {"status": "idle", "runtime_id": runtime_id, "task_id": task_id}

    if task_id and str(lease.get("taskId")) != task_id:
        raise ValueError("exact lease returned unexpected task id")
    raw_ir = lease.get("canonicalIR")
    if not isinstance(raw_ir, dict):
        raise ValueError("lease canonicalIR must be an object")
    ir = CanonicalIR.from_dict(raw_ir)
    if lease.get("inputDigest") != ir.digest():
        raise ValueError("lease Canonical IR digest mismatch")

    result = active_worker.execute(ir)
    completed = client.complete(str(lease["taskId"]), result)
    return {
        "status": result.status,
        "runtime_id": runtime_id,
        "task_id": lease["taskId"],
        "completed": completed,
    }
