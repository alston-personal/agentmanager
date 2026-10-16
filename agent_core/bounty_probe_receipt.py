"""Bridge a GitHub capability probe receipt into the existing ONE ControlPlaneStore.

A READY read-probe must never be promoted to a PR-delivery success.
No new scheduler or new task state is introduced.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


OUTCOMES = {"READY", "AUTH_REQUIRED", "NOT_FOUND", "RETRYABLE", "BLOCKED", "UNVERIFIED"}


def reconcile_probe_receipt(store: Any, task_id: str, path: str | Path) -> dict[str, Any]:
    """Checkpoint a completed probe. Consumer owns the task lease and receipt path."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("outcome") not in OUTCOMES:
        raise ValueError("invalid capability probe receipt")
    if data.get("capability") != "github.repo.read":
        raise ValueError("unsupported probe capability")
    if not isinstance(data.get("repository"), str) or "/" not in data["repository"]:
        raise ValueError("receipt missing repository")
    outcome = data["outcome"]
    # READ capability only; this records that the probe finished, not that a bounty was delivered.
    status = "succeeded" if outcome == "READY" else "failed"
    receipt = {
        "receiptKind": "github-capability-probe/v1",
        "capability": data["capability"],
        "repository": data["repository"],
        "outcome": outcome,
        "reason": str(data.get("reason", "")),
        "httpStatus": data.get("http_status"),
        "upstreamWriteVerified": False,
        "bountyDelivered": False,
    }
    return store.update_task(task_id, status, result=receipt)
