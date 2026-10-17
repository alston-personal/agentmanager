"""One bounded Bounty PDCA wake using an existing leased Control Plane task.

This adapter is invoked by the existing worker; it does NOT spawn a daemon,
schedule tasks or perform financial/network operations.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
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
    cycle_key = payload.get("cycleKey")
    if not isinstance(cycle_key, str) or not cycle_key:
        raise ValueError("cycleKey required")
    current = BountyCycle(**payload["cycle"])
    event = payload["event"]
    next_cycle = advance_bounty_cycle(current, event)
    result = cycle_receipt(next_cycle)
    result["transitionApplied"] = next_cycle.revision > current.revision
    result["previousRevision"] = current.revision
    result["upstreamWriteVerified"] = False
    # Compare-and-swap while holding a SQLite write transaction: a reassigned or
    # expired lease cannot be completed by the previous Node.
    with store._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS bounty_cycles (cycle_key TEXT PRIMARY KEY, revision INTEGER NOT NULL, state_json TEXT NOT NULL)")
        existing = db.execute("SELECT revision,state_json FROM bounty_cycles WHERE cycle_key=?", (cycle_key,)).fetchone()
        if existing is None:
            if current.revision != 0:
                raise ValueError("missing cycle state")
        elif existing["revision"] != current.revision or json.loads(existing["state_json"]) != vars(current):
            raise ValueError("stale PDCA revision")
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        changed = db.execute(
            "UPDATE tasks SET status='succeeded', result_json=?, updated_at=? "
            "WHERE task_id=? AND status='leased' AND target_node_id=? "
            "AND lease_until=? AND lease_until>?",
            (json.dumps(result, sort_keys=True), now, persisted["taskId"],
             node_id, expiry, now),
        )
        if changed.rowcount != 1:
            raise ValueError("lease changed before committing PDCA wake")
        if existing is None:
            db.execute("INSERT INTO bounty_cycles VALUES (?,?,?)",
                       (cycle_key, next_cycle.revision, json.dumps(vars(next_cycle), sort_keys=True)))
        elif next_cycle.revision != current.revision:
            db.execute("UPDATE bounty_cycles SET revision=?,state_json=? WHERE cycle_key=? AND revision=?",
                       (next_cycle.revision, json.dumps(vars(next_cycle), sort_keys=True),
                        cycle_key, current.revision))
        row = db.execute("SELECT * FROM tasks WHERE task_id=?", (persisted["taskId"],)).fetchone()
        db.commit()
    return store._task_from_row(row)
