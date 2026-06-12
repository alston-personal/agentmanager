from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime_core.interfaces import ContextProviderInterface


@dataclass(slots=True)
class SessionCloseResult:
    session_id: str
    record_path: Path
    record: dict[str, Any]
    compact_entry: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_str() -> str:
    return utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")


def iso_now() -> str:
    return utc_now().isoformat()


def close_session(
    context_provider: ContextProviderInterface,
    agent_name: str | None = None,
    summary: str | None = None,
    # Kept for signature compatibility but ignored since path policy is in host
    project_root: Path | None = None,
    data_root: Path | None = None,
) -> SessionCloseResult:
    context = context_provider.load_context()
    
    summary_value = summary or context.summary or "Session closed"
    ended_at = iso_now()
    session_id = uuid.uuid4().hex[:12]

    record = {
        "session_id": session_id,
        "started_at": context.started_at,
        "ended_at": ended_at,
        "project": context.project_id,
        "summary": summary_value,
        "files_touched": context.uncommitted_files,
        "pending_tasks": context.pending_tasks,
        "blockers": context.blockers,
        "next_steps": context.next_steps or (context.pending_tasks[:3] if context.pending_tasks else ["Review the updated status and continue from the next highest priority task."]),
        "branch": context.branch,
        "uncommitted_files": context.uncommitted_files,
        "agent": agent_name or os.environ.get("AGENT_NAME") or os.environ.get("USER") or "agent",
        "git": {
            "diff_stat": context.diff_stat,
        },
    }

    # The host adapter decides where and how to persist this, and returns the URI and compact string
    record_uri, compact_entry = context_provider.persist_session_close(record)

    return SessionCloseResult(
        session_id=record["session_id"],
        record_path=Path(record_uri),
        record=record,
        compact_entry=compact_entry
    )
