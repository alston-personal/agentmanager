"""
actions/report.py
/report action — FORMAL session lifecycle closing protocol.

This replaces the old handover.py (67-line append-only).
New /report does ALL of the following atomically:
  1. Closes the session (writes sessions/YYYY-MM-DD_<session_id>.yaml)
  2. Extracts pending tasks from memory/SHORT_TERM.md
  3. Updates project.yaml: updated_at, health.freshness, current_focus
  4. Emits session_closed event to both LCS bus and per-project events.jsonl
  5. Appends COMPACT (≤15 line) entry to session_sync.md
  6. Auto-archives session_sync.md if > 50KB
  7. Sends Telegram notification
  8. Prints structured next_agent_brief to stdout
"""
from __future__ import annotations

import dataclasses
import yaml
from datetime import datetime, timezone
from pathlib import Path

from agent_core.context import RuntimeContext
from agent_core.registry import registry, ActionResult
from agent_core.config import CENTRAL_PROJECTS_DIR, MEMORY_DIR
from agent_core.errors import ProjectNotFoundError
from agent_core.project_store import load_project, save_project
from agent_memory.session_store import close_session
from agent_memory.event_store import emit as emit_event
from agent_memory.handover import (
    generate_brief,
    append_compact_to_sync,
    extract_pending_from_markdown,
    archive_sync_if_needed,
)
from agent_core.renderer import send_telegram


@registry.register(
    "report",
    description="Formal session close: write session record, update project, emit events, generate handover",
    aliases=["r"],
    requires_project=False,  # Will infer from cwd or --project flag
)
def handle_report(ctx: RuntimeContext) -> ActionResult:
    """
    Full session lifecycle close protocol.
    """
    # -----------------------------------------------------------------------
    # 1. Resolve project
    # -----------------------------------------------------------------------
    project_id = ctx.project_id or _infer_project_from_cwd()
    if not project_id:
        return ActionResult.fail(
            "Cannot determine project. Use --project <id> or run from project directory.",
            exit_code=2,
        )

    project = load_project(project_id)
    if project is None:
        return ActionResult.fail(
            f"Project '{project_id}' not found (no project.yaml).\n"
            f"Run: `python3 scripts/init_project_yaml.py --project {project_id}`",
            exit_code=2,
        )

    # -----------------------------------------------------------------------
    # 2. Collect session data from args / prompts
    # -----------------------------------------------------------------------
    summary = ctx.flags.get("summary", "") or ""
    tasks_completed_raw = ctx.flags.get("completed", "") or ""
    tasks_blocked_raw = ctx.flags.get("blocked", "") or ""

    tasks_completed = [t.strip() for t in tasks_completed_raw.split(",") if t.strip()]
    tasks_blocked = [t.strip() for t in tasks_blocked_raw.split(",") if t.strip()]

    # Extract pending from SHORT_TERM.md
    memory_dir = CENTRAL_PROJECTS_DIR / project_id / "memory"
    short_term_path = memory_dir / "SHORT_TERM.md"
    if not short_term_path.exists():
        # Fallback: check project code path
        code_memory = Path(project.actual_code_path) / "memory" / "SHORT_TERM.md"
        short_term_path = code_memory if code_memory.exists() else short_term_path

    pending_tasks = extract_pending_from_markdown(short_term_path)

    # -----------------------------------------------------------------------
    # 3. Generate next_agent_brief
    # -----------------------------------------------------------------------
    brief = generate_brief(
        project_id=project_id,
        agent_id=ctx.agent_id,
        summary=summary,
        tasks_completed=tasks_completed,
        tasks_blocked=tasks_blocked,
        pending_tasks=pending_tasks,
        files_touched=[],  # Future: track via git diff
        context_notes=ctx.flags.get("notes", ""),
    )

    # -----------------------------------------------------------------------
    # 4. Close session (writes sessions/YYYY-MM-DD_<id>.yaml)
    # -----------------------------------------------------------------------
    session_record = close_session(
        project_id=project_id,
        session_id=ctx.session_id,
        summary=summary,
        tasks_completed=tasks_completed,
        tasks_blocked=tasks_blocked,
        pending_tasks=pending_tasks,
        next_agent_brief=brief,
        context_notes=ctx.flags.get("notes", ""),
    )

    # -----------------------------------------------------------------------
    # 5. Update project.yaml
    # -----------------------------------------------------------------------
    now = datetime.now(timezone.utc).isoformat()
    project.updated_at = now
    project.health.freshness = "fresh"
    project.health.sync_state = "synced"
    project.health.last_verified_at = now
    if pending_tasks:
        project.next_action = pending_tasks[0]
    if summary:
        project.current_focus = summary[:150]
    save_project(project)

    # -----------------------------------------------------------------------
    # 6. Emit event (both LCS + persistent)
    # -----------------------------------------------------------------------
    emit_event(
        event_type="session_closed",
        project_id=project_id,
        actor=ctx.agent_id,
        session_id=ctx.session_id,
        entity=project_id,
        payload={
            "summary": summary,
            "tasks_completed": tasks_completed,
            "tasks_blocked": tasks_blocked,
            "pending_count": len(pending_tasks),
        },
    )

    # -----------------------------------------------------------------------
    # 7. Compact append to session_sync.md (≤15 lines)
    # -----------------------------------------------------------------------
    append_compact_to_sync(
        project_id=project_id,
        agent_id=ctx.agent_id,
        session_id=ctx.session_id,
        summary=summary,
        pending_tasks=pending_tasks,
        next_agent_brief=brief,
    )

    # Auto-archive if session_sync.md getting large
    archived = archive_sync_if_needed()
    warnings = []
    if archived:
        warnings.append(f"session_sync.md was large — archived to: {archived.name}")

    # -----------------------------------------------------------------------
    # 8. Telegram notification
    # -----------------------------------------------------------------------
    tg_text = (
        f"✅ *Session Closed*: `{project_id}`\n"
        f"Agent: `{ctx.agent_id}` | Session: `{ctx.session_id[:8]}…`\n"
        f"Completed: {len(tasks_completed)} | Pending: {len(pending_tasks)}\n"
        f"_{summary[:120] if summary else 'No summary provided.'}_"
    )
    send_telegram(tg_text)

    # -----------------------------------------------------------------------
    # 9. Build output
    # -----------------------------------------------------------------------
    output_lines = [
        f"## ✅ Session Closed: `{project_id}`",
        "",
        f"**Session ID:** `{ctx.session_id}`",
        f"**Agent:** `{ctx.agent_id}`",
        f"**Completed:** {len(tasks_completed)} tasks",
        f"**Pending:** {len(pending_tasks)} tasks",
        "",
        "---",
        "",
        brief,
        "",
        f"_Session record: `agent-data/projects/{project_id}/sessions/`_",
        f"_Events logged: `agent-data/projects/{project_id}/events.jsonl`_",
    ]

    return ActionResult(
        success=True,
        output="\n".join(output_lines),
        data={
            "session_id": ctx.session_id,
            "project_id": project_id,
            "tasks_completed": len(tasks_completed),
            "pending_tasks": len(pending_tasks),
        },
        exit_code=0,
        warnings=warnings,
    )


def _infer_project_from_cwd() -> str | None:
    """Guess project_id from the current working directory name."""
    import os
    cwd = Path(os.getcwd())
    # If we're inside agent-data/projects/<id>/
    parts = cwd.parts
    for i, part in enumerate(parts):
        if part == "projects" and i + 1 < len(parts):
            return parts[i + 1]
    # If we're inside workspace/<id>/
    for i, part in enumerate(parts):
        if part == "workspace" and i + 1 < len(parts):
            return parts[i + 1]
    return None
