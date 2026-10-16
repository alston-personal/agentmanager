"""One bounded Bounty PDCA wake using an existing leased Control Plane task.

This adapter is invoked by the existing worker; it does NOT spawn a daemon,
schedule tasks or perform financial/network operations.
"""
from __future__ import annotations

from datetime import datetime, timezone
from agent_core.bounty_pdca import BountyCycle, advance_bounty_cycle, cycle_receipt


def run_bounty_pdca_wake(store, task, *, node_id: str):
    if task.get("capability") != "bounty.pdca.wake" or not node_id:
        raise ValueError("invalid wake capability or node")
    with store._connect() as db:
        row = db.execute("SELECT * FROM tasks WHERE task_id=?", (task.get("taskId"),)).fetchone()
    if row is None:
        raise ValueError("task missing from control plane")
    persisted = store._task_from_row(row)
    if persisted["status"] != "leased" or persisted["targetNodeId"] != node_id:
        raise ValueError("wake lease owner mismatch")
    expiry = persisted["leaseUntil"]
    if not expiry or datetime.fromisoformat(expiry.replace("Z","+00:00")) <= datetime.now(timezone.utc):
        raise ValueError("wake lease expired")
    payload = persisted["payload"]
    current = BountyCycle(**payload["cycle"])
    event = payload["event"]
    next_cycle = advance_bounty_cycle(current, event)
    result = cycle_receipt(next_cycle)
    result["transitionApplied"] = next_cycle.revision > current.revision
    result["previousRevision"] = current.revision
    result["upstreamWriteVerified"] = False
    return store.update_task(persisted["taskId"], "succeeded", result=result)
