"""
agent_memory/event_store.py
Dual-layer event logging for Agent OS.

Layer 1 (volatile): /dev/shm/leopardcat-swarm/events.log — JSONL, real-time, fast
Layer 2 (persistent): agent-data/projects/{id}/events.jsonl — JSONL, durable, per-project

Both layers are append-only. The volatile layer is for live swarm monitoring.
The persistent layer is the source of truth for observability and audit.
"""
from __future__ import annotations

import json
import dataclasses
from datetime import datetime, timezone
from pathlib import Path

from agent_core.config import (
    CENTRAL_PROJECTS_DIR,
    LCS_SHM_ROOT,
    LCS_EVENTS_LOG,
    EVENTS_JSONL_NAME,
)
from agent_core.models import EventRecord


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def emit(
    event_type: str,
    project_id: str = "system",
    actor: str = "system",
    session_id: str = None,
    entity: str = "",
    payload: dict = None,
) -> EventRecord:
    """
    Emit an event to both volatile (LCS) and persistent (per-project) logs.
    This is the primary public function — callers don't construct EventRecord directly.

    event_type examples:
        session_started | session_closed | task_updated | project_updated
        workflow_executed | system_alert | handover_generated
    """
    record = EventRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type=event_type,
        project_id=project_id,
        actor=actor,
        session_id=session_id,
        entity=entity,
        payload=payload or {},
    )

    _write_lcs(record)
    _write_persistent(record)

    return record


def read_project_events(project_id: str, limit: int = 50) -> list[dict]:
    """Read the last N events from the per-project persistent event log."""
    path = CENTRAL_PROJECTS_DIR / project_id / EVENTS_JSONL_NAME
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    recent = lines[-limit:]
    result = []
    for line in recent:
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return result


def read_lcs_events(limit: int = 100) -> list[dict]:
    """Read the last N events from the volatile LCS event log."""
    if not LCS_EVENTS_LOG.exists():
        return []
    lines = LCS_EVENTS_LOG.read_text(encoding="utf-8").strip().splitlines()
    recent = lines[-limit:]
    result = []
    for line in recent:
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return result


# ---------------------------------------------------------------------------
# Internal writers
# ---------------------------------------------------------------------------

def _write_lcs(record: EventRecord) -> None:
    """Append to volatile LCS event log. Silently skip if /dev/shm unavailable."""
    try:
        LCS_SHM_ROOT.mkdir(parents=True, exist_ok=True)
        _append_jsonl(LCS_EVENTS_LOG, record)
    except Exception:
        pass  # LCS is best-effort


def _write_persistent(record: EventRecord) -> None:
    """Append to the per-project durable event log."""
    project_dir = CENTRAL_PROJECTS_DIR / record.project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    events_path = project_dir / EVENTS_JSONL_NAME
    _append_jsonl(events_path, record)


def _append_jsonl(path: Path, record: EventRecord) -> None:
    data = dataclasses.asdict(record)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")
