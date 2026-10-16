"""Allowlisted, read-only GitHub Actions run discovery for Action Relay integration."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

REPOSITORY = "alston-personal/agentmanager"
WORKFLOWS = frozenset({"oracle-deploy-invoice-intake-service.yml"})
FIELDS = "databaseId,headSha,status,conclusion,url,createdAt,event,workflowName"
_RUN_URL = re.compile(r"https://github\\.com/alston-personal/agentmanager/actions/runs/[0-9]+")


def list_runs(params: dict[str, Any], *, runner: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    """Query runs only; no workflow dispatch, shell, mutable operations or credentials in output."""
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    repository = params.get("repository", REPOSITORY)
    workflow = params.get("workflow")
    event = params.get("event", "workflow_dispatch")
    limit = params.get("limit", 10)
    if repository != REPOSITORY or workflow not in WORKFLOWS:
        raise ValueError("repository/workflow not allowlisted")
    if event != "workflow_dispatch":
        raise ValueError("only workflow_dispatch is supported")
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("limit out of range")
    argv = ["/usr/bin/gh", "run", "list", "--repo", repository,
            "--workflow", workflow, "--event", event, "--limit", str(limit),
            "--json", FIELDS]
    result = runner(argv, cwd=Path.home(), capture_output=True, text=True,
                    timeout=25, check=False)
    if result.returncode != 0:
        return {"ok": False, "error": "GITHUB_ACTIONS_READ_FAILED", "runs": []}
    try:
        rows = json.loads(result.stdout)
    except (ValueError, TypeError):
        return {"ok": False, "error": "INVALID_GITHUB_RESPONSE", "runs": []}
    if not isinstance(rows, list):
        return {"ok": False, "error": "INVALID_GITHUB_RESPONSE", "runs": []}
    runs = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        run_id = row.get("databaseId")
        url = row.get("url")
        if type(run_id) is not int or run_id < 1 or not isinstance(url, str):
            continue
        if url != f"https://github.com/{repository}/actions/runs/{run_id}":
            continue
        runs.append({
            "run_id": run_id, "url": url,
            "head_sha": str(row.get("headSha") or "")[:40],
            "status": str(row.get("status") or "")[:32],
            "conclusion": str(row.get("conclusion") or "")[:32],
            "created_at": str(row.get("createdAt") or "")[:40],
        })
    return {"ok": True, "repository": repository, "workflow": workflow,
            "event": event, "runs": runs, "latest": runs[0] if runs else None}
