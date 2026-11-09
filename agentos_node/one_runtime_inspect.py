from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

RUNTIME_INSPECT_SCHEMA = "agentos.one-runtime-inspect/v0.1"
FIXED_SERVICES = {
    "core_supervisor": "agentos-core-supervisor.service",
    "employee_worker_host": "agentos-employee-worker-host.service",
    "legacy_native_node": "agentos-node.service",
    "chatgpt_mcp": "agentos-chatgpt-mcp.service",
}


def _git(repo_root: Path, *args: str) -> str | None:
    if not repo_root.is_dir() or not (repo_root / ".git").exists():
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip()


def _git_projection(repo_root: Path) -> dict[str, Any]:
    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(repo_root, "status", "--porcelain", "--untracked-files=no")
    return {
        "present": bool(head),
        "head_sha": head if head and len(head) == 40 else None,
        "branch": branch or None,
        "dirty_tracked": bool(status) if status is not None else None,
    }


def _service_state(unit: str) -> str:
    try:
        completed = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    state = completed.stdout.strip().lower()
    if state in {"active", "inactive", "activating", "deactivating", "failed"}:
        return state
    if completed.returncode == 4:
        return "missing"
    return "unknown"


def _realm_projection(data_root: Path, core_node_id: str) -> dict[str, Any]:
    nodes_path = data_root / "realm" / "nodes.json"
    fabric_path = data_root / "realm" / "fabric.json"
    try:
        payload = json.loads(nodes_path.read_text(encoding="utf-8")) if nodes_path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        payload = {}
    nodes_obj = payload.get("nodes") if isinstance(payload, dict) else None
    if isinstance(nodes_obj, dict):
        node = nodes_obj.get(core_node_id)
        node_count = len(nodes_obj)
    elif isinstance(nodes_obj, list):
        node = next((item for item in nodes_obj if isinstance(item, dict) and item.get("node_id") == core_node_id), None)
        node_count = len(nodes_obj)
    else:
        node = None
        node_count = 0
    node = node if isinstance(node, dict) else {}
    return {
        "realm_id": payload.get("realm_id") if isinstance(payload, dict) else None,
        "fabric_present": fabric_path.is_file(),
        "registry_present": nodes_path.is_file(),
        "node_count": node_count,
        "core_node": {
            "node_id": core_node_id,
            "registered": bool(node),
            "status": node.get("status"),
            "last_heartbeat_at": node.get("last_heartbeat_at"),
            "capabilities": sorted(str(v)[:128] for v in (node.get("capabilities") or []) if isinstance(v, str))[:128],
            "employee_wake_capable": "agent.employee.wake.deliver" in set(node.get("capabilities") or []),
        },
    }


def inspect_oracle_runtime(
    *,
    data_root: Path | None = None,
    core_repo_root: Path | None = None,
    legacy_repo_root: Path | None = None,
    core_node_id: str | None = None,
) -> dict[str, Any]:
    """Return fixed, sanitized Oracle runtime facts without accepting command/path inputs."""
    root = (data_root or Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))).expanduser()
    core_repo = (core_repo_root or Path(os.environ.get("AGENTOS_CORE_SOURCE_ROOT", "/home/ubuntu/agentmanager"))).expanduser()
    legacy_repo = (legacy_repo_root or Path(os.environ.get("AGENTOS_LEGACY_RUNTIME_ROOT", "/home/ubuntu/agentos-distributed"))).expanduser()
    node_id = str(core_node_id or os.environ.get("AGENTOS_CORE_NODE_ID", "oracle-core-node")).strip()
    if not node_id:
        raise ValueError("core_node_id_required")

    return {
        "schema": RUNTIME_INSPECT_SCHEMA,
        "mode": "oracle-local-readonly",
        "credential_exposed": False,
        "mutation_allowed": False,
        "core_source": _git_projection(core_repo),
        "legacy_runtime_source": _git_projection(legacy_repo),
        "realm": _realm_projection(root, node_id),
        "services": {name: _service_state(unit) for name, unit in FIXED_SERVICES.items()},
    }
