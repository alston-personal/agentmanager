import os
import re
import yaml
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

from runtime_core.interfaces import ContextProviderInterface
from runtime_core.models import SessionContext, SessionClosePayload

from agent_core.platform import get_platform_driver

def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""

def _tail_text(path: Path, max_chars: int = 6000) -> str:
    if not path.exists():
        return ""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            if size <= max_chars:
                handle.seek(0)
            else:
                handle.seek(-max_chars, os.SEEK_END)
            raw = handle.read()
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        try:
            content = path.read_text(encoding="utf-8")
            return content[-max_chars:]
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
    return datetime.now(timezone.utc).isoformat()

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


class AgentOSContextAdapter(ContextProviderInterface):
    """
    Bridges the ContextProviderInterface to AgentOS's symlink-based memory system.
    """
    def __init__(self, project_root: Path, data_root: Path):
        self.project_root = project_root.expanduser().resolve()
        self.data_root = data_root.expanduser().resolve()
        
        # Ensure driver checks symlinks
        driver = get_platform_driver(project_root=self.project_root, data_root=self.data_root)
        driver.ensure_project_links(self.project_root, self.data_root)

        self.project_name = self.project_root.name
        self.project_data_root = self.data_root / "projects" / self.project_name
        self.short_term_path = self.project_data_root / "memory" / "SHORT_TERM.md"
        self.status_path = self.project_data_root / "STATUS.md"
        self.session_sync_path = self.data_root / "memory" / "session_sync.md"

    def load_context(self) -> SessionContext:
        short_term_content = _read_text(self.short_term_path)
        status_content = _read_text(self.status_path)
        git_state = _git_state(self.project_root)

        pending_tasks = _compact_list(_collect_checklist_items(short_term_content))
        blockers = _compact_list(_collect_blockers(short_term_content))
        next_steps = _compact_list(_collect_next_steps(short_term_content))
        summary_value = _derive_summary(short_term_content, status_content)
        started_at = _derive_started_at(self.short_term_path, short_term_content)

        return SessionContext(
            project_id=self.project_name,
            started_at=started_at,
            summary=summary_value,
            pending_tasks=pending_tasks,
            blockers=blockers,
            next_steps=next_steps,
            branch=git_state["branch"],
            uncommitted_files=git_state["uncommitted_files"],
            diff_stat=git_state["diff_stat"],
            host_metadata={
                "raw_status": status_content,
                "raw_short_term": short_term_content,
            },
        )

    def persist_session_close(self, payload: SessionClosePayload) -> tuple[str, str]:
        payload_dict = payload.to_dict()
        self._update_short_term_context(payload_dict)
        self._update_status_context(payload_dict)
        
        # Save session YAML record
        session_record_dir = self.project_data_root / "sessions"
        session_record_dir.mkdir(parents=True, exist_ok=True)
        session_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        record_path = session_record_dir / f"{session_date}_{payload.session_id}.yaml"
        record_path.write_text(yaml.safe_dump(payload_dict, sort_keys=False, allow_unicode=True), encoding="utf-8")
        
        self._append_session_sync(payload_dict, record_path)
        
        compact_entry = "\n".join(
            [
                f"Session `{payload.session_id}` closed for `{payload.project}`",
                f"Summary: {payload.summary}",
                f"Branch: `{payload.branch}`",
                f"Pending: {len(payload.pending_tasks)}, Blockers: {len(payload.blockers)}, Next: {len(payload.next_steps)}",
                f"Record: `{record_path}`",
            ]
        )
        return str(record_path), compact_entry
        
    def _update_short_term_context(self, payload: Dict[str, Any]) -> None:
        self.short_term_path.parent.mkdir(parents=True, exist_ok=True)
        content = _read_text(self.short_term_path).rstrip()
        close_section = "\n".join(
            [
                "## Session Close",
                f"- Session ID: `{payload.get('session_id', 'unknown')}`",
                f"- Closed At: {payload.get('ended_at', 'unknown')}",
                f"- Summary: {payload.get('summary', 'unknown')}",
                f"- Branch: `{payload.get('branch', 'unknown')}`",
                f"- Pending Tasks: {len(payload.get('pending_tasks', []))}",
                f"- Blockers: {len(payload.get('blockers', []))}",
                f"- Next Steps: {len(payload.get('next_steps', []))}",
            ]
        )
        if content:
            if "## Session Close" in content:
                prefix, _, remainder = content.partition("## Session Close")
                tail = remainder
                for marker in ("\n## ", "\n# "):
                    idx = tail.find(marker, 1)
                    if idx != -1:
                        tail = tail[idx:]
                        break
                    tail = ""
                new_content = prefix.rstrip() + "\n\n" + close_section
                if tail:
                    new_content += "\n" + tail.lstrip()
            else:
                new_content = content + "\n\n" + close_section + "\n"
        else:
            new_content = "# SHORT_TERM.md\n\n" + close_section + "\n"
        self.short_term_path.write_text(new_content.rstrip() + "\n", encoding="utf-8")

    def _update_status_context(self, payload: Dict[str, Any]) -> None:
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        content = _read_text(self.status_path)
        if not content.strip():
            content = "---\n---\n\n# Project Status\n\n## 📍 Summary\n| Metric | Value |\n| :--- | :--- |\n| **Last Status** | N/A |\n| **Last Updated** | N/A |\n\n## 🪵 Activity Log (Latest on Top)\n<!-- LOG_START -->\n"

        summary_value = payload.get("summary", "")
        updated_value = payload.get("ended_at", "").replace(" UTC", "")
        content = re.sub(
            r"(\|\s*\*\*Last Status\*\*\s*\|\s*)([^|]+?)(\s*\|)",
            lambda match: f"{match.group(1)}{summary_value}{match.group(3)}",
            content,
            count=1,
        )
        content = re.sub(
            r"(\|\s*\*\*Last Updated\*\*\s*\|\s*)([^|]+?)(\s*\|)",
            lambda match: f"{match.group(1)}{updated_value}{match.group(3)}",
            content,
            count=1,
        )
        activity_entry = (
            f"- `{updated_value}` 🤝 **SESSION CLOSE**: {summary_value} "
            f"(Session `{payload.get('session_id', 'unknown')}`, branch `{payload.get('branch', 'unknown')}`, "
            f"pending {len(payload.get('pending_tasks', []))}, blockers {len(payload.get('blockers', []))}, next {len(payload.get('next_steps', []))})"
        )
        if "<!-- LOG_START -->" in content:
            content = content.replace("<!-- LOG_START -->", "<!-- LOG_START -->\n" + activity_entry, 1)
        else:
            content = content.rstrip() + "\n\n## 🪵 Activity Log (Latest on Top)\n<!-- LOG_START -->\n" + activity_entry + "\n"

        session_block = "\n".join(
            [
                "",
                "## 🤝 Recent Session Close",
                f"- Session ID: `{payload.get('session_id', 'unknown')}`",
                f"- Summary: {summary_value}",
                f"- Pending Tasks: {len(payload.get('pending_tasks', []))}",
                f"- Blockers: {len(payload.get('blockers', []))}",
                f"- Next Steps: {len(payload.get('next_steps', []))}",
                f"- Branch: `{payload.get('branch', 'unknown')}`",
            ]
        )
        if "## 🤝 Recent Session Close" in content:
            content = re.sub(r"\n## 🤝 Recent Session Close.*", session_block + "\n", content, flags=re.S)
        else:
            content = content.rstrip() + session_block + "\n"
        self.status_path.write_text(content.rstrip() + "\n", encoding="utf-8")

    def _archive_session_sync_if_needed(self) -> None:
        if not self.session_sync_path.exists() or self.session_sync_path.stat().st_size <= 50_000:
            return
        archive_dir = self.session_sync_path.parent / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive_path = archive_dir / f"session_sync_{stamp}.md"
        archive_path.write_text(self.session_sync_path.read_text(encoding="utf-8"), encoding="utf-8")
        self.session_sync_path.write_text(
            "# 🧠 AgentOS Session Sync - Compressed Working Memory\n"
            "> Auto-rotated because the buffer exceeded 50KB.\n",
            encoding="utf-8",
        )

    def _append_session_sync(self, payload: dict[str, Any], record_path: Path) -> None:
        self.session_sync_path.parent.mkdir(parents=True, exist_ok=True)
        self._archive_session_sync_if_needed()
        compact = "\n".join(
            [
                f"## Session Handoff @ {payload['ended_at']}",
                f"- **Project**: `{payload['project']}`",
                f"- **Session ID**: `{payload['session_id']}`",
                f"- **Summary**: {payload['summary']}",
                f"- **Branch**: `{payload['branch']}`",
                f"- **Pending Tasks**: {len(payload.get('pending_tasks', []))}",
                f"- **Blockers**: {len(payload.get('blockers', []))}",
                f"- **Next Steps**: {len(payload.get('next_steps', []))}",
                f"- **Uncommitted Files**: {', '.join(payload.get('uncommitted_files', [])[:5]) or 'none'}",
                f"- **Session Record**: `{record_path}`",
                "",
            ]
        )
        existing = _read_text(self.session_sync_path).rstrip()
        if existing:
            content = existing + "\n\n" + compact
        else:
            content = "# 🧠 AgentOS Session Sync - Compressed Working Memory\n\n" + compact
        self.session_sync_path.write_text(content.rstrip() + "\n", encoding="utf-8")

    def read_compact_session_sync(self, max_chars: int = 6000) -> str:
        return _tail_text(self.session_sync_path, max_chars=max_chars)

    def latest_session_records(self, limit: int = 3) -> list[dict[str, Any]]:
        session_dir = self.project_data_root / "sessions"
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
