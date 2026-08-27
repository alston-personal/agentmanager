"""Lightweight Distributed AgentOS remote worker."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
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


def _project_paths() -> dict[str, str]:
    registry_file = os.getenv("AGENTOS_PROJECT_PATHS_FILE")
    if registry_file:
        path = Path(registry_file).expanduser()
        if path.exists():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise RuntimeError("AGENTOS_PROJECT_PATHS_FILE contains invalid JSON") from exc
            if not isinstance(value, dict):
                raise RuntimeError("AGENTOS_PROJECT_PATHS_FILE must contain a JSON object")
            return {str(k): str(v) for k, v in value.items() if k and v}

    raw = os.getenv("AGENTOS_PROJECT_PATHS_JSON", "{}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AGENTOS_PROJECT_PATHS_JSON is invalid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("AGENTOS_PROJECT_PATHS_JSON must be an object")
    return {str(k): str(v) for k, v in value.items() if k and v}


def _git(path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip()


def _inspect_project(ir: CanonicalIR) -> dict[str, Any]:
    configured = _project_paths()
    raw_path = configured.get(ir.project_id)
    if not raw_path:
        raise ValueError(f"project is not registered for native inspection: {ir.project_id}")
    path = Path(raw_path).expanduser().resolve()
    if not path.is_dir() or not (path / ".git").exists():
        raise ValueError(f"registered project is not a git checkout: {ir.project_id}")
    status = _git(path, "status", "--porcelain")
    remotes = _git(path, "remote")
    branch = _git(path, "branch", "--show-current")
    return {
        "project_id": ir.project_id,
        "path": str(path),
        "head": _git(path, "rev-parse", "HEAD"),
        "branch": branch or None,
        "dirty": bool(status),
        "dirty_entries": status.splitlines()[:50],
        "remote": _git(path, "remote", "get-url", "origin") if "origin" in remotes.splitlines() else None,
    }


def build_default_worker(runtime_id: str) -> RemoteRuntimeWorker:
    worker = RemoteRuntimeWorker(runtime_id)
    worker.register("agentos.ir.validate", _validate)
    worker.register("agentos.project.inspect", _inspect_project)
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
