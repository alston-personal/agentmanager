"""Lightweight Distributed AgentOS remote worker."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any

from runtime_core.canonical_ir import CanonicalIR
from runtime_core.remote_runtime import RemoteRuntimeWorker

from .codex_app_server_executor import BoundedCodexExecutor
from .control_plane_client import ControlPlaneClient


def _validate(ir: CanonicalIR) -> dict[str, Any]:
    return {
        "validated": True,
        "project_id": ir.project_id,
        "goal": ir.goal,
        "payload_keys": sorted(ir.payload),
    }


def _context_checkpoint(ir: CanonicalIR) -> dict[str, Any]:
    """Validate a deterministic context transition request.

    The node does not mutate canonical state. It only emits bounded evidence;
    the Kernel applies the checkpoint after validating the successful receipt.
    """
    completed_action = str(ir.payload.get("completed_action") or "").strip()
    finding = str(ir.payload.get("finding") or "").strip()
    next_action = str(ir.payload.get("next_action") or "").strip() or None
    if not completed_action or not finding:
        raise ValueError("context checkpoint requires completed_action and finding")
    if len(completed_action) > 4000 or len(finding) > 8000 or (next_action and len(next_action) > 4000):
        raise ValueError("context checkpoint field exceeds bounded size")
    return {
        "context_checkpoint": {
            "completed_action": completed_action,
            "finding": finding,
            "next_action": next_action,
        }
    }


def _codex_execute(ir: CanonicalIR) -> dict[str, Any]:
    working_set = ir.payload.get("working_set")
    instruction = str(ir.payload.get("instruction") or "")
    if not isinstance(working_set, dict):
        raise ValueError("bounded Codex executor requires working_set object")
    return BoundedCodexExecutor().execute(
        project_id=ir.project_id,
        working_set=working_set,
        instruction=instruction,
    )


def _load_object_registry(file_env: str, json_env: str) -> dict[str, Any]:
    registry_file = os.getenv(file_env)
    if registry_file:
        path = Path(registry_file).expanduser()
        if path.exists():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"{file_env} contains invalid JSON") from exc
            if not isinstance(value, dict):
                raise RuntimeError(f"{file_env} must contain a JSON object")
            return value

    raw = os.getenv(json_env, "{}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{json_env} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{json_env} must be an object")
    return value


def _project_paths() -> dict[str, str]:
    value = _load_object_registry("AGENTOS_PROJECT_PATHS_FILE", "AGENTOS_PROJECT_PATHS_JSON")
    return {str(k): str(v) for k, v in value.items() if k and v}


def _test_profiles() -> dict[str, Any]:
    return _load_object_registry("AGENTOS_PROJECT_TESTS_FILE", "AGENTOS_PROJECT_TESTS_JSON")


def _registered_project(project_id: str, *, purpose: str) -> Path:
    configured = _project_paths()
    raw_path = configured.get(project_id)
    if not raw_path:
        raise ValueError(f"project is not registered for native {purpose}: {project_id}")
    path = Path(raw_path).expanduser().resolve()
    if not path.is_dir() or not (path / ".git").exists():
        raise ValueError(f"registered project is not a git checkout: {project_id}")
    return path


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
    path = _registered_project(ir.project_id, purpose="inspection")
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


def _project_test(ir: CanonicalIR) -> dict[str, Any]:
    path = _registered_project(ir.project_id, purpose="testing")
    requested_profile = str(ir.payload.get("profile") or "default").strip()
    if not requested_profile:
        raise ValueError("test profile is required")

    project_profiles = _test_profiles().get(ir.project_id)
    if not isinstance(project_profiles, dict):
        raise ValueError(f"project has no registered native test profiles: {ir.project_id}")
    profile = project_profiles.get(requested_profile)
    if not isinstance(profile, dict):
        raise ValueError(f"test profile is not registered: {ir.project_id}/{requested_profile}")

    argv = profile.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        raise ValueError(f"registered test profile has invalid argv: {ir.project_id}/{requested_profile}")
    timeout_seconds = int(profile.get("timeout_seconds", 180))
    if timeout_seconds < 1 or timeout_seconds > 1800:
        raise ValueError("registered test profile timeout_seconds must be between 1 and 1800")

    completed = subprocess.run(
        argv,
        cwd=path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_seconds,
        check=False,
        env={**os.environ, "AGENTOS_NATIVE_TEST": "1"},
    )
    stdout = completed.stdout[-12000:]
    stderr = completed.stderr[-12000:]
    evidence = {
        "project_id": ir.project_id,
        "profile": requested_profile,
        "path": str(path),
        "head": _git(path, "rev-parse", "HEAD"),
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout": stdout,
        "stderr": stderr,
    }
    if completed.returncode != 0:
        summary = (stderr or stdout or "test command failed").strip()[-2000:]
        raise RuntimeError(
            f"native test profile failed ({ir.project_id}/{requested_profile}, rc={completed.returncode}): {summary}"
        )
    return evidence


def build_default_worker(runtime_id: str) -> RemoteRuntimeWorker:
    worker = RemoteRuntimeWorker(runtime_id)
    worker.register("agentos.ir.validate", _validate)
    worker.register("agentos.context.checkpoint", _context_checkpoint)
    worker.register("agentos.executor.codex", _codex_execute)
    worker.register("agentos.project.inspect", _inspect_project)
    worker.register("agentos.project.test", _project_test)
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
