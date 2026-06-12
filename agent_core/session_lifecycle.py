from __future__ import annotations

import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import config
from .platform import get_platform_driver
from .platform.base import tail_text, write_json


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


def _project_name(project_root: Path) -> str:
    return project_root.resolve().name


def _project_data_root(data_root: Path, project_root: Path) -> Path:
    return data_root / "projects" / _project_name(project_root)


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _parse_yaml_frontmatter(content: str) -> dict[str, Any]:
    if not content.startswith("---"):
        return {}
    lines = content.splitlines()
    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        return {}
    try:
        data = yaml.safe_load("\n".join(lines[1:end_idx])) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _extract_table_value(content: str, label: str) -> str:
    pattern = rf"\|\s*\*\*{re.escape(label)}\*\*\s*\|\s*([^|]+?)\s*\|"
    match = re.search(pattern, content)
    return match.group(1).strip() if match else ""


def _extract_section(content: str, heading: str) -> str:
    lines = content.splitlines()
    found = None
    for idx, line in enumerate(lines):
        if line.strip() == heading.strip():
            found = idx
            break
    if found is None:
        return ""
    start = found + 1
    end = len(lines)
    for idx in range(start, len(lines)):
        if lines[idx].startswith("## ") and idx > start:
            end = idx
            break
    return "\n".join(lines[start:end]).strip()


def _collect_checklist_items(content: str) -> list[str]:
    items: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ]") or stripped.startswith("* [ ]"):
            items.append(stripped[5:].strip())
    return items


def _collect_blockers(content: str) -> list[str]:
    blockers: list[str] = []
    in_blockers = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") and any(token in stripped.lower() for token in ["blocker", "blocked", "阻擋", "阻斷", "障礙"]):
            in_blockers = True
            continue
        if in_blockers and stripped.startswith("## "):
            break
        if in_blockers and stripped.startswith(("- ", "* ")):
            blockers.append(stripped[2:].strip())
    return blockers


def _collect_next_steps(content: str) -> list[str]:
    next_steps: list[str] = []
    in_next = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") and any(token in stripped.lower() for token in ["next", "next step", "下一步", "後續"]):
            in_next = True
            continue
        if in_next and stripped.startswith("## "):
            break
        if in_next and stripped.startswith(("- ", "* ")):
            next_steps.append(stripped[2:].strip())
    return next_steps


def _derive_summary(short_term: str, status_content: str) -> str:
    summary = _extract_table_value(status_content, "Last Status")
    if summary:
        return summary
    for line in short_term.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("-"):
            return stripped.lstrip("- ").strip()
    return "Session closed"


def _derive_started_at(short_term_path: Path, short_term_content: str) -> str:
    metadata = _parse_yaml_frontmatter(short_term_content)
    for key in ("started_at", "session_started_at", "session_start_at"):
        if metadata.get(key):
            return str(metadata[key])
    env_hint = os.environ.get("AGENT_SESSION_STARTED_AT")
    if env_hint:
        return env_hint
    if short_term_path.exists():
        try:
            return datetime.fromtimestamp(short_term_path.stat().st_mtime, tz=timezone.utc).isoformat()
        except Exception:
            pass
    return iso_now()


def _git_state(project_root: Path) -> dict[str, Any]:
    branch = "unknown"
    uncommitted_files: list[str] = []
    diff_stat = ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            branch = result.stdout.strip()
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.splitlines():
                if len(line) > 3:
                    uncommitted_files.append(line[3:].strip())
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            diff_stat = result.stdout.strip()
    except Exception:
        pass
    return {"branch": branch, "uncommitted_files": uncommitted_files, "diff_stat": diff_stat}


def _compact_list(values: list[str], limit: int = 5) -> list[str]:
    items = [value.strip() for value in values if value and value.strip()]
    return items[:limit]


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


def build_session_close_payload(
    project_root: Path | None = None,
    data_root: Path | None = None,
    agent_name: str | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    project_root = Path(project_root or config.PROJECT_ROOT).expanduser().resolve()
    data_root = Path(data_root or config.AGENT_DATA_ROOT).expanduser().resolve()
    driver = get_platform_driver(project_root=project_root, data_root=data_root)
    driver.ensure_project_links(project_root, data_root)

    project_name = _project_name(project_root)
    project_data_root = _project_data_root(data_root, project_root)
    short_term_path = project_data_root / "memory" / "SHORT_TERM.md"
    status_path = project_data_root / "STATUS.md"
    session_sync_path = _session_sync_path(data_root)

    short_term_content = _read_text(short_term_path)
    status_content = _read_text(status_path)
    git_state = _git_state(project_root)

    pending_tasks = _compact_list(_collect_checklist_items(short_term_content))
    blockers = _compact_list(_collect_blockers(short_term_content))
    next_steps = _compact_list(_collect_next_steps(short_term_content))
    summary_value = summary or _derive_summary(short_term_content, status_content)
    ended_at = iso_now()
    started_at = _derive_started_at(short_term_path, short_term_content)
    session_id = uuid.uuid4().hex[:12]

    record = {
        "session_id": session_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "project": project_name,
        "summary": summary_value,
        "files_touched": git_state["uncommitted_files"],
        "pending_tasks": pending_tasks,
        "blockers": blockers,
        "next_steps": next_steps or (pending_tasks[:3] if pending_tasks else ["Review the updated STATUS.md and continue from the next highest priority task."]),
        "branch": git_state["branch"],
        "uncommitted_files": git_state["uncommitted_files"],
        "agent": agent_name or os.environ.get("AGENT_NAME") or os.environ.get("USER") or "agent",
        "git": {
            "diff_stat": git_state["diff_stat"],
        },
    }
    return {
        "project_root": project_root,
        "data_root": data_root,
        "project_data_root": project_data_root,
        "short_term_path": short_term_path,
        "status_path": status_path,
        "session_sync_path": session_sync_path,
        "record": record,
        "session_id": session_id,
        "summary": summary_value,
    }


def close_session(
    project_root: Path | None = None,
    data_root: Path | None = None,
    agent_name: str | None = None,
    summary: str | None = None,
) -> SessionCloseResult:
    payload = build_session_close_payload(project_root=project_root, data_root=data_root, agent_name=agent_name, summary=summary)
    record = payload["record"]
    project_data_root = payload["project_data_root"]
    session_record_dir = project_data_root / "sessions"
    session_record_dir.mkdir(parents=True, exist_ok=True)
    session_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    record_path = session_record_dir / f"{session_date}_{record['session_id']}.yaml"
    record_path.write_text(yaml.safe_dump(record, sort_keys=False, allow_unicode=True), encoding="utf-8")

    from agentos_host.adapter import AgentOSContextAdapter
    context_adapter = AgentOSContextAdapter(
        project_root=payload["project_root"],
        data_root=payload["data_root"]
    )
    context_adapter.update_short_term_context(record)
    context_adapter.update_status_context(record)
    _append_session_sync(payload["session_sync_path"], record, record_path)

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
