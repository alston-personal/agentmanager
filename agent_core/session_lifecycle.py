from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import config
from .platform.base import tail_text
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


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""

def _project_name(project_root: Path) -> str:
    return project_root.resolve().name

def _project_data_root(data_root: Path, project_root: Path) -> Path:
    return data_root / "projects" / _project_name(project_root)


def _session_sync_path(data_root: Path) -> Path:
    return data_root / "memory" / "session_sync.md"


def _archive_session_sync_if_needed(session_sync_path: Path) -> None:
    if not session_sync_path.exists() or session_sync_path.stat().st_size <= 50_000:
        return
    archive_dir = session_sync_path.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_path = archive_dir / f"session_sync_{stamp}.md"
    archive_path.write_text(session_sync_path.read_text(encoding="utf-8"), encoding="utf-8")
    session_sync_path.write_text(
        "# 🧠 AgentOS Session Sync - Compressed Working Memory\n"
        "> Auto-rotated because the buffer exceeded 50KB.\n",
        encoding="utf-8",
    )


def _append_session_sync(session_sync_path: Path, payload: dict[str, Any], record_path: Path) -> None:
    session_sync_path.parent.mkdir(parents=True, exist_ok=True)
    _archive_session_sync_if_needed(session_sync_path)
    compact = "\n".join(
        [
            f"## Session Handoff @ {payload['ended_at']}",
            f"- **Project**: `{payload['project']}`",
            f"- **Session ID**: `{payload['session_id']}`",
            f"- **Summary**: {payload['summary']}",
            f"- **Branch**: `{payload['branch']}`",
            f"- **Pending Tasks**: {len(payload['pending_tasks'])}",
            f"- **Blockers**: {len(payload['blockers'])}",
            f"- **Next Steps**: {len(payload['next_steps'])}",
            f"- **Uncommitted Files**: {', '.join(payload['uncommitted_files'][:5]) or 'none'}",
            f"- **Session Record**: `{record_path}`",
            "",
        ]
    )
    existing = _read_text(session_sync_path).rstrip()
    if existing:
        content = existing + "\n\n" + compact
    else:
        content = "# 🧠 AgentOS Session Sync - Compressed Working Memory\n\n" + compact
    session_sync_path.write_text(content.rstrip() + "\n", encoding="utf-8")


def close_session(
    context_provider: ContextProviderInterface,
    agent_name: str | None = None,
    summary: str | None = None,
    project_root: Path | None = None,
    data_root: Path | None = None,
) -> SessionCloseResult:
    context = context_provider.load_context()
    
    project_root_val = Path(project_root or config.PROJECT_ROOT).expanduser().resolve()
    data_root_val = Path(data_root or config.AGENT_DATA_ROOT).expanduser().resolve()
    project_data_root = _project_data_root(data_root_val, project_root_val)
    session_sync_path = _session_sync_path(data_root_val)

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
        "next_steps": context.next_steps or (context.pending_tasks[:3] if context.pending_tasks else ["Review the updated STATUS.md and continue from the next highest priority task."]),
        "branch": context.branch,
        "uncommitted_files": context.uncommitted_files,
        "agent": agent_name or os.environ.get("AGENT_NAME") or os.environ.get("USER") or "agent",
        "git": {
            "diff_stat": context.diff_stat,
        },
    }

    session_record_dir = project_data_root / "sessions"
    session_record_dir.mkdir(parents=True, exist_ok=True)
    session_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    record_path = session_record_dir / f"{session_date}_{record['session_id']}.yaml"
    record_path.write_text(yaml.safe_dump(record, sort_keys=False, allow_unicode=True), encoding="utf-8")

    # Persist the close back via context provider interface
    context_provider.persist_session_close(record)
    
    _append_session_sync(session_sync_path, record, record_path)

    compact_entry = "\n".join(
        [
            f"Session `{record['session_id']}` closed for `{record['project']}`",
            f"Summary: {record['summary']}",
            f"Branch: `{record['branch']}`",
            f"Pending: {len(record['pending_tasks'])}, Blockers: {len(record['blockers'])}, Next: {len(record['next_steps'])}",
            f"Record: `{record_path}`",
        ]
    )
    return SessionCloseResult(session_id=record["session_id"], record_path=record_path, record=record, compact_entry=compact_entry)


def latest_session_records(project_root: Path | None = None, data_root: Path | None = None, limit: int = 3) -> list[dict[str, Any]]:
    project_root = Path(project_root or config.PROJECT_ROOT).expanduser().resolve()
    data_root = Path(data_root or config.AGENT_DATA_ROOT).expanduser().resolve()
    session_dir = _project_data_root(data_root, project_root) / "sessions"
    if not session_dir.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(session_dir.glob("*.yaml"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                data["record_path"] = str(path)
                records.append(data)
        except Exception:
            continue
    return records


def read_compact_session_sync(data_root: Path | None = None, max_chars: int = 6000) -> str:
    data_root = Path(data_root or config.AGENT_DATA_ROOT).expanduser().resolve()
    return tail_text(_session_sync_path(data_root), max_chars=max_chars)
