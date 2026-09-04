#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

SOURCE_REF = "core/integration"
MARKER_SCHEMA = "agentos.action-relay-capabilities/v1"
SERVICE = "agentos-action-relay.service"


def _run(argv: list[str], *, cwd: Path, env: dict[str, str] | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _git_value(repo: Path, *args: str) -> str:
    result = _run(["git", *args], cwd=repo)
    if result.returncode != 0:
        raise RuntimeError("action_relay_reconcile_git_failed")
    return result.stdout.strip()


def _marker_current(marker: Path, *, source_commit: str) -> bool:
    if not marker.is_file():
        return False
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        isinstance(payload, dict)
        and payload.get("schema") == MARKER_SCHEMA
        and payload.get("source_ref") == SOURCE_REF
        and payload.get("source_commit") == source_commit
        and "agentos.runtime.converge" in set(payload.get("actions") or [])
        and "node.runtime.converge" in set(payload.get("node_capabilities") or [])
    )


def _service_active(repo: Path) -> bool:
    result = _run(["systemctl", "--user", "is-active", "--quiet", SERVICE], cwd=repo, timeout=20)
    return result.returncode == 0


def reconcile(*, repo: Path, data_root: Path) -> dict[str, Any]:
    repo = repo.resolve()
    data_root = data_root.resolve()
    if not (repo / ".git").exists():
        raise RuntimeError("action_relay_reconcile_repo_missing")
    installer = repo / "scripts" / "install_action_relay_user.sh"
    if not installer.is_file():
        raise RuntimeError("action_relay_reconcile_installer_missing")

    dirty = _git_value(repo, "status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise RuntimeError("action_relay_reconcile_tracked_checkout_dirty")
    current = _git_value(repo, "rev-parse", "HEAD")
    fetched = _run(["git", "fetch", "--no-tags", "origin", SOURCE_REF], cwd=repo)
    if fetched.returncode != 0:
        raise RuntimeError("action_relay_reconcile_source_fetch_failed")
    expected = _git_value(repo, "rev-parse", "FETCH_HEAD")
    if current != expected:
        raise RuntimeError("action_relay_reconcile_checkout_not_current_core_integration")

    marker = data_root / "runtime" / "action-relay" / "capabilities.json"
    if _marker_current(marker, source_commit=current) and _service_active(repo):
        return {
            "schema": "agentos.action-relay-generation-reconcile/v1",
            "status": "current",
            "source_ref": SOURCE_REF,
            "source_commit": current,
            "service_active": True,
            "credential_exposed": False,
        }

    env = os.environ.copy()
    env.update({
        "AGENTOS_REPO": str(repo),
        "AGENT_DATA_ROOT": str(data_root),
        "AGENTOS_ACTION_SOURCE_REF": SOURCE_REF,
        "AGENTOS_ACTION_SOURCE_COMMIT": current,
    })
    installed = _run(["bash", str(installer)], cwd=repo, env=env, timeout=300)
    if installed.returncode != 0:
        raise RuntimeError("action_relay_reconcile_install_failed")
    if not _marker_current(marker, source_commit=current):
        raise RuntimeError("action_relay_reconcile_marker_mismatch")
    if not _service_active(repo):
        raise RuntimeError("action_relay_reconcile_service_not_active")

    return {
        "schema": "agentos.action-relay-generation-reconcile/v1",
        "status": "reconciled",
        "source_ref": SOURCE_REF,
        "source_commit": current,
        "service_active": True,
        "credential_exposed": False,
    }


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    data_root = Path(os.environ.get("AGENT_DATA_ROOT") or os.environ.get("AGENT_DATA_DIR") or Path.home() / "agent-data")
    try:
        result = reconcile(repo=repo, data_root=data_root)
    except RuntimeError as exc:
        print(json.dumps({
            "schema": "agentos.action-relay-generation-reconcile/v1",
            "status": "failed",
            "error_code": str(exc),
            "credential_exposed": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
