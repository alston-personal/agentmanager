"""Project-scoped read model for Distributed AgentOS continuity."""

from __future__ import annotations

from typing import Any

from .distributed_control_plane import DistributedControlPlane


ACTIVE_TASK_STATES = {"submitted", "leased", "running"}


def read_project_state(store: DistributedControlPlane, project_id: str) -> dict[str, Any]:
    """Return the latest durable task and the Canonical IR an IDE should resume from."""
    project_id = str(project_id or "").strip()
    if not project_id:
        raise ValueError("project_id is required")

    with store._connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM tasks
            WHERE project_id=?
            ORDER BY updated_at DESC, created_at DESC, task_id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()

    if row is None:
        return {
            "projectId": project_id,
            "latestTask": None,
            "currentIR": None,
            "currentSource": None,
            "recommendedAction": "start",
        }

    task = store._task_from_row(row)
    try:
        input_ir = store._ir_from_task(task)
    except ValueError:
        return {
            "projectId": project_id,
            "latestTask": task,
            "currentIR": None,
            "currentSource": None,
            "recommendedAction": "unsupported_task",
        }

    continuation = store.load_continuation_ir(task["taskId"])
    if continuation is not None:
        current_ir = continuation
        current_source = "task_continuation"
    else:
        current_ir = input_ir
        current_source = "task_input"

    status = task["status"]
    if status in ACTIVE_TASK_STATES:
        action = "wait"
    elif status == "succeeded":
        action = "continue"
    elif status in {"failed", "cancelled", "expired"}:
        action = "retry_or_continue"
    else:
        action = "continue"

    return {
        "projectId": project_id,
        "latestTask": task,
        "currentIR": current_ir.to_dict(),
        "currentSource": current_source,
        "recommendedAction": action,
    }
