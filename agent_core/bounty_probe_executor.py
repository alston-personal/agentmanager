"""Execute one *already leased* github.repo.read task through the governed worker.

No polling loop, scheduler, credential output or upstream write permissions.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any

from agent_core.bounty_probe_receipt import reconcile_probe_receipt


def run_leased_probe(store: Any, task: dict[str, Any], *, node_id: str, python: str = sys.executable,
                     script: Path | None = None) -> dict[str, Any]:
    if not node_id:
        raise ValueError("node_id required")
    # Trust durable storage, not the task dictionary supplied by a worker.
    with store._connect() as connection:
        row = connection.execute("SELECT * FROM tasks WHERE task_id=?", (task.get("taskId"),)).fetchone()
    if row is None:
        raise ValueError("task does not exist")
    task = store._task_from_row(row)
    lease_until = task.get("leaseUntil")
    if task.get("targetNodeId") != node_id or not lease_until:
        raise ValueError("lease not owned by this node")
    lease_deadline = datetime.fromisoformat(lease_until.replace("Z", "+00:00"))
    if lease_deadline <= datetime.now(timezone.utc):
        raise ValueError("task lease expired")
    if task.get("status") not in ("leased", "running"):
        raise ValueError("probe task must be leased or running")
    if task.get("capability") != "github.repo.read":
        raise ValueError("unsupported capability")
    repo = task.get("payload", {}).get("repo")
    if not isinstance(repo, str) or len(repo.split("/")) != 2 or not all(repo.split("/")):
        raise ValueError("invalid repository")
    task_id = task["taskId"]
    script = script or Path(__file__).resolve().parents[1] / "scripts" / "bounty_github_delivery_probe.py"
    # A receipt file stays in a temporary directory until reconciled into the Control Plane DB.
    with tempfile.TemporaryDirectory(prefix="agentos-bounty-probe-") as folder:
        receipt_path = Path(folder) / "receipt.json"
        env = dict(os.environ)
        # Pass token through inherited environment, never command arguments.
        process = subprocess.run(
            [python, str(script), "--repo", repo, "--receipt-file", str(receipt_path)],
            capture_output=True, text=True, timeout=40, env=env, check=False,
        )
        if not receipt_path.exists():
            return store.update_task(task_id, "failed", result={
                "receiptKind": "github-capability-probe/v1",
                "outcome": "BLOCKED", "reason": "probe_did_not_emit_receipt",
                "probeExitCode": process.returncode,
                "bountyDelivered": False, "upstreamWriteVerified": False,
            })
        return reconcile_probe_receipt(store, task_id, receipt_path)
