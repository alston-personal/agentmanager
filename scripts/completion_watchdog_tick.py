"""Single bounded Completion Ledger wake tick through existing Chronos.

This runs the existing verified due-time transition, then (only for the exact
already-approved WoW #2134 WorkItem) projects an inspect-only Paw assignment.
Neither step grants execution, delivery, model, merge or deployment authority.
"""
from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from work_completion import load, wake_due
from approved_wow_paw_handoff import WORK_ID, handoff


def tick(data_root: Path, *, at: datetime | None = None) -> dict:
    root = data_root.expanduser().resolve()
    state = root / "governance" / "work-items.json"
    if not state.is_file():
        raise FileNotFoundError("completion_ledger_missing")
    lock_path = root / "governance" / "completion-watchdog-tick.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"schema": "agentos.completion-watchdog-tick/v1",
                    "status": "already_running", "credential_exposed": False}
        awakened = wake_due(state, actor="role://completion.watchdog", at=at)
        items = load(state).get("items") or {}
        if WORK_ID not in items:
            result = {"status": "no_approved_wow_work"}
        else:
            # Handoff itself checks the exact source, role, scope and authority.
            result = handoff(completion_state=state,
                             runtime_root=root / "employee-runtime")
        return {
            "schema": "agentos.completion-watchdog-tick/v1",
            "status": "completed",
            "awakened_wow": WORK_ID in awakened,
            "paw_projection": result.get("status", "not_registered"),
            "paw_registered": result.get("assignment_registered") is True,
            "credential_exposed": False,
        }


def main() -> int:
    root = Path(os.environ.get("AGENT_DATA_ROOT") or "/home/ubuntu/agent-data")
    if not root.is_absolute():
        raise SystemExit("agent_data_root_must_be_absolute")
    print(json.dumps(tick(root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
