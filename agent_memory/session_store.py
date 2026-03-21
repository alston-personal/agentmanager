"""
agent_memory/session_store.py
Formal session lifecycle management for Agent OS.

A "session" is a single continuous agent work period on a project.
Sessions have: start, end, objective, tasks touched, files touched, handover.
Every session is persisted as a YAML file — not appended to a global log.
"""
from __future__ import annotations

import uuid
import yaml
import dataclasses
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent_core.config import CENTRAL_PROJECTS_DIR
from agent_core.models import SessionRecord, SessionHandover
from agent_core.errors import SessionError


def _sessions_dir(project_id: str) -> Path:
    path = CENTRAL_PROJECTS_DIR / project_id / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_session(
    project_id: str,
    agent_id: str,
    agent_role: str = "engineer",
    entry_mode: str = "ide",
    objective: str = "",
    session_id: str = None,
) -> SessionRecord:
    """
    Open a new session. Writes the initial YAML immediately.
    Returns the SessionRecord so callers can attach to ctx.
    """
    sid = session_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    record = SessionRecord(
        session_id=sid,
        project_id=project_id,
        agent_id=agent_id,
        started_at=now,
        status="active",
        agent_role=agent_role,
        entry_mode=entry_mode,
        objective=objective,
    )
    _write_session(record)
    return record


def close_session(
    project_id: str,
    session_id: str,
    summary: str = "",
    tasks_started: list[str] = None,
    tasks_completed: list[str] = None,
    tasks_blocked: list[str] = None,
    files_touched: list[str] = None,
    pending_tasks: list[str] = None,
    next_agent_brief: str = "",
    context_notes: str = "",
) -> SessionRecord:
    """
    Close an existing session.
    - Sets ended_at, status=closed
    - Records handover payload
    - Persists updated YAML
    """
    record = load_session(project_id, session_id)
    if record is None:
        # Create a minimal closing record if session was never formally opened
        record = SessionRecord(
            session_id=session_id,
            project_id=project_id,
            agent_id="unknown",
            started_at=datetime.now(timezone.utc).isoformat(),
        )

    now = datetime.now(timezone.utc).isoformat()
    record.ended_at = now
    record.status = "closed"
    record.summary = summary
    record.tasks_started = tasks_started or []
    record.tasks_completed = tasks_completed or []
    record.tasks_blocked = tasks_blocked or []
    record.files_touched = files_touched or []
    record.handover = SessionHandover(
        pending_tasks=pending_tasks or [],
        next_agent_brief=next_agent_brief,
        context_notes=context_notes,
    )

    _write_session(record)
    return record


def load_session(project_id: str, session_id: str) -> Optional[SessionRecord]:
    """Load a session YAML by session_id. Returns None if not found."""
    sessions_dir = _sessions_dir(project_id)
    # Session files are named: YYYY-MM-DD_<session_id>.yaml
    # We search by session_id suffix
    for path in sessions_dir.glob(f"*_{session_id}.yaml"):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            handover_data = data.get("handover") or {}
            handover = SessionHandover(
                pending_tasks=handover_data.get("pending_tasks") or [],
                next_agent_brief=handover_data.get("next_agent_brief", ""),
                context_notes=handover_data.get("context_notes", ""),
            )
            return SessionRecord(
                session_id=data.get("session_id", session_id),
                project_id=data.get("project_id", project_id),
                agent_id=data.get("agent_id", "unknown"),
                started_at=data.get("started_at", ""),
                status=data.get("status", "active"),
                agent_role=data.get("agent_role", "engineer"),
                entry_mode=data.get("entry_mode", "ide"),
                ended_at=data.get("ended_at"),
                objective=data.get("objective", ""),
                summary=data.get("summary", ""),
                tasks_started=data.get("tasks_started") or [],
                tasks_completed=data.get("tasks_completed") or [],
                tasks_blocked=data.get("tasks_blocked") or [],
                files_touched=data.get("files_touched") or [],
                handover=handover,
            )
        except Exception:
            continue
    return None


def list_sessions(project_id: str, limit: int = 10) -> list[SessionRecord]:
    """Return the most recent sessions for a project, newest first."""
    sessions_dir = _sessions_dir(project_id)
    paths = sorted(sessions_dir.glob("*.yaml"), reverse=True)[:limit]
    results = []
    for path in paths:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            results.append(SessionRecord(
                session_id=data.get("session_id", ""),
                project_id=project_id,
                agent_id=data.get("agent_id", ""),
                started_at=data.get("started_at", ""),
                status=data.get("status", ""),
                summary=data.get("summary", ""),
            ))
        except Exception:
            continue
    return results


def _write_session(record: SessionRecord) -> Path:
    """Persist a SessionRecord as YAML. Filename: YYYY-MM-DD_<session_id>.yaml"""
    sessions_dir = _sessions_dir(record.project_id)
    date_str = record.started_at[:10]  # YYYY-MM-DD
    filename = f"{date_str}_{record.session_id}.yaml"
    path = sessions_dir / filename

    data = dataclasses.asdict(record)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

    return path
